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


if __name__ == "__main__":
    unittest.main()
