#!/usr/bin/env python3
"""T-062: a provider switched off in the project config is not probed.

Regression history: v2.0.2 fixed "pulse probes the source of a disabled
engine" in `pulse.py` only; the seven hand-copied `*-health.py` never got
the fix. T-053 moved their skeleton into `seo_cycle_core/health.py` (pure
refactor, byte-for-byte). This test proves the BEHAVIOUR that refactor
prepared for:

1. Every provider whose config switch is explicitly off writes a report with
   status `disabled_in_config`, touches no network (git/curl PATH spies +
   a `sitecustomize` socket spy — the same shape as the installer tests),
   and never calls the wrapper's `build_report` (no credential fields in
   the output). Exit code 0 — "report produced", same rung of the ladder
   as `partner_limited`/`needs_credentials`.
2. Golden fixtures `tests/fixtures/health/<provider>-disabled.*` pin the
   new state's exact output so it cannot drift silently.
3. The gate lives in the core and REACHES all seven — proven the only way
   the T-053 gate accepted: by running each wrapper for real
   (`runpy.run_path(..., run_name="__main__")` / a subprocess), never by
   importing a function. Patching the core check to a no-op makes the
   marker disappear for all seven; if a wrapper stopped going through the
   shared engine, this test would not notice the patch — and that is
   exactly the v2.0.2 failure shape the assertion is written against.

Config-switch semantics deliberately mirror `pulse.py`: there, an engine
is skipped when its flag is falsy (`engines.py:15`, `if enabled`); here, a
provider is skipped when its switch key is present AND falsy. A missing
key means "no signal" and the wrapper runs exactly as before — which is
what keeps the 24 pre-existing goldens byte-identical.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import runpy
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

# Works both under `unittest discover -s tests` (tests/ already on sys.path)
# and `python -m unittest tests.<module>` (it is not).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_health_core import (  # noqa: E402
    ALL_SEVEN_SCRIPTS,
    BASE_CFG_RU,
    FIXTURES,
    SCRIPTS,
    clean_env,
    normalize,
    run_script,
)

sys.path.insert(0, str(SCRIPTS))

DISABLED_STATUS = "disabled_in_config"

# script -> (provider slug used in fixture names, dotted config key the
# wrapper declares, YAML snippet that switches it off)
DISABLED_CASES: dict[str, tuple[str, str, str]] = {
    "gbp-health.py": ("gbp", "sources.google_business_profile.enabled",
                      "sources:\n  google_business_profile:\n    enabled: false\n"),
    "google-ads-health.py": ("google-ads", "ads.google_ads.enabled",
                             "ads:\n  google_ads:\n    enabled: false\n"),
    "merchant-health.py": ("merchant", "sources.google_merchant.enabled",
                           "sources:\n  google_merchant:\n    enabled: false\n"),
    "yandex-direct-health.py": ("yandex-direct", "ads.yandex_direct.enabled",
                                "ads:\n  yandex_direct:\n    enabled: false\n"),
    "yandex-business-health.py": ("yandex-business", "sources.yandex_business_maps.enabled",
                                  "sources:\n  yandex_business_maps:\n    enabled: false\n"),
    "notebooklm-health.py": ("notebooklm", "notebooklm_provider.enabled",
                             "notebooklm_provider:\n  enabled: false\n"),
    "perplexity-health.py": ("perplexity", "perplexity_provider.enabled",
                             "perplexity_provider:\n  enabled: false\n"),
}
assert set(DISABLED_CASES) == set(ALL_SEVEN_SCRIPTS)

# Fields a wrapper's own build_report emits and the core's disabled report
# must NOT — their presence means the wrapper was consulted after all.
WRAPPER_ONLY_MARKERS = ("needs_credentials", "env_names", "partner_limited",
                        "degraded_source", "fallback_required", "cache_policy")

SITECUSTOMIZE = textwrap.dedent(
    """
    # Socket spy for T-062: any attempt to resolve or connect is logged and
    # refused. Injected via PYTHONPATH into the health-script subprocess.
    import os, socket

    _LOG = os.environ["HEALTH_NET_SPY_LOG"]

    def _log(kind, args):
        with open(_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{kind} {args!r}\\n")
        raise OSError(f"network refused by T-062 spy: {kind}")

    socket.getaddrinfo = lambda *a, **k: _log("getaddrinfo", a)
    socket.create_connection = lambda *a, **k: _log("create_connection", a)
    socket.socket.connect = lambda self, *a, **k: _log("connect", a)
    socket.socket.connect_ex = lambda self, *a, **k: _log("connect_ex", a)
    """
)


class NetworkSpy:
    """PATH shims for `git`/`curl` + a `sitecustomize` socket spy, all
    writing to one log. `calls()` is empty iff nothing touched the network
    or those binaries."""

    def __init__(self, root: pathlib.Path) -> None:
        self.log = root / "net-spy.log"
        self.bin = root / "spy-bin"
        self.site = root / "spy-site"
        self.bin.mkdir()
        self.site.mkdir()
        for name in ("git", "curl"):
            shim = self.bin / name
            shim.write_text(f'#!/bin/sh\necho "{name} $*" >> "{self.log}"\nexit 7\n', encoding="utf-8")
            shim.chmod(0o755)
        (self.site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")

    def env(self, base: dict[str, str]) -> dict[str, str]:
        env = dict(base)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["PYTHONPATH"] = f"{self.site}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(self.site)
        env["HEALTH_NET_SPY_LOG"] = str(self.log)
        return env

    def calls(self) -> str:
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""


class DisabledProviderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(tempfile.mkdtemp(prefix="health-disabled-")).resolve()
        cls.spy = NetworkSpy(cls.root)
        cls.projects: dict[str, pathlib.Path] = {}
        for script, (slug, _key, snippet) in DISABLED_CASES.items():
            project = cls.root / slug
            project.mkdir()
            (project / "seo-cycle.yaml").write_text(BASE_CFG_RU + snippet, encoding="utf-8")
            cls.projects[script] = project

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.root, ignore_errors=True)

    def _run(self, script: str, args: list[str]) -> tuple[int, str, str]:
        project = self.projects[script]
        return run_script(script, [str(project / "seo-cycle.yaml"), *args], project, self.spy.env(clean_env()))

    def test_spy_is_not_blind(self) -> None:
        """A spy that logs nothing proves nothing unless it is shown to
        catch a real attempt — negative control for criterion 1."""
        probe = "import socket; socket.create_connection(('127.0.0.1', 9))"
        proc = subprocess.run([sys.executable, "-c", probe], env=self.spy.env(clean_env()),
                              text=True, capture_output=True, check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("create_connection", self.spy.calls())
        proc = subprocess.run(["curl", "http://127.0.0.1:9/"], env=self.spy.env(clean_env()),
                              text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 7)
        self.assertIn("curl http://127.0.0.1:9/", self.spy.calls())
        self.spy.log.unlink()

    def test_disabled_provider_is_not_probed(self) -> None:
        for script, (slug, key, _snippet) in DISABLED_CASES.items():
            with self.subTest(script=script):
                if self.spy.log.exists():
                    self.spy.log.unlink()
                project = self.projects[script]
                setup_dir = project / "seo" / "setup"
                shutil.rmtree(setup_dir, ignore_errors=True)

                rc_md, out_md, err_md = self._run(script, ["--format", "md"])
                rc_json, out_json, err_json = self._run(script, ["--format", "json"])
                rc_w, out_w, err_w = self._run(script, ["--write", "--format", "md"])

                self.assertEqual(self.spy.calls(), "", f"{script} touched the network/git/curl while disabled")
                self.assertEqual((rc_md, rc_json, rc_w), (0, 0, 0), (err_md, err_json, err_w))
                self.assertEqual((err_md, err_json, err_w), ("", "", ""))
                self.assertIn(DISABLED_STATUS, out_md)
                self.assertIn(key, out_md)
                report = json.loads(out_json)
                self.assertEqual(report["status"], DISABLED_STATUS)
                self.assertEqual(report["config_key"], key)
                for marker in WRAPPER_ONLY_MARKERS:
                    self.assertNotIn(marker, out_md, f"{script}: wrapper build_report ran while disabled")
                    self.assertNotIn(marker, out_json, f"{script}: wrapper build_report ran while disabled")

                # The bundle is written under the provider's own paths, both
                # halves carry the disabled status, and nothing else appears.
                written = sorted(p.name for p in setup_dir.iterdir())
                self.assertEqual(written, sorted([
                    f"{slug}-health.md", f"{slug}-health.json",
                    f"latest-{slug}-health.md", f"latest-{slug}-health.json",
                ]))
                self.assertIn(DISABLED_STATUS, (setup_dir / f"{slug}-health.md").read_text(encoding="utf-8"))
                self.assertEqual(json.loads((setup_dir / f"{slug}-health.json").read_text(encoding="utf-8"))["status"],
                                 DISABLED_STATUS)
                shutil.rmtree(setup_dir, ignore_errors=True)

    def test_disabled_goldens(self) -> None:
        """Pins the exact disabled-state output (md, json, --write bundle,
        stdout of --write) per provider, normalized like the T-053 goldens."""
        for script, (slug, _key, _snippet) in DISABLED_CASES.items():
            with self.subTest(script=script):
                project = self.projects[script]
                setup_dir = project / "seo" / "setup"
                shutil.rmtree(setup_dir, ignore_errors=True)
                prefix = f"{slug}-disabled"

                _rc, out_md, _err = self._run(script, ["--format", "md"])
                self.assertEqual(normalize(out_md, self.root), (FIXTURES / f"{prefix}.md").read_text(encoding="utf-8"))
                _rc, out_json, _err = self._run(script, ["--format", "json"])
                self.assertEqual(normalize(out_json, self.root), (FIXTURES / f"{prefix}.json").read_text(encoding="utf-8"))

                _rc, out_w, _err = self._run(script, ["--write", "--format", "md"])
                bundle = {p.name: normalize(p.read_text(encoding="utf-8"), self.root) for p in sorted(setup_dir.iterdir())}
                golden = json.loads((FIXTURES / f"{prefix}-write.json").read_text(encoding="utf-8"))
                self.assertEqual(bundle, golden["bundle"])
                self.assertEqual(normalize(out_w, self.root), golden["stdout"])
                shutil.rmtree(setup_dir, ignore_errors=True)

    def test_disabled_gate_reaches_all_seven(self) -> None:
        """Negative control for criterion 3: neutralize the ONE check in the
        core and run every wrapper for real via `runpy` — the disabled
        marker must vanish for all seven. A wrapper that stopped routing
        through the core would keep (or lose) the marker regardless of the
        patch; the paired positive run above catches that side."""
        import seo_cycle_core.health as health_core

        def run_wrapper(script: str) -> str:
            project = self.projects[script]
            old_argv, old_cwd = sys.argv, pathlib.Path.cwd()
            stdout = io.StringIO()
            try:
                sys.argv = [script, str(project / "seo-cycle.yaml"), "--format", "json"]
                os.chdir(project)
                with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as exc:
                    runpy.run_path(str(SCRIPTS / script), run_name="__main__")
            finally:
                sys.argv = old_argv
                os.chdir(old_cwd)
            self.assertEqual(exc.exception.code, 0)
            return stdout.getvalue()

        for script in ALL_SEVEN_SCRIPTS:
            with self.subTest(script=script, core_check="real"):
                self.assertIn(DISABLED_STATUS, run_wrapper(script))
            with self.subTest(script=script, core_check="neutralized"):
                with mock.patch.object(health_core, "disabled_config_key", lambda cfg, keys: None):
                    self.assertNotIn(DISABLED_STATUS, run_wrapper(script),
                                     f"{script} still reports disabled with the core check removed — "
                                     "the gate is not coming from the shared engine")


if __name__ == "__main__":
    unittest.main(verbosity=2)
