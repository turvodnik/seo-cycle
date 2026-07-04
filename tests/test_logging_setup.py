#!/usr/bin/env python3
"""Tests for seo_cycle_core.logging_setup."""

from __future__ import annotations

import datetime as dt
import logging
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seo_cycle_core.config import nested_get  # noqa: E402
from seo_cycle_core.logging_setup import log_file_path, prune_logs, setup_logging  # noqa: E402


class LoggingSetupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-logging-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def tearDown(self) -> None:
        for name in list(logging.Logger.manager.loggerDict):
            if name.startswith("seo-cycle."):
                for handler in logging.getLogger(name).handlers:
                    handler.close()
                logging.getLogger(name).handlers.clear()
                del logging.Logger.manager.loggerDict[name]

    def test_creates_dated_log_file(self) -> None:
        logger = setup_logging("unit-a", self.tmp, {})
        logger.info("hello file")
        expected = log_file_path(self.tmp, {})
        self.assertTrue(expected.exists())
        self.assertIn("hello file", expected.read_text(encoding="utf-8"))
        self.assertEqual(expected.name, f"seo-cycle-{dt.date.today().isoformat()}.log")

    def test_idempotent_setup_no_duplicate_handlers(self) -> None:
        first = setup_logging("unit-b", self.tmp, {})
        count = len(first.handlers)
        second = setup_logging("unit-b", self.tmp, {})
        self.assertIs(first, second)
        self.assertEqual(len(second.handlers), count)

    def test_disabled_via_config_writes_no_file(self) -> None:
        logger = setup_logging("unit-c", self.tmp, {"logging": {"enabled": False}})
        logger.info("no file expected")
        self.assertFalse(log_file_path(self.tmp, {}).exists())
        self.assertTrue(logger.handlers)  # stderr handler still attached

    def test_no_project_root_is_stderr_only(self) -> None:
        logger = setup_logging("unit-d")
        logger.info("stderr only")
        self.assertEqual(len([h for h in logger.handlers if isinstance(h, logging.FileHandler)]), 0)

    def test_custom_dir_and_level(self) -> None:
        cfg = {"logging": {"dir": "custom/logs", "level": "ERROR"}}
        logger = setup_logging("unit-e", self.tmp, cfg)
        logger.info("filtered out")
        logger.error("kept")
        path = log_file_path(self.tmp, cfg)
        self.assertTrue(str(path).endswith(f"custom/logs/seo-cycle-{dt.date.today().isoformat()}.log"))
        body = path.read_text(encoding="utf-8")
        self.assertNotIn("filtered out", body)
        self.assertIn("kept", body)

    def test_prune_logs_removes_old_files(self) -> None:
        log_dir = self.tmp / "seo" / "logs"
        log_dir.mkdir(parents=True)
        old = log_dir / "seo-cycle-2020-01-01.log"
        old.write_text("old", encoding="utf-8")
        fresh = log_dir / f"seo-cycle-{dt.date.today().isoformat()}.log"
        fresh.write_text("fresh", encoding="utf-8")
        removed = prune_logs(self.tmp, {}, days=30)
        self.assertEqual(removed, 1)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())


class NestedGetDefaultTest(unittest.TestCase):
    def test_returns_default_for_missing_path(self) -> None:
        self.assertEqual(nested_get({}, "a.b.c", "fallback"), "fallback")
        self.assertIsNone(nested_get({}, "a.b.c"))

    def test_returns_value_when_present(self) -> None:
        data = {"a": {"b": {"c": 7}}}
        self.assertEqual(nested_get(data, "a.b.c", "fallback"), 7)

    def test_non_dict_intermediate_returns_default(self) -> None:
        self.assertEqual(nested_get({"a": [1, 2]}, "a.b", 0), 0)


if __name__ == "__main__":
    unittest.main()
