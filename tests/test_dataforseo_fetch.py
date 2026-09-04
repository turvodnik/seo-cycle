#!/usr/bin/env python3
"""Tests for dataforseo-fetch.py (auth, cache, budget guard, usage ledger, distill)."""

from __future__ import annotations

import base64
import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dfs_fetch", ROOT / "scripts" / "dataforseo-fetch.py")
dfs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dfs)


def volume_response(cost: float = 0.05) -> dict:
    return {
        "status_code": 20000,
        "cost": cost,
        "tasks": [{
            "status_code": 20000,
            "result": [
                {"keyword": "vata", "search_volume": 1000, "competition": "LOW", "cpc": 0.4},
                {"keyword": "vata cena", "search_volume": 2000, "competition": "HIGH", "cpc": 0.9},
            ],
        }],
    }


class AuthTest(unittest.TestCase):
    def test_ready_base64_wins(self) -> None:
        self.assertEqual(dfs.load_auth({"DATAFORSEO_API_KEY_BASE64": " abc "}), "abc")

    def test_login_password_are_encoded(self) -> None:
        got = dfs.load_auth({"DATAFORSEO_LOGIN": "u@example.com", "DATAFORSEO_PASSWORD": "p"})
        self.assertEqual(base64.b64decode(got).decode(), "u@example.com:p")

    def test_missing_credentials_exit(self) -> None:
        with mock.patch.object(pathlib.Path, "exists", return_value=False):
            with self.assertRaises(SystemExit):
                dfs.load_auth({})


class FetchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dfs-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.args = dfs.build_parser().parse_args(
            ["--out", str(self.tmp), "volume", "vata"])

    def test_cost_is_accumulated_in_usage_ledger(self) -> None:
        with mock.patch.object(dfs, "call", return_value=volume_response(0.05)) as called:
            dfs.fetch("b64", "keywords_data/google_ads/search_volume/live", {"k": 1}, self.args)
            self.assertEqual(called.call_count, 1)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["calls"], 1)
        self.assertAlmostEqual(usage["spent_usd"], 0.05)

    def test_second_identical_call_is_served_from_cache(self) -> None:
        payload = {"k": 1}
        with mock.patch.object(dfs, "call", return_value=volume_response()) as called:
            dfs.fetch("b64", "some/path", payload, self.args)
            dfs.fetch("b64", "some/path", payload, self.args)
            self.assertEqual(called.call_count, 1, "второй одинаковый запрос должен идти из кэша")
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["calls"], 1)

    def test_budget_guard_stops_before_paid_call(self) -> None:
        dfs.save_usage(self.tmp, {"month": dfs.load_usage(self.tmp)["month"],
                                  "spent_usd": 99.0, "calls": 7})
        with mock.patch.object(dfs, "call") as called:
            with self.assertRaises(SystemExit):
                dfs.fetch("b64", "some/path", {"k": 2}, self.args)
            called.assert_not_called()

    def test_force_overrides_budget_guard(self) -> None:
        dfs.save_usage(self.tmp, {"month": dfs.load_usage(self.tmp)["month"],
                                  "spent_usd": 99.0, "calls": 7})
        self.args.force = True
        with mock.patch.object(dfs, "call", return_value=volume_response(0.01)):
            dfs.fetch("b64", "some/path", {"k": 3}, self.args)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(usage["spent_usd"], 99.01)

    def test_api_error_status_exits(self) -> None:
        bad = {"status_code": 40401, "status_message": "Not Found", "tasks": []}
        with mock.patch.object(dfs, "call", return_value=bad):
            with self.assertRaises(SystemExit):
                dfs.fetch("b64", "some/path", {"k": 4}, self.args)


class DistillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dfs-md-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_volume_md_is_sorted_by_search_volume(self) -> None:
        args = dfs.build_parser().parse_args(
            ["--out", str(self.tmp), "--md", "volume", "vata", "vata cena"])
        with mock.patch.object(dfs, "call", return_value=volume_response()):
            with mock.patch("builtins.print") as printed:
                dfs.cmd_volume("b64", args)
        table = "\n".join(str(c.args[0]) for c in printed.call_args_list if c.args)
        self.assertIn("| ключ | частотность | конкуренция | CPC |", table)
        self.assertLess(table.index("vata cena"), table.index("| vata |"),
                        "строки должны идти по убыванию частотности")


if __name__ == "__main__":
    unittest.main()
