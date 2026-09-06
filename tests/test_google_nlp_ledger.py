#!/usr/bin/env python3
"""Tests for google-nlp-audit.py's own usage ledger (T-066 R-2: the THIRD,
independent implementation of the same class the independent gate found —
`usage-<month>.json`, no shared code with dataforseo/spyfu/keyso/usage-ledger.py).

Reviewer's round-2 repro (report §R-2в):
  отрицательное used=-99999 → check_monthly_cap ПРОПУСТИЛ вызов
  битый JSON → load_usage: голый JSONDecodeError (не управляемый отказ)
  (второй гейт) исключение после платного вызова -> файла учёта нет вовсе
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("google_nlp_audit", SCRIPTS / "google-nlp-audit.py")
gnlp = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(gnlp)
except ImportError as e:
    # google-nlp-audit.py требует опциональные зависимости из extras `google`
    # (requests/beautifulsoup4/google-auth) — CI ставит только `.[dev]`, они
    # там не установлены. Пропускаем модуль целиком, а не падаем ImportError'ом
    # на уровне discovery (та же практика, что для остальных опциональных extras).
    raise unittest.SkipTest(f"google-nlp-audit.py deps missing: {e}") from e


class LoadUsageCorruptionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-gnlp-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.month = gnlp.month_key()

    def test_missing_file_is_empty_state(self) -> None:
        u = gnlp.load_usage(self.tmp, self.month)
        self.assertEqual(u["features"], {})

    def test_corrupt_json_raises_guard_error_not_bare_traceback(self) -> None:
        (self.tmp / f"usage-{self.month}.json").write_text("{ не json", encoding="utf-8")
        with self.assertRaises(gnlp.GuardError):
            gnlp.load_usage(self.tmp, self.month)

    def test_negative_feature_usage_raises_guard_error(self) -> None:
        """Точный репро гейта: used=-99999 раньше проходило int() без вопросов
        и check_monthly_cap() пропускал вызов сверх лимита."""
        (self.tmp / f"usage-{self.month}.json").write_text(
            json.dumps({"month": self.month, "features": {"analyzeEntities": -99999}}),
            encoding="utf-8")
        with self.assertRaises(gnlp.GuardError):
            gnlp.load_usage(self.tmp, self.month)

    def test_nan_feature_usage_raises_guard_error(self) -> None:
        (self.tmp / f"usage-{self.month}.json").write_text(
            json.dumps({"month": self.month, "features": {"analyzeEntities": float("nan")}}),
            encoding="utf-8")
        with self.assertRaises(gnlp.GuardError):
            gnlp.load_usage(self.tmp, self.month)

    def test_stale_month_resets_to_empty(self) -> None:
        (self.tmp / f"usage-2000-01.json").write_text(
            json.dumps({"month": "2000-01", "features": {"analyzeEntities": 500}}), encoding="utf-8")
        # запрашиваем текущий месяц — файла с таким именем нет, значит пусто
        u = gnlp.load_usage(self.tmp, self.month)
        self.assertEqual(u["features"], {})


class CheckMonthlyCapDefenseInDepthTest(unittest.TestCase):
    """check_monthly_cap() тоже проверяет значение напрямую (защита в глубину
    на случай вызова в обход load_usage())."""

    def test_negative_used_passed_directly_still_raises(self) -> None:
        config = {"GOOGLE_NLP_TOTAL_ENTITY_UNITS_CAP_PER_MONTH": "1000"}
        usage = {"month": gnlp.month_key(), "features": {"analyzeEntities": -99999}}
        with self.assertRaises(gnlp.GuardError):
            gnlp.check_monthly_cap(config, usage, "analyzeEntities", 10)

    def test_ordinary_used_within_cap_does_not_raise(self) -> None:
        config = {"GOOGLE_NLP_TOTAL_ENTITY_UNITS_CAP_PER_MONTH": "1000"}
        usage = {"month": gnlp.month_key(), "features": {"analyzeEntities": 5}}
        gnlp.check_monthly_cap(config, usage, "analyzeEntities", 10)  # не бросает

    def test_used_over_cap_raises(self) -> None:
        config = {"GOOGLE_NLP_TOTAL_ENTITY_UNITS_CAP_PER_MONTH": "10"}
        usage = {"month": gnlp.month_key(), "features": {"analyzeEntities": 8}}
        with self.assertRaises(gnlp.GuardError):
            gnlp.check_monthly_cap(config, usage, "analyzeEntities", 10)


class SaveUsageAtomicityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-gnlp-atomic-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_write_failure_leaves_no_half_file(self) -> None:
        month = gnlp.month_key()
        gnlp.save_usage(self.tmp, {"month": month, "features": {"analyzeEntities": 1}})
        with mock.patch("json.dump", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                gnlp.save_usage(self.tmp, {"month": month, "features": {"analyzeEntities": 2}})
        usage = gnlp.load_usage(self.tmp, month)
        self.assertEqual(usage["features"]["analyzeEntities"], 1)
        leftovers = [p for p in self.tmp.iterdir() if p.name.startswith(".")]
        self.assertEqual(leftovers, [])


class AnalyzeSourceF13Test(unittest.TestCase):
    """F-13 (независимый гейт, круг 2): исключение из call_feature() (сеть,
    HTTP-ошибка) раньше уходило из analyze_source() необработанным — запрос
    уже был отправлен, а файл учёта не обновлялся вовсе."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-gnlp-analyze-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.config = {"GOOGLE_NLP_CACHE_DIR": "cache", "GOOGLE_NLP_CACHE_DAYS": "30",
                       "GOOGLE_NLP_TOTAL_ENTITY_UNITS_CAP_PER_MONTH": "100000"}

    def _cache_dir(self) -> pathlib.Path:
        return self.tmp / "cache"

    def test_request_exception_still_records_units_spent(self) -> None:
        import requests
        with mock.patch.object(gnlp, "call_feature",
                               side_effect=requests.exceptions.ConnectionError("boom")):
            results = gnlp.analyze_source(
                project_root=self.tmp, source_id="https://example.com", text="hello world",
                language="en", features=["analyzeEntities"], config=self.config,
                dry_run=False, force_refresh=False, include_cache_result=False,
            )
        self.assertEqual(results[0]["status"], "api_error")
        month = gnlp.month_key()
        usage = gnlp.load_usage(self._cache_dir(), month)
        self.assertGreater(usage["features"].get("analyzeEntities", 0), 0,
                           "юниты обязаны быть учтены даже при сетевой ошибке")

    def test_successful_call_records_units_as_before(self) -> None:
        with mock.patch.object(gnlp, "call_feature", return_value={"entities": []}):
            results = gnlp.analyze_source(
                project_root=self.tmp, source_id="https://example.com", text="hello world",
                language="en", features=["analyzeEntities"], config=self.config,
                dry_run=False, force_refresh=False, include_cache_result=False,
            )
        self.assertEqual(results[0]["status"], "api_call")
        month = gnlp.month_key()
        usage = gnlp.load_usage(self._cache_dir(), month)
        self.assertGreater(usage["features"].get("analyzeEntities", 0), 0)


if __name__ == "__main__":
    unittest.main()
