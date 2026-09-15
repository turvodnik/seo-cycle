#!/usr/bin/env python3
"""Whitelist/docstring consistency for the dashboard command panel (T-104).

webapp.py's module docstring and inline COMMANDS comment used to claim
"nothing --live" while three commands (`yml-feed`, `site-crawl`,
`link-liveness`) shipped with `--live` in their args, grouped under an
ordinary-looking label ("Данные"/"Техничка") indistinguishable from the
offline commands around them. This test makes the docstring's claim and the
whitelist's actual contents check each other mechanically instead of by
memory at review time.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("webapp_whitelist", SCRIPTS / "webapp.py")
webapp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webapp)


class CommandWhitelistConsistencyTest(unittest.TestCase):
    def test_every_live_command_is_in_live_group(self) -> None:
        for key, spec_ in webapp.COMMANDS.items():
            if "--live" in spec_["args"]:
                self.assertEqual(
                    spec_["group"], webapp.LIVE_GROUP,
                    f"command '{key}' passes --live but is not grouped under LIVE_GROUP — "
                    "it would look like an ordinary offline command in the dashboard UI",
                )
            else:
                self.assertNotEqual(
                    spec_["group"], webapp.LIVE_GROUP,
                    f"command '{key}' is in LIVE_GROUP but does not pass --live — "
                    "grouping and reality have drifted apart",
                )

    def test_docstring_no_longer_makes_the_false_blanket_claim(self) -> None:
        doc = webapp.__doc__ or ""
        self.assertNotIn(
            "nothing --live", doc,
            "module docstring still claims 'nothing --live' while the whitelist ships live commands",
        )

    def test_negative_control_catches_a_mislabeled_live_command(self) -> None:
        """Break it on purpose: a --live command hidden in a non-LIVE_GROUP
        group must fail the first assertion above — proves the check is not
        vacuously true."""
        fake_commands = dict(webapp.COMMANDS)
        fake_commands["fake-live"] = {"group": "Данные", "args": ["--live", "--write"]}
        with self.assertRaises(AssertionError):
            for key, spec_ in fake_commands.items():
                if "--live" in spec_["args"]:
                    self.assertEqual(spec_["group"], webapp.LIVE_GROUP, key)


if __name__ == "__main__":
    unittest.main(verbosity=2)
