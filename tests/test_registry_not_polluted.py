#!/usr/bin/env python3
"""Guard: no test in this suite may write to the REAL machine-local registry
(``~/.seo-cycle/projects-registry.yaml`` by default, see
``seo_cycle_core.registry.default_registry_path``) — T-104.

T-061 introduced two isolation mechanisms for subprocess tests that invoke
``init-project.sh``/``monthly-runner.sh`` (the only two entry points that
write the registry): ``SEO_CYCLE_SKIP_REGISTRY=1`` (skip the write
entirely) or a fake ``HOME`` (registry resolves under the fake home). Both
were applied when T-061 landed, but 15.09 the real registry on the
maintainer's machine was found polluted with three ``"MyProject"`` entries
pointing at scratchpad/tempdir paths — debris from some run, at some point,
that reached the real file. This test does not attempt to prove which run
did it (git history did not point to a specific offender still present on
``main`` — see T-104 «Результат»); it exists so a *future* regression (a
new subprocess test added without the isolation convention) is caught
immediately instead of silently accumulating in the file a human
eventually has to clean up by hand.

Method: hash the real registry (or record its absence) before and after
running every test file known to invoke ``init-project.sh`` or
``monthly-runner.sh`` as a subprocess, and assert nothing changed. This is
narrower than re-running the entire suite (which would need a recursion
guard and roughly doubles CI time for one invariant) but exercises exactly
the code paths capable of writing the registry.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.registry import default_registry_path  # noqa: E402

# Every test file that shells out to init-project.sh or monthly-runner.sh —
# the only two scripts that ever append to the registry. Grep to keep this
# list honest: `grep -rl 'init-project.sh\|monthly-runner.sh' tests`.
GUARDED_MODULES = (
    "test_registry",
    "test_init_project",
    "test_intake_wizard_tty",
)


def _hash_or_marker(path: pathlib.Path) -> str:
    if not path.exists():
        return "<absent>"
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RealMachineRegistryUntouchedTest(unittest.TestCase):
    def test_guarded_modules_do_not_touch_real_registry(self) -> None:
        real = default_registry_path()
        before = _hash_or_marker(real)

        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for name in GUARDED_MODULES:
            suite.addTests(loader.discover(start_dir=str(ROOT / "tests"), pattern=f"{name}.py"))

        # A module that fails to import becomes a _FailedTest placeholder —
        # it counts toward testsRun without running any real test body, so
        # a broken guarded module would silently pass this whole check
        # (found live while staging the negative control for this test:
        # an unrelated IndentationError made the guard report a false "ok").
        self.assertEqual(
            loader.errors, [],
            f"guarded module(s) failed to import: {loader.errors!r} — "
            "the guard did not actually exercise them",
        )

        with open(os.devnull, "w", encoding="utf-8") as devnull:
            result = unittest.TextTestRunner(verbosity=0, stream=devnull).run(suite)

        after = _hash_or_marker(real)
        self.assertEqual(
            before, after,
            "a guarded test module wrote to the REAL machine registry "
            f"({real}) — every init-project.sh/monthly-runner.sh subprocess call in "
            "tests must set SEO_CYCLE_SKIP_REGISTRY=1 or a fake HOME",
        )
        self.assertTrue(
            result.testsRun > 0,
            "no tests were discovered in GUARDED_MODULES — the module list or pattern is stale",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
