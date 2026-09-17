#!/usr/bin/env python3
"""T-108: one secrets canon — values go to the Keychain via `ai-secret`, never to files.

Every test here runs against the stub broker from tests/helpers/ai_secret_stub.py,
reached through `SEO_CYCLE_AI_SECRET` under a fake HOME; the real
`ai-secret`/Keychain of the machine is never reached (the default
`~/.local/bin/ai-secret` resolves inside an empty temp HOME, and PATH is not
consulted by the code under test at all — wave K 🟡-1).
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
LAUNCHER = ROOT / "bin" / "seo-cycle"
sys.path.insert(0, str(ROOT / "tests" / "helpers"))

from ai_secret_stub import broker_override, clean_env, install_stub, isolated_path, seed_store, stub_log  # noqa: E402

SECRET_VALUE = "sk-live-T108-do-not-leak-9f3a"
CONFIG_WITH_SCOPE = "project:\n  name: Test Project\n  brand_name_technical: testproj\n"
CONFIG_NO_SCOPE = "project:\n  name: Test Project\n"


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-t108-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.stub_dir = self.tmp / "stub"
        install_stub(self.stub_dir)
        self.empty_dir = self.tmp / "nothing"
        self.empty_dir.mkdir()
        self.home = self.tmp / "home"  # empty: no ~/.local/bin/ai-secret here
        self.home.mkdir()
        self.global_env = self.tmp / "env.global"

    def env(self, *, with_stub: bool, extra: dict[str, str] | None = None) -> dict[str, str]:
        # The stub is wired ONLY through the override variable; PATH never
        # contains it, so a green run here also proves PATH is not consulted.
        override = broker_override(self.stub_dir) if with_stub else {}
        return clean_env(path=isolated_path(self.empty_dir), home=self.home,
                         extra={"SEO_CYCLE_GLOBAL_ENV": str(self.global_env), **override, **(extra or {})})

    def auth(self, *args: str, with_stub: bool = True, stdin: str | None = None,
             extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "auth-assistant.py"), *args],
            cwd=self.project, env=self.env(with_stub=with_stub, extra=extra),
            input=stdin, text=True, capture_output=True, check=False, timeout=60,
        )

    def write_config(self, text: str = CONFIG_WITH_SCOPE) -> None:
        (self.project / "seo-cycle.yaml").write_text(text, encoding="utf-8")

    def env_file_has(self, name: str) -> int:
        path = self.project / ".env"
        if not path.exists():
            return 0
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.startswith(f"{name}="))

    def assert_no_leak(self, proc: subprocess.CompletedProcess) -> None:
        self.assertNotIn(SECRET_VALUE, proc.stdout)
        self.assertNotIn(SECRET_VALUE, proc.stderr)
        self.assertNotIn(SECRET_VALUE, stub_log(self.stub_dir))
        env_path = self.project / ".env"
        if env_path.exists():
            self.assertNotIn(SECRET_VALUE, env_path.read_text(encoding="utf-8"))
        if self.global_env.exists():
            self.assertNotIn(SECRET_VALUE, self.global_env.read_text(encoding="utf-8"))


class AuthSetTest(_Base):
    def test_set_goes_to_keychain_not_env(self) -> None:
        # Criterion: after `auth set X` grep -c '^X=' .env == 0, stub log has X.
        self.write_config()
        proc = self.auth("set", "PERPLEXITY_API_KEY", stdin=SECRET_VALUE + "\n")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.env_file_has("PERPLEXITY_API_KEY"), 0)
        self.assertFalse((self.project / ".env").exists())
        self.assertIn("set testproj PERPLEXITY_API_KEY", stub_log(self.stub_dir))
        self.assertIn("Keychain scope `testproj`", proc.stderr)
        self.assert_no_leak(proc)

    def test_set_global_uses_global_scope(self) -> None:
        self.write_config()
        proc = self.auth("set", "TELEGRAM_BOT_TOKEN", "--global", stdin=SECRET_VALUE + "\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("set global TELEGRAM_BOT_TOKEN", stub_log(self.stub_dir))
        self.assertFalse(self.global_env.exists())
        self.assert_no_leak(proc)

    def test_set_explicit_scope_override(self) -> None:
        self.write_config(CONFIG_NO_SCOPE)
        proc = self.auth("set", "KEYSO_API_TOKEN", "--scope", "client-a", stdin=SECRET_VALUE + "\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("set client-a KEYSO_API_TOKEN", stub_log(self.stub_dir))

    def test_set_without_ai_secret_fails_loudly(self) -> None:
        # Criterion: no ai-secret on PATH -> rc != 0, stderr names ai-secret, nothing written.
        self.write_config()
        proc = self.auth("set", "PERPLEXITY_API_KEY", with_stub=False, stdin=SECRET_VALUE + "\n")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("ai-secret", proc.stderr)
        self.assertIn("секреты не подключены", proc.stderr)
        self.assertFalse((self.project / ".env").exists())
        self.assertFalse(self.global_env.exists())
        self.assert_no_leak(proc)

    def test_set_without_scope_asks_for_brand_name_technical(self) -> None:
        self.write_config(CONFIG_NO_SCOPE)
        proc = self.auth("set", "PERPLEXITY_API_KEY", stdin=SECRET_VALUE + "\n")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("brand_name_technical", proc.stderr)
        self.assertEqual(stub_log(self.stub_dir), "")
        self.assert_no_leak(proc)

    def test_value_on_argv_is_rejected(self) -> None:
        # `--value` would put the secret into `ps` and the dispatcher log — removed.
        self.write_config()
        proc = self.auth("set", "PERPLEXITY_API_KEY", "--value", SECRET_VALUE)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unrecognized arguments: --value", proc.stderr)
        self.assertEqual(stub_log(self.stub_dir), "")

    def test_empty_value_is_refused(self) -> None:
        self.write_config()
        proc = self.auth("set", "PERPLEXITY_API_KEY", stdin="\n")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("пустое значение", proc.stderr)
        self.assertEqual(stub_log(self.stub_dir), "")

    def test_broker_failure_is_reported(self) -> None:
        # Negative control for "rc 0 by accident": a broker that refuses must surface.
        self.write_config()
        broken = self.tmp / "broken"
        broken.mkdir()
        (broken / "ai-secret").write_text(f"#!{sys.executable}\nimport sys\nsys.stdin.readline()\n"
                                          "print('keychain error (OSStatus -25308)', file=sys.stderr)\n"
                                          "sys.exit(14)\n", encoding="utf-8")
        (broken / "ai-secret").chmod(0o755)
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "auth-assistant.py"), "set", "PERPLEXITY_API_KEY"],
            cwd=self.project, env=clean_env(path=isolated_path(self.empty_dir), home=self.home,
                                            extra=broker_override(broken)),
            input=SECRET_VALUE + "\n", text=True, capture_output=True, check=False, timeout=60,
        )
        self.assertEqual(proc.returncode, 14, proc.stderr)
        self.assertIn("OSStatus", proc.stderr)
        self.assertNotIn(SECRET_VALUE, proc.stdout + proc.stderr)


class BrokerResolutionTest(_Base):
    """Wave K 🟡-1: the broker is taken from `~/.local/bin/ai-secret` or the
    explicit `SEO_CYCLE_AI_SECRET` — never from PATH (policy §5: PATH is
    untrusted, and `ai-secret set` receives secret values over stdin)."""

    def _sentinel(self, directory: pathlib.Path) -> pathlib.Path:
        """A fake `ai-secret` that only logs it was called and fails."""
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "ai-secret").write_text(
            f"#!{sys.executable}\nimport pathlib, sys\n"
            "pathlib.Path(__file__).resolve().with_name('sentinel.log').write_text('CALLED\\n')\n"
            "sys.exit(99)\n", encoding="utf-8")
        (directory / "ai-secret").chmod(0o755)
        return directory / "sentinel.log"

    def test_stub_first_in_path_without_override_is_not_used(self) -> None:
        # Control question 1 of the wave-K gate: a foreign `ai-secret` earlier
        # in PATH must not receive the value. No override, empty HOME -> rc 3.
        self.write_config()
        env = clean_env(path=isolated_path(self.stub_dir), home=self.home,
                        extra={"SEO_CYCLE_GLOBAL_ENV": str(self.global_env)})
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "auth-assistant.py"), "set", "PERPLEXITY_API_KEY"],
            cwd=self.project, env=env, input=SECRET_VALUE + "\n",
            text=True, capture_output=True, check=False, timeout=60,
        )
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("секреты не подключены", proc.stderr)
        self.assertEqual(stub_log(self.stub_dir), "")  # the PATH stub never ran
        self.assert_no_leak(proc)

    def test_canonical_path_wins_over_a_sentinel_in_path(self) -> None:
        # Sentinel first in PATH, real (stub) broker at $HOME/.local/bin — the
        # canonical one is called, the sentinel log stays empty.
        self.write_config()
        sentinel_log = self._sentinel(self.tmp / "evil")
        canonical_dir = self.home / ".local" / "bin"
        install_stub(canonical_dir)
        env = clean_env(path=isolated_path(self.tmp / "evil"), home=self.home,
                        extra={"SEO_CYCLE_GLOBAL_ENV": str(self.global_env)})
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "auth-assistant.py"), "set", "PERPLEXITY_API_KEY"],
            cwd=self.project, env=env, input=SECRET_VALUE + "\n",
            text=True, capture_output=True, check=False, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("set testproj PERPLEXITY_API_KEY", stub_log(canonical_dir))
        self.assertFalse(sentinel_log.exists())
        self.assertNotIn(SECRET_VALUE, proc.stdout + proc.stderr)

    def test_override_variable_selects_the_broker(self) -> None:
        # Same sentinel in PATH; the override names the stub explicitly.
        self.write_config()
        sentinel_log = self._sentinel(self.tmp / "evil")
        env = clean_env(path=isolated_path(self.tmp / "evil"), home=self.home,
                        extra={"SEO_CYCLE_GLOBAL_ENV": str(self.global_env), **broker_override(self.stub_dir)})
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "auth-assistant.py"), "set", "PERPLEXITY_API_KEY"],
            cwd=self.project, env=env, input=SECRET_VALUE + "\n",
            text=True, capture_output=True, check=False, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("set testproj PERPLEXITY_API_KEY", stub_log(self.stub_dir))
        self.assertFalse(sentinel_log.exists())

    def test_override_pointing_nowhere_does_not_fall_back(self) -> None:
        # An explicit override that does not exist = "not wired", not a quiet
        # fallback to the default path or PATH (both hold a stub here).
        self.write_config()
        install_stub(self.home / ".local" / "bin")
        env = clean_env(path=isolated_path(self.stub_dir), home=self.home,
                        extra={"SEO_CYCLE_GLOBAL_ENV": str(self.global_env),
                               "SEO_CYCLE_AI_SECRET": str(self.tmp / "missing" / "ai-secret")})
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "auth-assistant.py"), "set", "PERPLEXITY_API_KEY"],
            cwd=self.project, env=env, input=SECRET_VALUE + "\n",
            text=True, capture_output=True, check=False, timeout=60,
        )
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertEqual(stub_log(self.stub_dir), "")
        self.assertEqual(stub_log(self.home / ".local" / "bin"), "")


class AuthLoginTest(_Base):
    def test_login_prompts_each_var_and_stores_in_keychain(self) -> None:
        self.write_config()
        # WordPress REST family: 3 required vars, no optional -> three stdin lines.
        proc = self.auth("login", "wordpress", stdin="https://example.com\nadmin\n" + SECRET_VALUE + "\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        log = stub_log(self.stub_dir)
        for name in ("WP_BASE_URL", "WP_USER", "WP_APP_PASSWORD"):
            self.assertIn(f"set testproj {name}", log)
        self.assertNotIn("WP_API_URL", log)
        self.assertIn("статус провайдера: ready", proc.stderr)
        self.assertFalse((self.project / ".env").exists())
        self.assert_no_leak(proc)

    def test_login_mcp_is_a_separate_provider(self) -> None:
        self.write_config()
        proc = self.auth("login", "wordpress-mcp", stdin="https://example.com/wp-json/mcp/novamira\nadmin\n" + SECRET_VALUE + "\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        log = stub_log(self.stub_dir)
        for name in ("WP_API_URL", "WP_API_USERNAME", "WP_API_PASSWORD"):
            self.assertIn(f"set testproj {name}", log)
        self.assertNotIn("WP_BASE_URL", log)

    def test_login_without_ai_secret_fails_before_prompting(self) -> None:
        self.write_config()
        proc = self.auth("login", "yandex", with_stub=False, stdin=SECRET_VALUE + "\n")
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("ai-secret", proc.stderr)
        self.assertFalse((self.project / ".env").exists())
        self.assert_no_leak(proc)

    def test_login_unknown_provider_still_fails_with_2(self) -> None:
        self.write_config()
        proc = self.auth("login", "nosuch", with_stub=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("неизвестный провайдер", proc.stderr)


class AuthListTest(_Base):
    def test_list_reports_keychain_process_and_legacy_sources(self) -> None:
        self.write_config()
        seed_store(self.stub_dir, {
            "testproj/PERPLEXITY_API_KEY": "p", "global/TELEGRAM_BOT_TOKEN": "t", "global/TELEGRAM_CHAT_ID": "c",
        })
        (self.project / ".env").write_text("NEURON_API_KEY=legacy-value\n", encoding="utf-8")
        proc = self.auth("list", "--format", "json", extra={"KEYSO_API_TOKEN": "from-process"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertIn("scope=testproj", proc.stderr)
        self.assertIn("ai-secret=" + str(self.stub_dir / "ai-secret"), proc.stderr)
        # every top-level key is a provider row (the dashboard iterates them all)
        for alias, data in report.items():
            self.assertIn("state", data, alias)
        rows = {r["var"]: r["source"] for alias in report for r in report[alias]["vars"]}
        self.assertEqual(rows["PERPLEXITY_API_KEY"], "keychain:testproj")
        self.assertEqual(rows["TELEGRAM_BOT_TOKEN"], "keychain:global")
        self.assertEqual(rows["KEYSO_API_TOKEN"], "process")
        self.assertEqual(rows["NEURON_API_KEY"], "project")  # legacy file, read-only
        self.assertEqual(rows["WP_APP_PASSWORD"], None)
        self.assertEqual(report["telegram"]["state"], "ready")
        self.assertEqual(report["perplexity"]["state"], "ready")
        # names only travelled: the stub was asked to list, never to run/get
        self.assertIn("list testproj", stub_log(self.stub_dir))
        self.assertIn("list global", stub_log(self.stub_dir))
        self.assertNotIn("run ", stub_log(self.stub_dir))
        for value in ("legacy-value", "from-process"):
            self.assertNotIn(value, proc.stdout)

    def test_list_md_marks_sources_and_keeps_minimum_tier(self) -> None:
        self.write_config()
        seed_store(self.stub_dir, {"testproj/YANDEX_OAUTH_TOKEN": "y"})
        proc = self.auth("list")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[keychain:testproj]", proc.stdout)
        self.assertIn("YANDEX_OAUTH_TOKEN", proc.stdout)
        self.assertGreaterEqual(proc.stdout.count("минимум для pulse"), 2)  # T-100 kept
        self.assertIn("legacy", proc.stdout)

    def test_list_without_ai_secret_is_rc0_and_honest(self) -> None:
        self.write_config()
        proc = self.auth("list", with_stub=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("секреты не подключены", proc.stdout)
        proc = self.auth("list", "--format", "json", with_stub=False)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("ai-secret=not-found", proc.stderr)
        self.assertNotIn("_secrets", json.loads(proc.stdout))


class LauncherSecretsTest(_Base):
    """bin/seo-cycle: fetching commands never run silently without keys."""

    def launcher(self, *args: str, with_stub: bool, extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(LAUNCHER), *args],
            cwd=self.project, env=self.env(with_stub=with_stub, extra=extra),
            text=True, capture_output=True, check=False, timeout=120,
        )

    def test_pulse_without_keys_and_without_ai_secret_warns(self) -> None:
        # Criterion: warning line in stderr; the command still reaches pulse.
        self.write_config()
        proc = self.launcher("pulse", "--skip-fetch", with_stub=False)
        self.assertIn("ai-secret", proc.stderr)
        self.assertIn("ключи провайдеров не в окружении", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_pulse_without_keys_reexecs_under_ai_secret_run(self) -> None:
        self.write_config()
        proc = self.launcher("pulse", "--skip-fetch", with_stub=True)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("run testproj", stub_log(self.stub_dir))
        self.assertEqual(stub_log(self.stub_dir).count("run testproj"), 1)  # loop guard

    def test_scope_without_pulse_keys_is_named_after_reexec(self) -> None:
        # Review round 1 (🟡-2): broker present, scope present, but the scope holds
        # no pulse key (keys live under another scope) — the child must say so.
        self.write_config()
        seed_store(self.stub_dir, {"testproj/PERPLEXITY_API_KEY": "x"})
        proc = self.launcher("pulse", "--skip-fetch", with_stub=True)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(stub_log(self.stub_dir).count("run testproj"), 1)
        self.assertIn("в Keychain scope `testproj`", proc.stderr)
        self.assertIn("auth login yandex", proc.stderr)

    def test_reexec_with_pulse_key_in_scope_is_silent(self) -> None:
        self.write_config()
        seed_store(self.stub_dir, {"testproj/YANDEX_OAUTH_TOKEN": "y"})
        proc = self.launcher("pulse", "--skip-fetch", with_stub=True)
        self.assertEqual(stub_log(self.stub_dir).count("run testproj"), 1)
        self.assertNotIn("⚠ seo-cycle pulse", proc.stderr)

    def test_keys_already_in_env_are_never_overridden(self) -> None:
        self.write_config()
        proc = self.launcher("pulse", "--skip-fetch", with_stub=True,
                             extra={"YANDEX_OAUTH_TOKEN": "exported-by-hand"})
        self.assertNotIn("Traceback", proc.stderr)
        self.assertNotIn("run ", stub_log(self.stub_dir))
        self.assertNotIn("ключи провайдеров не в окружении", proc.stderr)

    def test_scope_missing_names_the_config_field(self) -> None:
        self.write_config(CONFIG_NO_SCOPE)
        proc = self.launcher("pulse", "--skip-fetch", with_stub=True)
        self.assertIn("brand_name_technical", proc.stderr)
        self.assertNotIn("run ", stub_log(self.stub_dir))

    def test_non_fetching_commands_do_not_touch_the_broker(self) -> None:
        self.write_config()
        proc = self.launcher("validate", with_stub=True)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(stub_log(self.stub_dir), "")

    def test_provider_specific_commands_are_not_reexeced(self) -> None:
        # `notify`/`sync`/`ads`/`feed` need keys the launcher cannot judge by the
        # pulse names — re-exec there could override a hand-exported WP/Telegram
        # value, so they stay on the manual `ai-secret run` path (documented).
        self.write_config()
        proc = self.launcher("notify", "probe", with_stub=True, extra={"TELEGRAM_BOT_TOKEN": "exported"})
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(stub_log(self.stub_dir), "")

    def test_broken_yaml_gets_the_cli_error_not_a_traceback(self) -> None:
        (self.project / "seo-cycle.yaml").write_text("project: [unclosed\n", encoding="utf-8")
        proc = self.launcher("pulse", "--skip-fetch", with_stub=True)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("ERROR", proc.stderr)
        self.assertEqual(stub_log(self.stub_dir), "")


class GbpHelperTest(_Base):
    def test_store_scope_requires_ai_secret_before_the_oauth_dance(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "gbp-oauth-helper.py"), "--store-scope", "testproj", "--print-url-only"],
            cwd=self.project, env=self.env(with_stub=False, extra={"GBP_OAUTH_CLIENT_ID": "id", "GBP_OAUTH_CLIENT_SECRET": "s"}),
            text=True, capture_output=True, check=False, timeout=60,
        )
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("ai-secret", proc.stderr)

    def test_write_env_flag_is_gone(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "gbp-oauth-helper.py"), "--write-env", str(self.project / ".env")],
            cwd=self.project, env=self.env(with_stub=True), text=True, capture_output=True, check=False, timeout=60,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unrecognized arguments: --write-env", proc.stderr)


class NoSecretWritersLeftTest(unittest.TestCase):
    def test_upsert_env_var_only_writes_the_gbp_date_marker(self) -> None:
        # Criterion: `grep -rn upsert_env_var scripts/` has no call with a secret value.
        hits = []
        for path in sorted(SCRIPTS.rglob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "upsert_env_var(" in line and "def upsert_env_var" not in line:
                    hits.append((path.relative_to(ROOT).as_posix(), number, line.strip()))
        self.assertEqual(len(hits), 1, hits)
        path, number, _ = hits[0]
        self.assertEqual(path, "scripts/gbp-oauth-helper.py")
        lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
        call = " ".join(lines[number - 1:number + 1])  # the call spans two lines
        self.assertIn('"GBP_TOKEN_MINTED_AT"', call)
        self.assertNotIn("refresh", call)

    def test_wordpress_name_families_are_split_by_purpose(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("auth_assistant", SCRIPTS / "auth-assistant.py")
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(SCRIPTS))
        spec.loader.exec_module(module)
        self.assertEqual(module.PROVIDERS["wordpress"]["env"], ["WP_BASE_URL", "WP_USER", "WP_APP_PASSWORD"])
        self.assertEqual(module.PROVIDERS["wordpress-mcp"]["env"], ["WP_API_URL", "WP_API_USERNAME", "WP_API_PASSWORD"])
        self.assertEqual(module.PROVIDERS["yandex"]["tier"], "minimum")  # T-100 kept


if __name__ == "__main__":
    unittest.main()
