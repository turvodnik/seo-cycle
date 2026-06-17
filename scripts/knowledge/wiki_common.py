#!/usr/bin/env python3
"""Shared helpers for project-local seo-cycle Knowledge Hub scripts."""

from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import requests
except ImportError:  # pragma: no cover - only needed for live WordPress REST export
    requests = None

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from seo_cycle_core.config import find_config, load_yaml, project_root_for, rel_path  # noqa: E402
from seo_cycle_core.reports import write_jsonl_file as write_jsonl, write_sorted_json_file as write_json  # noqa: E402


def _discover_project_root() -> Path:
    env_root = os.environ.get("SEO_CYCLE_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    cwd = Path.cwd().resolve()
    config = find_config(cwd)
    if config:
        return project_root_for(config.resolve())
    return cwd


ROOT = _discover_project_root()
CONFIG_PATH = find_config(ROOT)
CONFIG = load_yaml(CONFIG_PATH) if CONFIG_PATH else {}
ENV_FILE = ROOT / ".env"


def _policy_path(key: str, default: str) -> Path:
    policy_files = CONFIG.get("policy_files", {}) if isinstance(CONFIG.get("policy_files"), dict) else {}
    return rel_path(ROOT, policy_files.get(key, default))


WIKI_ROOT = _policy_path("knowledge_wiki_root", "seo/knowledge/wiki")
OBSIDIAN_ROOT = _policy_path("knowledge_obsidian_root", "seo/knowledge/obsidian-vault")
GRAPH_CORPUS_ROOT = _policy_path("knowledge_graph_corpus", "seo/knowledge/graph-corpus")
GRAPH_ROOT = _policy_path("knowledge_graph_root", "seo/knowledge/graph")
HYBRID_INDEX_ROOT = _policy_path("knowledge_hybrid_index_root", "seo/knowledge/zvec")
project_cfg = CONFIG.get("project", {}) if isinstance(CONFIG.get("project"), dict) else {}
PROJECT_DOMAIN = str(project_cfg.get("domain") or os.environ.get("SEO_PROJECT_DOMAIN") or "example.com").strip()
PROJECT_NAME = str(project_cfg.get("name") or project_cfg.get("brand_name_user_facing") or PROJECT_DOMAIN).strip()
PROJECT_BRAND = str(project_cfg.get("brand_name_user_facing") or project_cfg.get("name") or PROJECT_DOMAIN).strip()
PROJECT_SLUG = str(project_cfg.get("brand_name_technical") or PROJECT_DOMAIN.split(".")[0] or "project").strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return {**env, **os.environ}


def wp_config(env: dict[str, str]) -> tuple[str, tuple[str, str] | None]:
    base = env.get("WP_BASE_URL") or env.get("WP_API_URL", "").split("/wp-json")[0]
    if not base:
        raise SystemExit("Missing WP_BASE_URL or WP_API_URL in .env")
    base = re.sub(r"/wp-json.*$", "", base).rstrip("/")
    user = env.get("WP_USER") or env.get("WP_API_USERNAME")
    password = (env.get("WP_APP_PASSWORD") or env.get("WP_API_PASSWORD") or "").replace(" ", "")
    auth = (user, password) if user and password else None
    return base, auth


def wp_get_all(base: str, endpoint: str, auth: tuple[str, str] | None, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if requests is None:
        raise RuntimeError("The `requests` package is required for live WordPress REST export.")
    page = 1
    records: list[dict[str, Any]] = []
    while True:
        query = {"per_page": 100, "page": page, **(params or {})}
        response = requests.get(f"{base}/wp-json/wp/v2/{endpoint}", params=query, auth=auth, timeout=60)
        if response.status_code == 400 and page > 1:
            break
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        records.extend(batch)
        total_pages = int(response.headers.get("X-WP-TotalPages", page) or page)
        if page >= total_pages:
            break
        page += 1
    return records


def ensure_wiki_tree() -> None:
    for subdir in [
        "rules",
        "state",
        "articles",
        "categories",
        "brands",
        "products",
        "reports",
        "decisions",
        "preflight",
        "context",
        "api-catalog",
        "frameworks",
        "indexes",
        "graph",
        "backlog",
        "raw",
    ]:
        (WIKI_ROOT / subdir).mkdir(parents=True, exist_ok=True)


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<script.*?</script>", "", text, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(" ".join(text.split()))


def title_from_record(record: dict[str, Any]) -> str:
    value = record.get("title") or record.get("name") or record.get("slug") or ""
    if isinstance(value, dict):
        value = value.get("raw") or value.get("rendered") or ""
    return clean_text(value)


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.netloc:
        path = url if url.startswith("/") else f"/{url}"
        return f"https://{PROJECT_DOMAIN}{path}"
    result = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if not result.endswith("/") and "." not in Path(parsed.path).name:
        result += "/"
    return result


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-z0-9а-яё/_-]+", "-", value, flags=re.I)
    return value.replace("/", "-").strip("-") or "untitled"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def frontmatter(fields: dict[str, Any]) -> str:
    def scalar(value: Any) -> str:
        if value is None:
            return '""'
        text = str(value).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{text}"'

    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {scalar(item)}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        else:
            lines.append(f"{key}: {scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


class HtmlSnapshotParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.headings: list[dict[str, str]] = []
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self._link_href: str | None = None
        self._link_parts: list[str] = []
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k: v or "" for k, v in attrs}
        if tag == "a" and attrs_dict.get("href"):
            self._link_href = attrs_dict["href"]
            self._link_parts = []
        if tag == "img":
            self.images.append({"src": attrs_dict.get("src", ""), "alt": attrs_dict.get("alt", "")})
        if tag in {"h1", "h2", "h3", "h4"}:
            self._heading_tag = tag
            self._heading_parts = []
        if tag in {"p", "li", "td", "th", "h1", "h2", "h3", "h4"}:
            self._text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._link_href is not None:
            text = " ".join("".join(self._link_parts).split())
            self.links.append({"href": self._link_href, "anchor": html.unescape(text)})
            self._link_href = None
            self._link_parts = []
        if self._heading_tag == tag:
            text = " ".join("".join(self._heading_parts).split())
            if text:
                self.headings.append({"level": tag, "text": html.unescape(text)})
            self._heading_tag = None
            self._heading_parts = []
        if tag in {"p", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._heading_tag:
            self._heading_parts.append(data)
        if self._link_href is not None:
            self._link_parts.append(data)
        self._text_parts.append(data)

    @property
    def text(self) -> str:
        return html.unescape("\n".join(line.strip() for line in "".join(self._text_parts).splitlines() if line.strip()))


def parse_html(html_value: str) -> HtmlSnapshotParser:
    parser = HtmlSnapshotParser()
    parser.feed(html_value or "")
    parser.close()
    return parser


def public_content_from_record(record: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in ("title", "content", "excerpt"):
        value = record.get(field)
        if isinstance(value, dict):
            parts.append(value.get("raw") or value.get("rendered") or "")
        else:
            parts.append(str(value or ""))
    acf = record.get("acf")
    if isinstance(acf, dict):
        parts.append(json.dumps(acf, ensure_ascii=False))
    return "\n".join(parts)
