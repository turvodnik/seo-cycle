#!/usr/bin/env python3
"""T-091 round 2 (2026-09-07 review, new finding): three browser-collector
scripts (writerzen-browser-collect.py, gsc-indexing-export-browser.py,
gsc-request-indexing-browser.py) hard-coded ~/.codex/vendor/seo-cycle-node
as their Node dependency cache and ran `npm install playwright-core@latest`
into it as a silent side effect of an ordinary run — the same class of bug
as F-18 (silent pip installs), but for npm, and additionally writing into
~/.codex/vendor, which README.md there declares read-only (§3 of the global
rules: vendor storage is machine-managed, hand edits/writes are forbidden).

Two things are asserted for all three scripts:
  1. the default Node dependency cache path is under ~/.seo-cycle/ (the
     project's established working-directory location, e.g.
     ~/.seo-cycle/reports, ~/.seo-cycle/env.global), never under
     ~/.codex/vendor.
  2. a missing playwright-core is reported ("status": "missing") rather than
     silently installed, unless the caller passes the explicit opt-in flag
     --install-browser-runtime — verified by calling ensure_browser_runtime()
     directly with a fake HOME and confirming zero subprocess calls and zero
     files written when the flag is absent.
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest
import unittest.mock as mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

MODULES = [
    "writerzen-browser-collect",
    "gsc-indexing-export-browser",
    "gsc-request-indexing-browser",
]


def _load(name: str, home: pathlib.Path):
    """Import one of the browser-collector scripts fresh, with HOME
    overridden BEFORE import — DEFAULT_NODE_DEPS_DIR is computed at import
    time from pathlib.Path.home(), which reads the HOME env var."""
    with mock.patch.dict("os.environ", {"HOME": str(home)}):
        spec = importlib.util.spec_from_file_location(
            f"_t091_{name.replace('-', '_')}", SCRIPTS / f"{name}.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


class NodeDepsDirIsNotVendorTest(unittest.TestCase):
    def test_default_deps_dir_is_under_dot_seo_cycle_not_codex_vendor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="seo-cycle-home-") as home_s:
            home = pathlib.Path(home_s)
            for name in MODULES:
                mod = _load(name, home)
                default_dir = pathlib.Path(mod.DEFAULT_NODE_DEPS_DIR)
                self.assertTrue(
                    str(default_dir).startswith(str(home / ".seo-cycle")),
                    f"{name}: DEFAULT_NODE_DEPS_DIR={default_dir!r} должен быть под ~/.seo-cycle/",
                )
                self.assertNotIn(
                    ".codex/vendor", str(default_dir),
                    f"{name}: DEFAULT_NODE_DEPS_DIR всё ещё указывает в read-only ~/.codex/vendor",
                )
                self.assertNotIn(
                    ".codex" + "/" + "vendor", str(default_dir).replace("\\", "/"),
                )


class InstallRequiresExplicitConsentTest(unittest.TestCase):
    """ensure_browser_runtime() must not touch the network or the disk
    unless the caller explicitly opted in."""

    def _fake_args(self, install_browser_runtime: bool, node_deps_dir: str | None = None) -> argparse.Namespace:
        return argparse.Namespace(
            install_browser_runtime=install_browser_runtime,
            node_deps_dir=node_deps_dir,
        )

    def test_missing_runtime_without_consent_is_reported_not_installed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="seo-cycle-home-") as home_s:
            home = pathlib.Path(home_s)
            for name in MODULES:
                mod = _load(name, home)
                deps_dir = home / ".seo-cycle" / "vendor" / "seo-cycle-node"
                self.assertFalse(deps_dir.exists(), f"{name}: deps dir should not pre-exist in a fresh sandbox")

                args = self._fake_args(install_browser_runtime=False)
                with mock.patch("subprocess.run") as run_mock:
                    if name == "writerzen-browser-collect":
                        plan = {"node_deps_dir": str(deps_dir)}
                        result = mod.ensure_browser_runtime(plan, args)
                    else:
                        result = mod.ensure_browser_runtime(args)
                self.assertEqual(
                    result["status"], "missing",
                    f"{name}: без --install-browser-runtime статус должен быть 'missing', получено {result!r}",
                )
                run_mock.assert_not_called()
                self.assertFalse(
                    deps_dir.exists(),
                    f"{name}: без явного согласия деплой-каталог не должен быть создан на диске: {deps_dir}",
                )

    def test_consent_flag_triggers_install_attempt_only_then(self) -> None:
        with tempfile.TemporaryDirectory(prefix="seo-cycle-home-") as home_s:
            home = pathlib.Path(home_s)
            for name in MODULES:
                mod = _load(name, home)
                deps_dir = home / ".seo-cycle" / "vendor" / "seo-cycle-node-consent"
                args = self._fake_args(install_browser_runtime=True, node_deps_dir=str(deps_dir))
                # Simulate npm being present but the actual install call
                # intercepted (no real network access in this test).
                with mock.patch("shutil.which", return_value="/usr/bin/npm"), \
                     mock.patch("subprocess.run") as run_mock:
                    run_mock.return_value = subprocess.CompletedProcess(
                        args=["npm"], returncode=0, stdout="", stderr="",
                    )
                    if name == "writerzen-browser-collect":
                        plan = {"node_deps_dir": str(deps_dir)}
                        mod.ensure_browser_runtime(plan, args)
                    else:
                        mod.ensure_browser_runtime(args)
                run_mock.assert_called_once()
                called_cmd = run_mock.call_args[0][0]
                self.assertIn("npm", called_cmd)
                self.assertIn("install", called_cmd)
                self.assertIn(str(deps_dir), called_cmd)

    def test_real_codex_vendor_is_never_the_default_target(self) -> None:
        """Negative control: prove the OLD default (~/.codex/vendor/seo-cycle-node)
        is gone, not just moved to a second, additional default."""
        real_vendor_style = pathlib.Path.home() / ".codex" / "vendor" / "seo-cycle-node"
        with tempfile.TemporaryDirectory(prefix="seo-cycle-home-") as home_s:
            home = pathlib.Path(home_s)
            for name in MODULES:
                mod = _load(name, home)
                self.assertNotEqual(
                    pathlib.Path(mod.DEFAULT_NODE_DEPS_DIR),
                    home / ".codex" / "vendor" / "seo-cycle-node",
                    f"{name}: default deps dir must not be ~/.codex/vendor/seo-cycle-node",
                )
        del real_vendor_style  # documents the shape being rejected, not a live path check


if __name__ == "__main__":
    unittest.main()
