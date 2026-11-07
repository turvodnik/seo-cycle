#!/usr/bin/env python3
"""draft-quality-gate enforces the project rules from seo-cycle.yaml (3.1.0).

Before 3.1.0 a 30-word draft full of «лучший/уникальный», with an image
without alt and no `fact_check_log`, passed the gate with zero findings —
although `skills/seo-writing/SKILL.md` called these publication blockers and
the config template carried the thresholds. These tests run the real CLI
(as `seo-cycle loop` does) inside a temp project.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
GATE = SCRIPTS / "draft-quality-gate.py"
LOOP = SCRIPTS / "loop-runner.py"
TEMPLATE = ROOT / "config" / "project.template.yaml"

BAD_DRAFT = """---
title: Как выбрать минвату
---
# Как выбрать минвату

Мы предлагаем уникальный, лучший и качественный ассортимент — широкий выбор, индивидуальный подход!

## Плотность

Плотность минваты бывает разной. ![](photo.webp)

Source: где-то в интернете.
"""


def clean_draft(words: int = 1600) -> str:
    filler = " ".join(f"Плита{i % 7} держит форму при плотности {30 + i % 50} кг/м³." for i in range(words // 7 + 1))
    links = " ".join(f"[раздел {i}](/catalog/section-{i}/)" for i in range(5))
    return f"""---
title: Как выбрать минвату для каркасной стены
page_type: Guide
fact_check_log:
  - claim: "Плотность фасадной минваты — от 80 кг/м³"
    source: "ГОСТ 9573-2012"
    url: "https://example.com/gost"
    verdict: достоверно
    checked: 2026-05-28
---
# Как выбрать минвату для каркасной стены

![Плита минеральной ваты в разрезе каркаса](/img/cut.webp "hero")

## Плотность

![Монтаж плиты между стойками каркаса с шагом 600 мм](/img/frame.webp)
*Плиту ставят враспор между стойками.*

{filler}

![Слои стены: пароизоляция, утеплитель, ветрозащита](/img/layers.webp)
*Пирог стены снаружи внутрь.*

Ссылки по теме: {links}. Source: https://example.com/spec
"""


@unittest.skipIf(yaml is None, "PyYAML is required")
class DraftGateProjectRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="draft-gate-rules-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        self.cfg["project"]["name"] = "Строймаркет Север"
        self.cfg["project"]["domain"] = "stroy-sever.test"
        # config lives in .claude/ — the pre-3.1 lookup (package_project_root +
        # find_config) would not find it from a draft three levels down
        self.cfg_path = self.tmp / ".claude" / "seo-cycle.yaml"
        self.write_config()
        self.drafts = self.tmp / "seo" / "research-package" / "drafts"
        self.drafts.mkdir(parents=True)
        self.outline = self.tmp / "outline.json"
        self.outline.write_text(json.dumps({"page": {"page_type": "Guide"}, "sections": [], "internal_links": [], "faq": []}),
                                encoding="utf-8")

    def write_config(self) -> None:
        self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg_path.write_text(yaml.safe_dump(self.cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def gate(self, text: str, *extra: str, name: str = "draft.publish.md") -> tuple[int, dict, str]:
        draft = self.drafts / name
        draft.write_text(text, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(GATE), str(draft), "--outline", str(self.outline), "--format", "json", *extra],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        report = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
        return proc.returncode, report, proc.stderr

    def ids(self, report: dict) -> list[str]:
        return [finding["id"] for finding in report.get("findings", [])]

    def test_bad_draft_fails_on_every_project_rule(self) -> None:
        rc, report, _ = self.gate(BAD_DRAFT)
        self.assertEqual(rc, 1)
        self.assertEqual(report["status"], "fail")
        ids = self.ids(report)
        for expected in ("stop_words_found", "fact_check_log_missing", "image_missing_alt",
                         "image_missing_caption", "word_count_below_min"):
            self.assertIn(expected, ids)
        self.assertIn("inline_images_below_min", ids)
        self.assertIn("internal_links_below_min", ids)
        self.assertEqual(report["summary"]["config"], str(self.cfg_path.resolve()))
        # one finding per distinct stop word, with the real line number in the message
        stop = [f for f in report["findings"] if f["id"] == "stop_words_found"]
        self.assertGreaterEqual(len(stop), 4)
        self.assertTrue(all("строки 6" in f["message"] for f in stop), stop)
        # template demo local signals («Мытищи») are skipped, not enforced
        self.assertIn("local_signals", {row["check"] for row in report["summary"]["skipped_checks"]})

    def test_clean_draft_passes_with_template_rules(self) -> None:
        rc, report, stderr = self.gate(clean_draft())
        self.assertEqual(rc, 0, (report.get("findings"), stderr))
        self.assertIn(report["status"], {"pass", "warn"})
        self.assertNotIn("error", {f["severity"] for f in report["findings"]})
        self.assertIn("word_count", report["summary"]["checks_run"])

    def test_each_rule_is_switched_off_by_its_flag(self) -> None:
        self.cfg["quality_gates"]["stop_words_check"]["enabled"] = False
        self.cfg["quality_gates"]["fact_check_log_present"]["enabled"] = False
        self.cfg["quality_gates"]["word_count_min"]["enabled"] = False
        self.cfg["images"]["alt"]["required"] = False
        self.cfg["images"]["captions"]["inline_required"] = False
        self.cfg["images"]["inline_min_per_post"] = 0
        self.cfg["content_rules"]["internal_linking"]["min_links_per_article"] = 0
        self.write_config()
        _, report, _ = self.gate(BAD_DRAFT)
        ids = set(self.ids(report))
        for gone in ("stop_words_found", "fact_check_log_missing", "word_count_below_min", "image_missing_alt",
                     "image_missing_caption", "inline_images_below_min", "internal_links_below_min"):
            self.assertNotIn(gone, ids)

    def test_fail_on_match_false_downgrades_stop_words_to_warning(self) -> None:
        self.cfg["quality_gates"]["stop_words_check"]["fail_on_match"] = False
        self.write_config()
        _, report, _ = self.gate(BAD_DRAFT)
        severities = {f["severity"] for f in report["findings"] if f["id"] == "stop_words_found"}
        self.assertEqual(severities, {"warning"})

    def test_real_local_signals_are_enforced(self) -> None:
        self.cfg["content_rules"]["local_signals"]["examples"] = ["Казань", "Татарстан"]
        self.write_config()
        _, report, _ = self.gate(clean_draft())
        self.assertIn("local_signals_below_min", self.ids(report))
        text = clean_draft().replace("## Плотность", "## Плотность для Казани\n\nДоставка по Казани и Татарстану, склад в Казани.")
        _, report, _ = self.gate(text)
        self.assertNotIn("local_signals_below_min", self.ids(report))

    def test_fact_check_log_shape_and_disputed_claims(self) -> None:
        text = clean_draft().replace(
            "    checked: 2026-05-28\n",
            "    checked: 2026-05-28\n  - claim: \"Минвата не горит вообще\"\n    source: \"форум\"\n    verdict: спорно\n  - claim: \"без источника\"\n",
        )
        rc, report, stderr = self.gate(text)
        self.assertNotIn("Traceback", stderr)
        ids = self.ids(report)
        self.assertIn("fact_check_claim_disputed", ids)
        self.assertIn("fact_check_log_incomplete", ids)
        self.assertEqual(rc, 0)  # both are warnings (evidence class), not errors

    def test_broken_frontmatter_is_a_finding_not_a_call_error(self) -> None:
        rc, report, stderr = self.gate("---\ntitle: [oops\n---\n# Текст\n\nSource: https://example.com\n")
        self.assertEqual(rc, 1, stderr)
        self.assertIn("frontmatter_invalid", self.ids(report))
        self.assertNotIn("Traceback", stderr)

    def test_broken_config_is_rc2_with_one_line_and_no_report(self) -> None:
        self.cfg_path.write_text("project: [unclosed\n", encoding="utf-8")
        draft = self.drafts / "draft.publish.md"
        draft.write_text(BAD_DRAFT, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(GATE), str(draft), "--outline", str(self.outline), "--write"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(len([line for line in proc.stderr.splitlines() if line.strip()]), 1, proc.stderr)
        self.assertFalse(draft.with_suffix(".draft-quality-gate.json").exists())

    def test_explicit_missing_config_is_rc2(self) -> None:
        rc, _, stderr = self.gate(BAD_DRAFT, "--config", str(self.tmp / "nope.yaml"))
        self.assertEqual(rc, 2)
        self.assertIn("конфиг не найден", stderr)

    def test_without_config_only_structure_is_checked(self) -> None:
        shutil.rmtree(self.cfg_path.parent)
        rc, report, _ = self.gate(BAD_DRAFT)
        self.assertEqual(rc, 0)
        self.assertEqual(report["findings"], [])
        self.assertIsNone(report["summary"]["config"])

    def test_russian_first_person_expertise_is_caught_without_config(self) -> None:
        shutil.rmtree(self.cfg_path.parent)
        rc, report, _ = self.gate("# Текст\n\nПо моему опыту, мои клиенты выбирают плиту 50 мм. Source: https://example.com\n")
        self.assertEqual(rc, 1)
        self.assertIn("unsafe_first_person_expertise", self.ids(report))
        rc, report, _ = self.gate("# Текст\n\nМы доставляем по городу за день. Source: https://example.com\n")
        self.assertNotIn("unsafe_first_person_expertise", self.ids(report))

    def make_profile(self) -> pathlib.Path:
        proc = subprocess.run([sys.executable, str(SCRIPTS / "brand-voice.py"), "init", "--write"],
                              cwd=self.tmp, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        profile = self.tmp / "seo" / "brand" / "voice.yaml"
        text = profile.read_text(encoding="utf-8")
        profile.write_text(text.replace("  preferred: {}", '  preferred: {"минвата": "минеральная вата"}'), encoding="utf-8")
        return profile

    def test_brand_voice_profile_is_checked_by_the_gate(self) -> None:
        self.make_profile()
        text = clean_draft().replace("Ссылки по теме:", "Если ты берёшь минвата - смотри ссылки по теме:")
        rc, report, stderr = self.gate(text)
        ids = self.ids(report)
        self.assertIn("voice_address_mismatch", ids, stderr)
        self.assertIn("voice_preferred_term", ids)
        self.assertIn("voice_typography_dash", ids)
        self.assertIn("brand_voice", report["summary"]["checks_run"])
        self.assertEqual(report["summary"]["brand_voice_profile"], "seo/brand/voice.yaml")
        self.assertEqual(rc, 0)  # voice findings are warnings with enforce: warn
        self.cfg["brand_voice"]["enforce"] = "error"
        self.write_config()
        rc, report, _ = self.gate(text)
        self.assertEqual(rc, 1)
        self.cfg["brand_voice"]["enabled"] = False
        self.write_config()
        _, report, _ = self.gate(text)
        self.assertNotIn("voice_address_mismatch", self.ids(report))

    def test_broken_voice_profile_is_a_config_error(self) -> None:
        profile = self.make_profile()
        profile.write_text("voice:\n  address: sir\n", encoding="utf-8")
        rc, _, stderr = self.gate(clean_draft())
        self.assertEqual(rc, 2)
        self.assertIn("профиль голоса с ошибками", stderr)
        profile.write_text("voice: [oops\n", encoding="utf-8")
        rc, _, stderr = self.gate(clean_draft())
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", stderr)

    def test_real_expert_in_brief_allows_first_person(self) -> None:
        shutil.rmtree(self.cfg_path.parent)
        self.outline.write_text(json.dumps({"sections": [], "internal_links": [], "faq": [],
                                            "eeat_guard": {"expert_author_mode": "real_expert_allowed"}}), encoding="utf-8")
        rc, report, _ = self.gate("# Текст\n\nПо моему опыту, плиту 50 мм ставят в два слоя. Source: https://example.com\n")
        self.assertEqual(rc, 0)
        finding = next(f for f in report["findings"] if f["id"] == "unsafe_first_person_expertise")
        self.assertEqual(finding["severity"], "info")

    def test_loop_hands_project_rule_findings_to_the_model(self) -> None:
        draft = self.drafts / "loop.publish.md"
        draft.write_text(BAD_DRAFT, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(LOOP), "draft", str(draft), "--outline", str(self.outline)],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout[proc.stdout.index("{"):])
        ids = {finding["id"] for finding in payload["findings"]}
        self.assertIn("stop_words_found", ids)
        self.assertIn("fact_check_log_missing", ids)
        self.assertGreaterEqual(payload["classes"]["evidence"], 1)
        self.assertTrue(any("stop_words_found" in line for line in payload["instructions"]))


if __name__ == "__main__":
    unittest.main()
