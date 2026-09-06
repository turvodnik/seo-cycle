#!/usr/bin/env python3
"""Мост `ads.ledger_record()` → подпроцесс `usage-ledger.py record` → реальная
строка в `seo/usage/usage-ledger.jsonl` (независимый гейт T-066, круг 4).

До этого теста ни один тест сюиты не проверял этот путь целиком: везде
подменялась сама функция `ledger_record` (`mock.patch.object(..., "ledger_record")`
в `test_ads_fetch_f13.py`/`test_ads_apply_f13.py`), так что проверялся ПОРЯДОК
вызова заглушки относительно `live_fetch()`/`apply_direct()`, а не факт, что
запись реально ложится в журнал, и не возвращаемое значение, ради которого
`ledger_record()` переделали в bool в круге 2 (T-066 R-2). Это и есть корень
R3-3 — почему write-ahead без проверки возврата пережил два гейта незамеченным.

Никакого мока самой `ledger_record` здесь нет — вызывается настоящая функция
с временным `project_root` (`seo-cycle.yaml` + пустой `seo/usage/`, как
ожидает `usage-ledger.py`)."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import stat
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core import ads  # noqa: E402 (sys.path must be set first)

CFG = (
    "project:\n  name: ads-ledger-bridge-test\n  url: https://example.com\n"
    "governance:\n  budget_policy:\n    monthly_total_usd_cap: 500\n"
    "    monthly_paid_api_usd_cap: 90\n"
)


class LedgerRecordRealSubprocessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = pathlib.Path(tempfile.mkdtemp(prefix="seo-ads-ledger-bridge-"))
        self.addCleanup(lambda: shutil.rmtree(self.project_root, ignore_errors=True))
        (self.project_root / "seo-cycle.yaml").write_text(CFG, encoding="utf-8")

    def test_real_call_writes_a_jsonl_line_and_returns_true(self) -> None:
        ok = ads.ledger_record(self.project_root, "yandex_direct", requests=3,
                               note="bridge test: real write")
        self.assertTrue(ok, "ledger_record() обязан вернуть True, когда запись реально удалась")

        ledger_path = self.project_root / "seo" / "usage" / "usage-ledger.jsonl"
        self.assertTrue(ledger_path.exists(), "usage-ledger.py record обязан создать JSONL-файл")
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1, "ровно одна строка на один вызов ledger_record()")
        record = json.loads(lines[0])
        self.assertEqual(record["service"], "yandex_direct")
        self.assertEqual(record["metrics"].get("requests"), 3.0)
        self.assertEqual(record["note"], "bridge test: real write")

    def test_write_failure_on_readonly_project_returns_false(self) -> None:
        """Второй случай: запись реально не может состояться (директория
        только на чтение) — возврат обязан быть False, а не тихое True."""
        usage_dir = self.project_root / "seo" / "usage"
        usage_dir.mkdir(parents=True)
        original_mode = usage_dir.stat().st_mode
        os.chmod(usage_dir, stat.S_IREAD | stat.S_IEXEC)
        self.addCleanup(os.chmod, usage_dir, original_mode)
        try:
            ok = ads.ledger_record(self.project_root, "yandex_direct", requests=3,
                                   note="bridge test: should fail")
        finally:
            os.chmod(usage_dir, original_mode)
        self.assertFalse(ok, "запись в read-only каталог обязана вернуть False, а не тихий успех")

    def test_broken_argv_makes_the_bridge_fail(self) -> None:
        """Мутация: сломай argv подпроцесса (несуществующая подкоманда) —
        этот тест обязан покраснеть, если кто-то восстановит старое поведение
        (отброшенный returncode)."""
        script = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "usage-ledger.py"
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(script), "not-a-real-command", "--service", "yandex_direct",
             "--requests", "1"],
            cwd=self.project_root, text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(proc.returncode, 0, "неверная подкоманда обязана давать ненулевой rc")


if __name__ == "__main__":
    unittest.main()
