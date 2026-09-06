#!/usr/bin/env python3
"""Tests for scripts/usage-ledger.py — the SECOND, independent money stop
found by the round-2 gate (T-066 R-2). It is a live gate, not a report:
`seo_cycle_core/ads.py:ledger_preflight()` runs `usage-ledger.py check
--fail-on-block` and its exit code allows/denies a paid call in
`ads-apply.py`, `google-ads-fetch.py`, `yandex-direct-fetch.py`.

Reviewer's round-2 repro (report §R-2a): with $98 spent against a $100 cap
and a $5 estimate, a NaN/negative/corrupted spend value made the preflight
return "ok" (rc=0, call allowed) instead of "blocked". These tests reproduce
that repro and its fix behaviorally.
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

spec = importlib.util.spec_from_file_location("usage_ledger_script", SCRIPTS / "usage-ledger.py")
ul_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ul_script)


class CapRowNonFiniteTest(unittest.TestCase):
    """Reviewer's exact repro: used=NaN at cap=100 must never read as "ok"."""

    def test_nan_used_is_blocked_not_ok(self) -> None:
        row = ul_script.cap_row("paid_api", "usd", float("nan"), 100.0, estimate=5.0)
        self.assertEqual(row["status"], "blocked")

    def test_negative_used_is_blocked(self) -> None:
        row = ul_script.cap_row("paid_api", "usd", -50.0, 100.0, estimate=5.0)
        self.assertEqual(row["status"], "blocked")

    def test_infinite_used_is_blocked(self) -> None:
        row = ul_script.cap_row("paid_api", "usd", float("inf"), 100.0, estimate=5.0)
        self.assertEqual(row["status"], "blocked")

    def test_98_of_100_still_blocks_normally(self) -> None:
        """Positive control: the reviewer's legitimate case (used=98, cap=100,
        estimate=5) must still block — this is not a regression, just a
        different reason (projected > effective_cap, not non-finite input)."""
        row = ul_script.cap_row("paid_api", "usd", 98.0, 100.0, estimate=5.0)
        self.assertEqual(row["status"], "blocked")

    def test_ordinary_value_is_ok(self) -> None:
        row = ul_script.cap_row("paid_api", "usd", 10.0, 100.0, estimate=5.0)
        self.assertEqual(row["status"], "ok")

    def test_uncapped_zero_cap_is_not_blocked_by_the_finiteness_guard(self) -> None:
        """cap=0 means "no cap configured" elsewhere in this module — the new
        finite_nonneg guard must not misfire on legitimate zero values."""
        row = ul_script.cap_row("paid_api", "usd", 0.0, 0.0, estimate=0.0)
        self.assertIn(row["status"], ("uncapped",))


class UsdArgParseTest(unittest.TestCase):
    """R-2 (round 2): --usd (and siblings) were bare type=float — `record
    --usd nan` disabled the governance stop until month rollover."""

    def test_usd_nan_is_rejected_at_parse_time(self) -> None:
        with self.assertRaises(SystemExit):
            ul_script.parse_cli(["record", "--service", "dataforseo", "--usd", "nan"])

    def test_usd_negative_is_rejected_at_parse_time(self) -> None:
        with self.assertRaises(SystemExit):
            ul_script.parse_cli(["record", "--service", "dataforseo", "--usd", "-1"])

    def test_usd_ordinary_value_parses(self) -> None:
        _, _, args = ul_script.parse_cli(["record", "--service", "dataforseo", "--usd", "1.5"])
        self.assertEqual(args.usd, 1.5)


class ImportedUsageCorruptionTest(unittest.TestCase):
    """R-2 (finding "б"): a present-but-corrupt `_usage.json` used to come
    back from load_json() as `{}` — indistinguishable from "nothing spent"."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-ul-script-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.research = self.tmp / "seo" / "research" / "dataforseo"
        self.research.mkdir(parents=True)

    def test_nan_spent_usd_produces_ledger_error_not_silence(self) -> None:
        month = ul_script.current_month()
        (self.research / "_usage.json").write_text(
            json.dumps({"month": month, "spent_usd": float("nan"), "calls": 3}), encoding="utf-8")
        events = ul_script.imported_usage_events(self.tmp, month)
        self.assertTrue(any(e.get("_error") for e in events),
                         "непригодное значение обязано стать видимой ошибкой, не тихим нулём")
        self.assertFalse(any(e.get("metrics") for e in events),
                          "испорченное значение не должно попасть в сумму расхода")

    def test_corrupt_json_produces_ledger_error(self) -> None:
        month = ul_script.current_month()
        (self.research / "_usage.json").write_text("{ не json", encoding="utf-8")
        events = ul_script.imported_usage_events(self.tmp, month)
        self.assertTrue(any(e.get("_error") for e in events))

    def test_ledger_errors_force_evaluate_to_block(self) -> None:
        """End-to-end: an unreadable _usage.json must flip evaluate()'s
        overall status to blocked, not just print a warning in the report."""
        totals = {"errors": ["seo/research/dataforseo/_usage.json: corrupt"],
                  "overall": {}, "categories": {}, "services": {}, "events": 0, "imported_events": 0}
        state = {
            "totals": totals,
            "global_caps": {"monthly_total_usd_cap": 0, "monthly_paid_api_usd_cap": 0,
                            "monthly_llm_usd_cap": 0, "monthly_ads_usd_cap": 0,
                            "monthly_input_tokens_cap": 0, "monthly_output_tokens_cap": 0,
                            "require_approval_over_usd": 0},
            "service_caps": {},
        }
        evaluation = ul_script.evaluate(state)
        self.assertFalse(evaluation["allowed"])
        self.assertEqual(evaluation["status"], "blocked")

    def test_healthy_state_without_errors_is_not_blocked(self) -> None:
        """Negative control: no ledger errors, no caps configured -> allowed."""
        totals = {"errors": [], "overall": {}, "categories": {}, "services": {},
                  "events": 0, "imported_events": 0}
        state = {
            "totals": totals,
            "global_caps": {"monthly_total_usd_cap": 0, "monthly_paid_api_usd_cap": 0,
                            "monthly_llm_usd_cap": 0, "monthly_ads_usd_cap": 0,
                            "monthly_input_tokens_cap": 0, "monthly_output_tokens_cap": 0,
                            "require_approval_over_usd": 0},
            "service_caps": {},
        }
        evaluation = ul_script.evaluate(state)
        self.assertTrue(evaluation["allowed"])


class AppendRecordLockTest(unittest.TestCase):
    """ВАЖНО про эту группу (честность вместо холостого теста): append_record()
    оборачивает запись в usage_lock() для консистентности со всем остальным
    модулем (T-066 R-2), но это ЧИСТЫЙ append без предварительного чтения —
    на POSIX запись короче PIPE_BUF в файл, открытый с O_APPEND, и без лока
    интерливится крайне редко. Тест «параллельные записи не теряются» в этом
    месте оказался БЫ холостым (проходит и без блокировки в норме) — вместо
    того чтобы держать такой тест «для галочки», как уже дважды случалось в
    этом релизе, здесь только тест happy-path записи. Настоящая блокировка,
    где она доказуемо необходима (read-modify-write под _usage.json), уже
    покрыта ConcurrencyTest в test_dataforseo_fetch.py/test_spyfu_fetch.py/
    test_keyso_fetch.py."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-ul-append-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_record_is_written_correctly(self) -> None:
        ledger_path = self.tmp / "usage-ledger.jsonl"
        state = {"month": ul_script.current_month(), "ledger_path": ledger_path}
        args = mock.Mock(service="dataforseo", category=None, task="", source="", note="",
                         usd=1.5, input_tokens=0, output_tokens=0, requests=0, credits=0,
                         units=0, rows=0, browser_minutes=0, browser_pages=0,
                         content_writer=0, ai_credits=0, plagiarism_checks=0)
        ul_script.append_record(state, args)
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["metrics"]["usd"], 1.5)


class LedgerLineValidationTest(unittest.TestCase):
    """T-066 R2-1 (независимый гейт, круг 3): строки самого журнала
    `usage-ledger.jsonl` не проверялись на пригодность значения — одна
    отрицательная строка вычитала расход и снимала денежный стоп навсегда
    (репро из отчёта: A/B/C). Мутация: откати построчную проверку в
    `read_ledger_events()` до голого `if row.get("month") == month:
    rows.append(row)` — B обязан покраснеть (расход снова 8.0, allowed=True).
    """

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-ul-linevalid-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.project_root = self.tmp
        (self.project_root / "seo" / "usage").mkdir(parents=True)
        self.ledger_path = self.project_root / "seo" / "usage" / "usage-ledger.jsonl"
        self.cfg_path = self.project_root / "seo-cycle.yaml"
        self.cfg_path.write_text(
            "governance:\n"
            "  budget_policy:\n"
            "    monthly_total_usd_cap: 500\n"
            "    monthly_paid_api_usd_cap: 90\n",
            encoding="utf-8",
        )

    def _write_ledger_lines(self, *rows: dict) -> None:
        month = ul_script.current_month()
        lines = []
        for row in rows:
            row = dict(row)
            row.setdefault("month", month)
            row.setdefault("service", "spyfu")
            row.setdefault("category", "paid_api")
            lines.append(json.dumps(row))
        self.ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _rc_and_status(self) -> tuple[bool, str, float]:
        month = ul_script.current_month()
        state = ul_script.load_state(self.cfg_path, month)
        evaluation = ul_script.evaluate(state)
        usd_used = state["totals"].get("overall", {}).get("usd", 0.0)
        return evaluation["allowed"], evaluation["status"], usd_used

    def test_a_single_98_blocks_against_90_cap(self) -> None:
        self._write_ledger_lines({"metrics": {"usd": 98.0}})
        allowed, status, used = self._rc_and_status()
        self.assertFalse(allowed)
        self.assertEqual(status, "blocked")
        self.assertEqual(used, 98.0)

    def test_b_negative_second_line_must_not_lift_the_stop(self) -> None:
        self._write_ledger_lines({"metrics": {"usd": 98.0}}, {"metrics": {"usd": -90.0}})
        allowed, status, used = self._rc_and_status()
        self.assertFalse(allowed, "отрицательная строка не должна снимать денежный стоп")
        self.assertEqual(status, "blocked")

    def test_c_control_negative_month_field(self) -> None:
        month = ul_script.current_month()
        self.ledger_path.write_text(
            json.dumps({"month": [month], "service": "spyfu", "metrics": {"usd": 98.0}}) + "\n",
            encoding="utf-8",
        )
        events = ul_script.read_ledger_events(self.ledger_path, month)
        self.assertTrue(any(e.get("_error") for e in events))

    def test_bad_metrics_type_is_an_error_not_silently_dropped(self) -> None:
        month = ul_script.current_month()
        self.ledger_path.write_text(
            json.dumps({"month": month, "service": "spyfu", "metrics": [1, 2]}) + "\n",
            encoding="utf-8",
        )
        events = ul_script.read_ledger_events(self.ledger_path, month)
        self.assertEqual(len(events), 1)
        self.assertIn("_error", events[0])


if __name__ == "__main__":
    unittest.main()
