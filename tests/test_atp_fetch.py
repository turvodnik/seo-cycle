#!/usr/bin/env python3
"""R3-2 (независимый гейт T-066, круг 4): atp-fetch.py — единственное место в
репозитории, тратящее платные кредиты (~8 за обычный запуск, по докстрингу
файла) ПОЛНОСТЬЮ голым: без гейта, без учёта, без стопа. `python3 atp-fetch.py
"фраза"` — обычный запуск с одним позиционным аргументом — списывал сразу.

Это НЕ полный учёт (полноценный `_usage.json` + governance-лимит — отдельный
пакет после тега) — только обязательный флаг `--live` перед платным вызовом,
по образцу xmlriver-source-pack.py: create_search() физически недостижим без
него, до какого-либо сетевого обращения.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("atp_fetch_r32", SCRIPTS / "atp-fetch.py")
atp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(atp)


class LiveGateTest(unittest.TestCase):
    """Мутация: убери проверку `if not args.live` перед create_search() —
    все тесты ниже, использующие мок create_search, обязаны покраснеть
    (assert_not_called провалится, потому что create_search реально вызовут)."""

    def test_plain_run_without_live_does_not_create_search(self) -> None:
        with mock.patch.object(atp, "_env_token", return_value="tok"), \
             mock.patch.object(atp, "create_search") as create_search, \
             mock.patch.object(sys, "argv", ["atp-fetch.py", "mineral wool insulation"]):
            with self.assertRaises(SystemExit) as ctx:
                atp.main()
        self.assertNotEqual(ctx.exception.code, 0)
        create_search.assert_not_called()

    def test_live_flag_allows_create_search_to_be_reached(self) -> None:
        with mock.patch.object(atp, "_env_token", return_value="tok"), \
             mock.patch.object(atp, "create_search",
                               return_value={"data": {"parent_search_id": "p1"}}) as create_search, \
             mock.patch.object(atp, "wait_completed"), \
             mock.patch.object(atp, "fetch_source", return_value=[]), \
             mock.patch.object(sys, "argv",
                               ["atp-fetch.py", "mineral wool insulation", "--live"]):
            atp.main()
        create_search.assert_called_once()

    def test_me_health_check_does_not_require_live(self) -> None:
        """--me — бесплатный health check, --live не требуется."""
        with mock.patch.object(atp, "_env_token", return_value="tok"), \
             mock.patch.object(atp, "me", return_value={"ok": True}), \
             mock.patch.object(atp, "create_search") as create_search, \
             mock.patch.object(sys, "argv", ["atp-fetch.py", "--me"]):
            atp.main()
        create_search.assert_not_called()

    def test_report_id_pull_does_not_require_live(self) -> None:
        """--report-id — бесплатный pull уже созданного отчёта, --live не
        требуется: create_search вообще не должен вызываться на этом пути."""
        with mock.patch.object(atp, "_env_token", return_value="tok"), \
             mock.patch.object(atp, "create_search") as create_search, \
             mock.patch.object(atp, "fetch_source", return_value=[]), \
             mock.patch.object(sys, "argv",
                               ["atp-fetch.py", "--report-id", "existing-parent-id"]):
            atp.main()
        create_search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
