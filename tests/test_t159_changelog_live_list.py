#!/usr/bin/env python3
"""T-159 / QA v3.0.0 F3: the `[3.0.0]` breaking-changes bullet about `--live`
must name only commands that really accept `--live`.

The released text listed `rag-query.py` there and told operators to add
`--live` to their cron; `rag query --live` is an argparse error (rc 2).
Guard: every script named in that bullet's "Затронуты:" list must contain
the literal `--live` in its source, and `rag-query.py` / `rag-index.py`
must not be listed (they gate spend through the usage ledger, no flag).
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def affected_list() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    section = text.split("## [3.0.0]", 1)[1].split("\n## [", 1)[0]
    breaking = section.split("### Ломающие изменения", 1)[1].split("\n### ", 1)[0]
    bullets = [b for b in re.split(r"\n- ", breaking) if "требуют явного `--live`" in b]
    if len(bullets) != 1:
        raise AssertionError(f"expected exactly one --live bullet, got {len(bullets)}")
    return bullets[0].split("Затронуты:", 1)[1].split("Что", 1)[0]


class ChangelogLiveListTest(unittest.TestCase):
    def test_listed_scripts_accept_live(self) -> None:
        affected = affected_list()
        names = re.findall(r"`(?:scripts/)?([\w./-]+\.(?:py|sh))", affected)
        self.assertGreaterEqual(len(names), 5, affected)
        for name in names:
            path = ROOT / "scripts" / name
            self.assertTrue(path.is_file(), f"{name}: no such script")
            self.assertTrue("--live" in path.read_text(encoding="utf-8"),
                            f"{name} is listed as requiring --live but has no such flag")

    def test_rag_scripts_not_listed_as_live(self) -> None:
        affected = affected_list()
        self.assertNotIn("rag-query.py", affected)
        self.assertNotIn("rag-index.py", affected)


if __name__ == "__main__":
    unittest.main()
