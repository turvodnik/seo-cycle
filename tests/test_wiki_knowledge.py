#!/usr/bin/env python3
"""Smoke/regression tests for the knowledge/wiki subsystem (bug #1 territory)."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "scripts" / "knowledge"


def load_module(path: pathlib.Path):
    sys.path.insert(0, str(KNOWLEDGE))
    try:
        spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class WikiExportRegressionTest(unittest.TestCase):
    def test_urlparse_safe_extracts_netloc(self) -> None:
        """Regression for v1.85 bug: urlparse was undefined, NameError was
        swallowed by `except Exception` and every URL yielded ''. Domain links
        were silently never recognized."""
        module = load_module(KNOWLEDGE / "wiki-export-project-state.py")
        self.assertEqual(module.urlparse_safe("https://emwoody.ru/blog/x/"), "emwoody.ru")
        self.assertEqual(module.urlparse_safe("http://sub.site.ru:8080/p?q=1"), "sub.site.ru:8080")
        self.assertEqual(module.urlparse_safe("not a url"), "")

    def test_all_knowledge_scripts_importable(self) -> None:
        """Every wiki script must at least import cleanly (no missing names)."""
        scripts = sorted(KNOWLEDGE.glob("wiki-*.py"))
        self.assertGreater(len(scripts), 0)
        for path in scripts:
            with self.subTest(script=path.name):
                load_module(path)


if __name__ == "__main__":
    unittest.main()
