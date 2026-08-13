"""secret-scan.py: значения ловятся, имена/плейсхолдеры — нет, значения не печатаются."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("secret_scan", ROOT / "scripts" / "secret-scan.py")
ss = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["secret_scan"] = ss
spec.loader.exec_module(ss)

FAKE_AWS = "AKIA" + "IOSFODNN7EXAMPLE"  # canonical AWS doc example  # secret-scan: allow


class SecretScanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-secret-scan-"))

    def scan(self) -> list[dict]:
        return ss.scan_tree(self.tmp, max_bytes=2_000_000)

    def test_planted_values_are_found_and_masked(self) -> None:
        (self.tmp / "config.toml").write_text(
            f'aws = "{FAKE_AWS}"\napp_password = "abcd efgh ijkl mnop qrst uvwx"\n',
            encoding="utf-8")
        findings = self.scan()
        rules = {f["rule"] for f in findings}
        self.assertIn("aws_access_key", rules)
        joined = json.dumps(findings, ensure_ascii=False)
        self.assertNotIn(FAKE_AWS, joined, "значение не должно попадать в отчёт целиком")

    def test_env_with_values_fails_but_names_only_example_passes(self) -> None:
        (self.tmp / ".env").write_text("WP_APP_PASSWORD=realvaluehere123\nEMPTY_ONE=\n", encoding="utf-8")
        (self.tmp / ".env.example").write_text("WP_APP_PASSWORD=\nSERPSTAT_API_KEY=\n", encoding="utf-8")
        findings = self.scan()
        self.assertTrue(any(f["rule"] == "env_value" and f["file"] == ".env" for f in findings), findings)
        self.assertFalse(any(f["file"] == ".env.example" for f in findings), findings)

    def test_allow_pragma_and_skip_dirs(self) -> None:
        (self.tmp / "docs.md").write_text(
            f"пример из документации: {FAKE_AWS}  <!-- secret-scan: allow -->\n", encoding="utf-8")
        junk = self.tmp / "node_modules" / "pkg"
        junk.mkdir(parents=True)
        (junk / "leak.js").write_text(f'key="{FAKE_AWS}"\n', encoding="utf-8")
        self.assertEqual(self.scan(), [])

    def test_private_key_block_detected(self) -> None:
        (self.tmp / "id_rsa_copy.txt").write_text(
            "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA...\n", encoding="utf-8")
        self.assertTrue(any(f["rule"] == "private_key" for f in self.scan()))


class FalsePositiveLedgerTest(unittest.TestCase):
    """T-021: двусторонняя сверка находок с реестром ложных срабатываний."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-secret-scan-ledger-"))
        # реалистичный ложноположительный кейс из ретро: "sk-packet" внутри слова.
        (self.tmp / "config.toml").write_text(
            'token = "task-sk-packet-not-a-real-secret-value"\n', encoding="utf-8")  # secret-scan: allow

    def scan(self) -> list[dict]:
        return ss.scan_tree(self.tmp, max_bytes=2_000_000)

    def test_ledger_suppresses_known_false_positive(self) -> None:
        findings = self.scan()
        self.assertEqual(len(findings), 1, findings)
        fp = findings[0]["fingerprint"]
        ledger = [{"id": "fp-demo", "fingerprint": fp, "scope": "*", "rule": "generic_assignment",
                   "reason": "sk-packet внутри task-packet, не секрет"}]
        active, suppressed, stale = ss.reconcile(findings, ledger)
        self.assertEqual(active, [], "покрытая находка не должна требовать разбора")
        self.assertEqual(len(suppressed), 1)
        self.assertEqual(stale, [], "запись сработала — не протухшая")

    def test_negative_control_uncovered_finding_stays_active(self) -> None:
        """Отрицательный контроль: похожая, но НЕ покрытая реестром находка обязана остаться активной."""
        findings = self.scan()
        fp = findings[0]["fingerprint"]
        wrong_ledger = [{"id": "fp-other", "fingerprint": "0" * 64, "scope": "*", "rule": "generic_assignment"}]
        active, suppressed, stale = ss.reconcile(findings, wrong_ledger)
        self.assertEqual(len(active), 1, "непокрытая находка обязана остаться в отчёте (скан краснеет)")
        self.assertEqual(suppressed, [])
        self.assertEqual(len(stale), 1, fp)

    def test_stale_entry_warns_when_nothing_matches_anymore(self) -> None:
        """Запись реестра, которая ни на что не совпала (код почистили), — протухшая."""
        active, suppressed, stale = ss.reconcile([], [{"id": "fp-dead", "fingerprint": "a" * 64, "scope": "*"}])
        self.assertEqual(active, [])
        self.assertEqual(suppressed, [])
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["id"], "fp-dead")

    def test_scope_glob_limits_suppression_to_matching_files(self) -> None:
        """Реестр не глобальный «на всё» — scope ограничивает подавление своим кодом (глоб по пути)."""
        findings = self.scan()
        fp = findings[0]["fingerprint"]
        ledger = [{"id": "fp-scoped", "fingerprint": fp, "scope": "other/**", "rule": "generic_assignment"}]
        active, suppressed, stale = ss.reconcile(findings, ledger)
        self.assertEqual(len(active), 1, "scope не совпал с файлом находки — подавлять нельзя")
        self.assertEqual(len(stale), 1)


if __name__ == "__main__":
    unittest.main()
