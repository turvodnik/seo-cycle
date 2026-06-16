#!/usr/bin/env python3
"""Smoke tests for the project-local Knowledge Hub."""

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
TEMPLATE = ROOT / "config" / "project.template.yaml"
KNOWLEDGE = ROOT / "scripts" / "knowledge"
WIKI_EXPORT = KNOWLEDGE / "wiki-export-project-state.py"
CONTEXT_PACK = KNOWLEDGE / "wiki-context-pack.py"
CONTENT_TASTE = KNOWLEDGE / "content-taste-gate.py"
REVIEW_CLUSTER = KNOWLEDGE / "review-cluster-plan.py"
ZVEC = KNOWLEDGE / "zvec-hybrid-index.py"
WIKI_REFRESH = KNOWLEDGE / "wiki-refresh-all.sh"


@unittest.skipIf(yaml is None, "PyYAML is required")
class KnowledgeHubTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-knowledge-hub-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        cfg["project"]["name"] = "Тестовый проект"
        cfg["project"]["domain"] = "example.test"
        cfg["project"]["brand_name_user_facing"] = "ТестБренд"
        cfg["project"]["brand_name_technical"] = "testbrand"
        (self.tmp / "seo-cycle.yaml").write_text(
            yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def run_script(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *args],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=check,
        )

    def test_wiki_export_and_context_pack_do_not_require_wordpress_env(self) -> None:
        proc = self.run_script(str(WIKI_EXPORT))
        report = json.loads(proc.stdout)

        self.assertEqual(report["status"], "ok")
        manifest_path = self.tmp / "seo" / "knowledge" / "wiki" / "project-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["project_name"], "Тестовый проект")
        self.assertIn("WordPress REST not configured", manifest["source"])
        self.assertEqual(manifest["counts"]["products"], 0)

        context = self.run_script(str(CONTEXT_PACK), "--topic", "правила проекта", "--write")
        payload = json.loads(context.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue((self.tmp / "seo" / "knowledge" / "wiki" / "context" / "latest-context-pack.md").exists())
        self.assertTrue((self.tmp / "seo" / "knowledge" / "wiki" / "context" / "latest-context-pack.json").exists())

    def test_content_taste_gate_blocks_service_terms_raw_urls_and_technical_brand(self) -> None:
        draft = self.tmp / "draft.md"
        draft.write_text(
            "Этот SEO-текст закрывает интент и ведёт на https://example.test/shop/. "
            "testbrand указан в публичном тексте.",
            encoding="utf-8",
        )

        proc = self.run_script(str(CONTENT_TASTE), str(draft), "--write", check=False)
        report = json.loads(proc.stdout)
        codes = {issue["code"] for item in report["reports"] for issue in item["issues"]}

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["decision"], "blocked")
        self.assertIn("service_terms", codes)
        self.assertIn("visible_raw_url", codes)
        self.assertIn("technical_brand_in_public_copy", codes)

    def test_review_cluster_uses_project_override_seeds(self) -> None:
        wiki_root = self.tmp / "seo" / "knowledge" / "wiki"
        state = wiki_root / "state"
        state.mkdir(parents=True, exist_ok=True)
        seeds = self.tmp / "seo" / "knowledge" / "review-cluster-seeds.json"
        seeds.write_text(
            json.dumps(
                [
                    {
                        "id": "custom-acoustic-comparison",
                        "title": "Акустические материалы: как выбрать под задачу",
                        "category_tokens": ["акустик", "acoustic"],
                        "category_include_tokens": ["акустик", "acoustic"],
                        "brand_tokens": ["бренд"],
                        "intent": "choice/comparison",
                        "page_type": "commercial_guide",
                        "mandatory_angle": "сравнивать только реальные товары и подтверждённые свойства",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (state / "categories.jsonl").write_text(
            json.dumps({"type": "product_cat", "title": "Акустические материалы", "slug": "acoustic", "url": "https://example.test/shop/acoustic/"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (state / "brands.jsonl").write_text(
            json.dumps({"type": "product_brand", "title": "Бренд", "slug": "brand", "url": "https://example.test/brand/brand/"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (state / "products.jsonl").write_text(
            "\n".join(
                [
                    json.dumps({"type": "product", "title": "Бренд акустическая плита 50 мм", "slug": "acoustic-50", "url": "https://example.test/product/acoustic-50/", "categories": ["Акустические материалы"], "brands": ["Бренд"]}, ensure_ascii=False),
                    json.dumps({"type": "product", "title": "Бренд акустическая плита 100 мм", "slug": "acoustic-100", "url": "https://example.test/product/acoustic-100/", "categories": ["Акустические материалы"], "brands": ["Бренд"]}, ensure_ascii=False),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (state / "articles.jsonl").write_text("", encoding="utf-8")

        proc = self.run_script(str(REVIEW_CLUSTER), "--write")
        report = json.loads(proc.stdout)

        self.assertEqual(report["seed_source"], "project_override")
        self.assertEqual(report["candidates"][0]["id"], "custom-acoustic-comparison")
        self.assertEqual(report["candidates"][0]["priority"], "P1")
        self.assertTrue((wiki_root / "frameworks" / "review-cluster-plan.md").exists())

    def test_wiki_refresh_and_hybrid_index_smoke(self) -> None:
        subprocess.run(
            ["bash", str(WIKI_REFRESH)],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=True,
        )
        status = json.loads((self.tmp / "seo" / "knowledge" / "zvec" / "zvec-status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "ok")
        self.assertTrue((self.tmp / "seo" / "knowledge" / "zvec" / "hybrid.sqlite").exists())

        search = self.run_script(str(ZVEC), "--query", "ТестБренд", "--limit", "5")
        result = json.loads(search.stdout)
        self.assertEqual(result["query"], "ТестБренд")


if __name__ == "__main__":
    unittest.main(verbosity=2)
