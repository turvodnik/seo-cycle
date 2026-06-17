#!/usr/bin/env python3
"""Export WordPress CPT blog articles into a project-local Obsidian vault.

The exporter is read-only for WordPress. It stores no secrets, only public/editorial
metadata that helps maintain content memory: article text, headings, internal links,
FAQ/CTA presence, content-plan mapping, and optional GSC performance snapshots.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: requests") from exc

from wiki_common import OBSIDIAN_ROOT, PROJECT_DOMAIN, PROJECT_NAME, PROJECT_SLUG, ROOT
from seo_cycle_core.reports import write_jsonl_file as write_jsonl

DEFAULT_VAULT = OBSIDIAN_ROOT


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return {**env, **os.environ}


def wp_config(env: dict[str, str]) -> tuple[str, str | None, str | None]:
    base = env.get("WP_BASE_URL") or env.get("WP_API_URL", "").split("/wp-json")[0]
    if not base:
        raise SystemExit("Missing WP_BASE_URL or WP_API_URL in environment")
    user = env.get("WP_USER") or env.get("WP_API_USERNAME")
    password = env.get("WP_APP_PASSWORD") or env.get("WP_API_PASSWORD")
    return base.rstrip("/"), user, password


def slugify_note(value: str) -> str:
    value = re.sub(r"https?://", "", value.strip().lower())
    value = re.sub(r"[^a-z0-9а-яё/_-]+", "-", value, flags=re.IGNORECASE)
    value = value.replace("/", "-").strip("-")
    return value or "untitled"


def clean_text(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value or "", flags=re.S)
    value = re.sub(r"<script.*?</script>", "", value, flags=re.S | re.I)
    value = re.sub(r"<style.*?</style>", "", value, flags=re.S | re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return html.unescape(" ".join(value.split()))


def yaml_scalar(value: Any) -> str:
    if value is None:
        return '""'
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


class ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.images: list[dict[str, str]] = []
        self.headings: list[dict[str, str]] = []
        self._heading_tag: str | None = None
        self._heading_text: list[str] = []
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k: v or "" for k, v in attrs}
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])
        if tag == "img":
            self.images.append(
                {
                    "src": attrs_dict.get("src", ""),
                    "alt": attrs_dict.get("alt", ""),
                }
            )
        if tag in {"h1", "h2", "h3", "h4"}:
            self._heading_tag = tag
            self._heading_text = []
        if tag in {"p", "li", "td", "th", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._heading_tag == tag:
            text = " ".join("".join(self._heading_text).split())
            if text:
                self.headings.append({"level": tag, "text": html.unescape(text)})
            self._heading_tag = None
            self._heading_text = []
        if tag in {"p", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._heading_tag:
            self._heading_text.append(data)
        self._parts.append(data)

    @property
    def text(self) -> str:
        return html.unescape("\n".join(line.strip() for line in "".join(self._parts).splitlines() if line.strip()))


def canonical_link(url: str) -> str:
    if not url:
        return url
    parsed = urlparse(url)
    if not parsed.netloc:
        return url
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if not normalized.endswith("/") and "." not in Path(parsed.path).name:
        normalized += "/"
    return normalized


def is_internal(url: str) -> bool:
    if url.startswith("/"):
        return True
    return PROJECT_DOMAIN in urlparse(url).netloc


def load_content_plan(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for key in ("url", "full_url", "existing_blog_url", "live_url", "canonical_url"):
                value = canonical_link(row.get(key, ""))
                if value:
                    rows[value] = row
                    if value.startswith(f"https://{PROJECT_DOMAIN}"):
                        rows[value.replace(f"https://{PROJECT_DOMAIN}", "")] = row
    return rows


def load_gsc_snapshot(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, Any]] = {}
    for cluster_id, cluster in data.get("clusters", {}).items():
        exact = cluster.get("exact_article") or {}
        url = canonical_link(exact.get("url", ""))
        if url:
            result[url] = {"cluster_id": cluster_id, **exact}
    return result


def wp_get_all(base: str, endpoint: str, auth: tuple[str, str] | None) -> list[dict[str, Any]]:
    page = 1
    records: list[dict[str, Any]] = []
    while True:
        params = {"per_page": 100, "page": page, "context": "edit" if auth else "view"}
        response = requests.get(f"{base}/wp-json/wp/v2/{endpoint}", params=params, auth=auth, timeout=45)
        if response.status_code == 400 and page > 1:
            break
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        records.extend(batch)
        total_pages = int(response.headers.get("X-WP-TotalPages", page))
        if page >= total_pages:
            break
        page += 1
    return records


def fetch_tags(base: str, ids: list[int], auth: tuple[str, str] | None) -> dict[int, str]:
    if not ids:
        return {}
    result: dict[int, str] = {}
    for chunk_start in range(0, len(ids), 100):
        chunk = ids[chunk_start : chunk_start + 100]
        response = requests.get(
            f"{base}/wp-json/wp/v2/tags",
            params={"include": ",".join(map(str, chunk)), "per_page": 100},
            auth=auth,
            timeout=30,
        )
        if response.status_code >= 400:
            continue
        for tag in response.json():
            result[int(tag["id"])] = tag.get("name", str(tag["id"]))
    return result


def frontmatter(fields: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {yaml_scalar(item)}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def render_article_note(article: dict[str, Any]) -> str:
    fm = frontmatter(
        {
            "type": "wp_blog_article",
            "project": PROJECT_SLUG,
            "wp_id": article["wp_id"],
            "status": article["status"],
            "slug": article["slug"],
            "url": article["url"],
            "modified": article["modified"],
            "cluster_id": article.get("cluster_id", ""),
            "primary_keyword": article.get("primary_keyword", ""),
            "intent": article.get("intent", ""),
            "page_type": article.get("page_type", ""),
            "gsc_clicks": article.get("gsc_clicks", 0),
            "gsc_impressions": article.get("gsc_impressions", 0),
            "gsc_position": round(float(article.get("gsc_position") or 0), 2),
            "tags": article.get("tag_names", []),
        }
    )
    headings = "\n".join(f"- {h['level']}: {h['text']}" for h in article["headings"]) or "- нет"
    internal_links = "\n".join(f"- {link}" for link in article["internal_links"]) or "- нет"
    product_links = "\n".join(f"- {link}" for link in article["product_links"]) or "- нет"
    category_links = "\n".join(f"- {link}" for link in article["category_links"]) or "- нет"
    images = "\n".join(f"- alt: {img.get('alt') or '[missing]'} | {img.get('src')}" for img in article["images"]) or "- нет"
    return f"""{fm}
# {article['title']}

## Snapshot
- URL: {article['url']}
- WordPress ID: `{article['wp_id']}`
- Status: `{article['status']}`
- Modified: `{article['modified']}`
- Words: `{article['word_count']}`
- FAQ count: `{article['faq_count']}`
- CTA chars: `{article['cta_chars']}`
- GSC 90d: `{article.get('gsc_clicks', 0)}` clicks / `{article.get('gsc_impressions', 0)}` impressions / avg position `{round(float(article.get('gsc_position') or 0), 2)}`
- Content plan: `{article.get('action', '')}`

## Intent And Cluster
- Cluster: `{article.get('cluster_id', '')}`
- Primary keyword: `{article.get('primary_keyword', '')}`
- Intent: `{article.get('intent', '')}`
- Page type: `{article.get('page_type', '')}`
- Stock category: {article.get('stock_category_url', '') or 'не привязана'}

## Headings
{headings}

## Internal Links
{internal_links}

## Product Links
{product_links}

## Category Links
{category_links}

## Images
{images}

## Text Snapshot

{article['text']}
"""


def main() -> int:
    env = load_env(ROOT / ".env")
    base, user, password = wp_config(env)
    auth = (user, password) if user and password else None
    vault = Path(os.environ.get("SEO_OBSIDIAN_VAULT", DEFAULT_VAULT))
    article_dir = vault / "Articles"
    index_dir = vault / "Indexes"
    data_dir = vault / "Data"
    for directory in (article_dir, index_dir, data_dir, vault / ".obsidian"):
        directory.mkdir(parents=True, exist_ok=True)

    content_plan = load_content_plan(ROOT / "seo" / "research-package" / "content-plan.csv")
    gsc = load_gsc_snapshot(ROOT / "seo" / "research" / "performance" / "gsc-refresh-brief-2026-06-15" / "summary.json")

    posts = wp_get_all(base, "blog", auth)
    tag_ids = sorted({int(tag_id) for post in posts for tag_id in post.get("tags", []) if str(tag_id).isdigit()})
    tag_names = fetch_tags(base, tag_ids, auth)

    articles: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    for post in posts:
        content = post.get("content", {}).get("rendered") or post.get("content", {}).get("raw") or ""
        parser = ArticleParser()
        parser.feed(content)
        parser.close()
        url = canonical_link(post.get("link", ""))
        plan = content_plan.get(url) or content_plan.get(url.replace(f"https://{PROJECT_DOMAIN}", "")) or {}
        gsc_row = gsc.get(url, {})
        internal_links = [canonical_link(link if not link.startswith("/") else f"https://{PROJECT_DOMAIN}{link}") for link in parser.links if is_internal(link)]
        product_links = [link for link in internal_links if "/shop/" in link]
        category_links = [
            link
            for link in internal_links
            if "/shop/" not in link and "/blog/" not in link
        ]
        article = {
            "wp_id": post.get("id"),
            "status": post.get("status", ""),
            "slug": post.get("slug", ""),
            "url": url,
            "title": clean_text(post.get("title", {}).get("rendered", "")),
            "modified": post.get("modified", ""),
            "headings": parser.headings,
            "images": parser.images,
            "internal_links": sorted(set(internal_links)),
            "product_links": sorted(set(product_links)),
            "category_links": sorted(set(category_links)),
            "text": parser.text,
            "word_count": len(re.findall(r"\w+", parser.text, flags=re.U)),
            "faq_count": len(post.get("acf", {}).get("faq_v_postah") or []) if isinstance(post.get("acf"), dict) else 0,
            "cta_chars": len(str(post.get("acf", {}).get("cta_text_post") or "")) if isinstance(post.get("acf"), dict) else 0,
            "tag_names": [tag_names.get(int(tag_id), str(tag_id)) for tag_id in post.get("tags", [])],
            "cluster_id": plan.get("cluster_id") or plan.get("source_cluster", ""),
            "primary_keyword": plan.get("primary_keyword", ""),
            "intent": plan.get("intent", ""),
            "page_type": plan.get("page_type", ""),
            "action": plan.get("action") or plan.get("page_action", ""),
            "stock_category_url": plan.get("stock_category_url") or plan.get("target_category", ""),
            "gsc_clicks": gsc_row.get("clicks", 0),
            "gsc_impressions": gsc_row.get("impressions", 0),
            "gsc_position": gsc_row.get("position_weighted", 0),
        }
        articles.append(article)
        for link in article["internal_links"]:
            links.append({"source": article["url"], "target": link, "source_slug": article["slug"], "target_slug": slugify_note(link)})
        (article_dir / f"{article['slug']}.md").write_text(render_article_note(article), encoding="utf-8")

    articles_sorted = sorted(articles, key=lambda item: item["slug"])
    write_jsonl(data_dir / "articles.jsonl", articles_sorted)
    write_jsonl(data_dir / "internal-links.jsonl", links)

    index_lines = [
        "# Articles Index",
        "",
        f"- Generated: `{dt.datetime.now(dt.timezone.utc).isoformat()}`",
        f"- Articles: `{len(articles_sorted)}`",
        "",
        "| Article | Status | Cluster | GSC clicks | GSC impressions | Internal links | Products | Categories |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for article in articles_sorted:
        note = f"[[Articles/{article['slug']}|{article['title']}]]"
        index_lines.append(
            f"| {note} | {article['status']} | {article.get('cluster_id', '')} | {article.get('gsc_clicks', 0)} | "
            f"{article.get('gsc_impressions', 0)} | {len(article['internal_links'])} | {len(article['product_links'])} | {len(article['category_links'])} |"
        )
    (index_dir / "articles-index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    graph_lines = ["# Internal Link Graph", ""]
    for link in sorted(links, key=lambda item: (item["source_slug"], item["target"])):
        graph_lines.append(f"- [[Articles/{link['source_slug']}]] -> {link['target']}")
    (index_dir / "internal-link-graph.md").write_text("\n".join(graph_lines) + "\n", encoding="utf-8")

    (vault / "README.md").write_text(
        f"""# {PROJECT_NAME} SEO Knowledge Vault

Project-local Obsidian-compatible vault for editorial SEO memory.

Open this folder in Obsidian:

`seo/knowledge/obsidian-vault`

Rules:
- no secrets or API keys here;
- article notes mirror WordPress CPT `blog`;
- analytics snapshots are factual and dated;
- refresh decisions must cite GSC/Yandex/source-lock evidence;
- use `Data/*.jsonl` for vector/index reuse.
""",
        encoding="utf-8",
    )
    (vault / ".obsidian" / "app.json").write_text('{"alwaysUpdateLinks":true}\n', encoding="utf-8")

    print(json.dumps({"status": "ok", "vault": str(vault), "articles": len(articles_sorted), "links": len(links)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
