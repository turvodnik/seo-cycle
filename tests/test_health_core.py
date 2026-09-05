#!/usr/bin/env python3
"""T-053: golden-tests for the shared health engine (`seo_cycle_core/health.py`).

Two things this test proves:

1. **Byte-for-byte compatibility.** `gbp/google-ads/merchant/yandex-direct/
   yandex-business/notebooklm/perplexity-health.py` were rewritten as thin
   `HealthSpec` wrappers over one shared engine. Every case in
   `tests/fixtures/health/` was captured from the PRE-refactor scripts
   (commit that added the fixtures is the first commit of this ticket — it
   predates every wrapper edit) and is replayed here against the CURRENT
   scripts. The only two fields allowed to differ are the ones that are
   inherently non-deterministic even without any refactor: the ISO
   `Generated:`/`generated_at` timestamp (`<TS>`) and the tmp-dir cwd path
   baked into "config not found" error text (`<CWD-ROOT>`) — both
   normalized identically on both sides.

2. **A core fix reaches all seven at once.** Before this ticket, a fix
   landed in one hand-copied `*-health.py` and never reached its five
   siblings (v2.0.2 — see the ticket). `test_core_fix_reaches_all_providers`
   patches ONE constant in `seo_cycle_core.health` and shows the effect on
   all seven providers' output without touching a single wrapper file —
   proving the shared engine actually closes that failure mode.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "health"

sys.path.insert(0, str(SCRIPTS))

TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\+\d{2}:\d{2}|Z)")

ENV_PREFIXES_TO_STRIP = (
    "GBP_", "GOOGLE_BUSINESS_", "GOOGLE_ADS_", "GOOGLE_MERCHANT_",
    "GOOGLE_APPLICATION_CREDENTIALS", "YANDEX_DIRECT_", "YANDEX_MERCHANT_",
    "PERPLEXITY_",
)

BASE_CFG_RU = """
project:
  name: Provider Test
  domain: provider.test
region_profile: ru
locale:
  country: RU
engines:
  - name: yandex
project_type: ecommerce
expert_sources:
  notebooklm_url: https://notebooklm.google.com/notebook/test
business_profile:
  gbp_url: https://maps.google.com/test
  yandex_business_url: https://yandex.ru/business/test
"""
BASE_CFG_NONRU = BASE_CFG_RU.replace("region_profile: ru", "region_profile: global")


def normalize(text: str, cwd_root: pathlib.Path) -> str:
    text = text.replace(str(cwd_root), "<CWD-ROOT>")
    return TS_RE.sub("<TS>", text)


def clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if any(key.startswith(p) for p in ENV_PREFIXES_TO_STRIP):
            env.pop(key, None)
    if extra:
        env.update(extra)
    return env


def run_script(script: str, args: list[str], cwd: pathlib.Path, env: dict[str, str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        cwd=cwd, env=env, text=True, capture_output=True, check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


# provider, case, script, cwd_kind ("no-config"|"ru"|"nonru"), cli_extra (relative to
# config path, i.e. flags AFTER the config positional), env
CASES: list[tuple[str, str, str, str, list[str], dict[str, str]]] = [
    ("gbp", "no-config", "gbp-health.py", "no-config", [], {}),
    ("gbp", "present", "gbp-health.py", "ru", [], {
        "GBP_OAUTH_CLIENT_ID": "x", "GBP_OAUTH_CLIENT_SECRET": "x", "GBP_OAUTH_REFRESH_TOKEN": "x",
        "GOOGLE_BUSINESS_ACCOUNT_ID": "x", "GOOGLE_BUSINESS_LOCATION_ID": "x",
    }),
    ("gbp", "missing-oauth", "gbp-health.py", "ru", [], {
        "GOOGLE_BUSINESS_ACCOUNT_ID": "x", "GOOGLE_BUSINESS_LOCATION_ID": "x",
    }),
    ("gbp", "missing-id", "gbp-health.py", "ru", [], {
        "GBP_OAUTH_CLIENT_ID": "x", "GBP_OAUTH_CLIENT_SECRET": "x", "GBP_OAUTH_REFRESH_TOKEN": "x",
    }),
    ("google-ads", "no-config", "google-ads-health.py", "no-config", [], {}),
    ("google-ads", "present", "google-ads-health.py", "nonru", [], {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "x", "GOOGLE_ADS_CLIENT_ID": "x",
        "GOOGLE_ADS_CLIENT_SECRET": "x", "GOOGLE_ADS_REFRESH_TOKEN": "x", "GOOGLE_ADS_CUSTOMER_ID": "x",
    }),
    ("google-ads", "missing-ru", "google-ads-health.py", "ru", [], {}),
    ("google-ads", "missing-nonru", "google-ads-health.py", "nonru", [], {}),
    ("merchant", "no-config", "merchant-health.py", "no-config", [], {}),
    ("merchant", "present", "merchant-health.py", "nonru", [], {
        "GOOGLE_MERCHANT_ACCOUNT_ID": "x", "GOOGLE_APPLICATION_CREDENTIALS": "x",
    }),
    ("merchant", "missing-ru", "merchant-health.py", "ru", [], {}),
    ("merchant", "missing-nonru", "merchant-health.py", "nonru", [], {}),
    ("yandex-direct", "no-config", "yandex-direct-health.py", "no-config", [], {}),
    ("yandex-direct", "present", "yandex-direct-health.py", "ru", [], {"YANDEX_DIRECT_TOKEN": "x"}),
    ("yandex-direct", "missing", "yandex-direct-health.py", "ru", [], {}),
    ("yandex-business", "no-config", "yandex-business-health.py", "no-config", [], {}),
    ("yandex-business", "present", "yandex-business-health.py", "ru", [], {"YANDEX_MERCHANT_BUSINESS_ID": "x"}),
    ("yandex-business", "missing", "yandex-business-health.py", "ru", [], {}),
    ("notebooklm", "no-config", "notebooklm-health.py", "no-config", [], {}),
    ("notebooklm", "configured-no-tools", "notebooklm-health.py", "ru",
     ["--codex-config", "<CFGTOML>"], {}),
    ("notebooklm", "tools-exposed", "notebooklm-health.py", "ru",
     ["--codex-config", "<CFGTOML>", "--tools-exposed"], {}),
    ("notebooklm", "not-configured", "notebooklm-health.py", "ru",
     ["--codex-config", "<CFGTOML-EMPTY>"], {}),
    ("perplexity", "no-config", "perplexity-health.py", "no-config", [], {}),
    ("perplexity", "degraded", "perplexity-health.py", "ru", ["--app-path", "<MISSING-APP>"], {}),
    ("perplexity", "browser-available", "perplexity-health.py", "ru",
     ["--app-path", "<MISSING-APP>", "--browser-available"], {}),
]

ALL_SIMPLE_SCRIPTS = ("gbp-health.py", "google-ads-health.py", "merchant-health.py",
                       "yandex-direct-health.py", "yandex-business-health.py")
ALL_POLICY_SCRIPTS = ("notebooklm-health.py", "perplexity-health.py")
ALL_SEVEN_SCRIPTS = ALL_SIMPLE_SCRIPTS + ALL_POLICY_SCRIPTS


class HealthGoldenTest(unittest.TestCase):
    """Every fixture case, replayed against the CURRENT (refactored)
    scripts, compared byte-for-byte (after `<TS>`/`<CWD-ROOT>` normalization)
    against the golden captured before the refactor."""

    @classmethod
    def setUpClass(cls) -> None:
        # .resolve(): mkdtemp() on macOS returns /var/folders/... but a
        # child process's actual cwd (what ends up in "not found in <cwd>"
        # error text) resolves the /var -> /private/var symlink.
        cls.cwd_root = pathlib.Path(tempfile.mkdtemp(prefix="health-golden-test-")).resolve()
        cls.no_config = cls.cwd_root / "no-config"
        cls.ru = cls.cwd_root / "ru"
        cls.nonru = cls.cwd_root / "nonru"
        for d, text in ((cls.no_config, None), (cls.ru, BASE_CFG_RU), (cls.nonru, BASE_CFG_NONRU)):
            d.mkdir(parents=True, exist_ok=True)
            if text is not None:
                (d / "seo-cycle.yaml").write_text(text, encoding="utf-8")
        (cls.ru / "config.toml").write_text('[mcp_servers.notebooklm]\ncommand = "npx"\n', encoding="utf-8")
        (cls.ru / "config-empty.toml").write_text("", encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.cwd_root, ignore_errors=True)

    def _cwd_for(self, kind: str) -> pathlib.Path:
        return {"no-config": self.no_config, "ru": self.ru, "nonru": self.nonru}[kind]

    def _resolve_extra(self, extra: list[str], cwd: pathlib.Path) -> list[str]:
        subst = {
            "<CFGTOML>": str(cwd / "config.toml"),
            "<CFGTOML-EMPTY>": str(cwd / "config-empty.toml"),
            "<MISSING-APP>": str(cwd / "Missing.app"),
        }
        return [subst.get(item, item) for item in extra]

    def _golden(self, name: str) -> str:
        path = FIXTURES / name
        self.assertTrue(path.exists(), f"missing golden fixture: {path}")
        return path.read_text(encoding="utf-8")

    def test_golden_cases(self) -> None:
        for provider, case, script, cwd_kind, extra, env_extra in CASES:
            with self.subTest(provider=provider, case=case):
                cwd = self._cwd_for(cwd_kind)
                resolved_extra = self._resolve_extra(extra, cwd)
                cfg_args = [] if cwd_kind == "no-config" else [str(cwd / "seo-cycle.yaml")] + resolved_extra
                env = clean_env(env_extra)
                prefix = f"{provider}-{case}"

                rc_md, out_md, err_md = run_script(script, cfg_args + ["--format", "md"], cwd, env)
                self.assertEqual(normalize(out_md, self.cwd_root), self._golden(f"{prefix}.md"))

                rc_json, out_json, err_json = run_script(script, cfg_args + ["--format", "json"], cwd, env)
                self.assertEqual(normalize(out_json, self.cwd_root), self._golden(f"{prefix}.json"))

                meta = json.loads(self._golden(f"{prefix}-meta.json"))
                self.assertEqual(rc_md, meta["rc_md"])
                self.assertEqual(rc_json, meta["rc_json"])
                self.assertEqual(normalize(err_md, self.cwd_root), meta["stderr_md"])
                self.assertEqual(normalize(err_json, self.cwd_root), meta["stderr_json"])

                golden_help = self._golden(f"{prefix}-help.txt")
                rc_h, out_h, err_h = run_script(script, ["--help"], cwd, env)
                self.assertEqual(out_h + err_h, golden_help)

                golden_write = json.loads(self._golden(f"{prefix}-write.json"))
                if cwd_kind != "no-config":
                    setup_dir = cwd / "seo" / "setup"
                    shutil.rmtree(setup_dir, ignore_errors=True)
                    rc_w, out_w, err_w = run_script(script, cfg_args + ["--write", "--format", "md"], cwd, env)
                    bundle = {}
                    if setup_dir.exists():
                        for p in sorted(setup_dir.iterdir()):
                            bundle[p.name] = normalize(p.read_text(encoding="utf-8"), self.cwd_root)
                    self.assertEqual(bundle, golden_write)
                    write_meta = json.loads(self._golden(f"{prefix}-meta.json"))["write_meta"]
                    self.assertEqual(rc_w, write_meta["rc"])
                    self.assertEqual(normalize(out_w, self.cwd_root), write_meta["stdout"])
                    self.assertEqual(normalize(err_w, self.cwd_root), write_meta["stderr"])
                    shutil.rmtree(setup_dir, ignore_errors=True)
                else:
                    self.assertEqual(golden_write, {})


class CoreFixReachesAllProvidersTest(unittest.TestCase):
    """The regression this ticket exists to prevent: v2.0.2 fixed the
    "config not found" wording in ONE hand-copied script and it never
    reached the other five. Patch that ONE message in the shared engine —
    `seo_cycle_core.health.MISSING_CONFIG_MSG` — and show it changes the
    output of all seven wrappers, without touching a single wrapper file.

    Review round 1 caught this test passing against a MUTATED `gbp-health.py`
    that no longer went through the shared engine at all (its own local
    copy of `_run_simple`, byte-identical output) — exactly the v2.0.2
    failure shape. Root cause: `importlib.util.spec_from_file_location` +
    `exec_module()` only *defines* `SPEC`/`run_health` in the loaded module;
    it never executes the wrapper's `if __name__ == "__main__":` line, so a
    wrapper that stopped calling the shared `run_health` at all was never
    actually exercised — the test called `health_core.run_health(module.SPEC)`
    itself, bypassing whatever the wrapper's own `__main__` block does.
    Fix: run the wrapper as a real subprocess-equivalent via
    `runpy.run_path(path, run_name="__main__")`, which executes the file's
    `__main__` block for real, so a wrapper that silently stopped going
    through the shared engine makes the patched message disappear."""

    def test_core_fix_reaches_all_providers(self) -> None:
        import seo_cycle_core.health as health_core

        empty_dir = pathlib.Path(tempfile.mkdtemp(prefix="health-fix-propagation-"))
        self.addCleanup(lambda: shutil.rmtree(empty_dir, ignore_errors=True))

        with mock.patch.object(health_core, "MISSING_CONFIG_MSG", "PATCHED-BY-CORE-FIX: {cwd}"):
            for script in ALL_SEVEN_SCRIPTS:
                with self.subTest(script=script):
                    old_argv, old_cwd = sys.argv, pathlib.Path.cwd()
                    stderr = io.StringIO()
                    try:
                        sys.argv = [script]
                        os.chdir(empty_dir)
                        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as exc:
                            runpy.run_path(str(SCRIPTS / script), run_name="__main__")
                    finally:
                        sys.argv = old_argv
                        os.chdir(old_cwd)
                    self.assertEqual(exc.exception.code, 2)
                    self.assertIn("PATCHED-BY-CORE-FIX", stderr.getvalue(),
                                  f"{script} did not see the core patch — it is not going through "
                                  "the shared engine (the exact v2.0.2 failure shape)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
