#!/usr/bin/env python3
"""Collect/cache Perplexity evidence without storing passwords or using paid API by default."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.providers import perplexity_health
from seo_cycle_core.source_artifacts import (
    compact_text,
    extract_urls,
    make_vector_record,
    read_cached_distillate,
    stable_cache_key,
    utc_now_iso,
    write_source_artifacts,
)


DEFAULT_PROMPT_TEMPLATE = """Ты работаешь как SEO/AEO/GEO research analyst.

Тема: {topic}
Регион: {region}
Язык: {language}

Собери evidence-backed вывод:
1. keyword groups и long-tail;
2. интенты и под-интенты;
3. сущности, атрибуты, бренды, материалы, размеры, коммерческие факторы;
4. вопросы для Answer Units и FAQ;
5. конкурирующие page formats;
6. источники/цитаты, которые можно проверить.

Ответ верни структурно: Summary, Keyword groups, Intents, Entities, Questions, Source-backed notes, Risks.
Не придумывай источники. Если данных нет, напиши unknown.
"""


def read_optional_text(path: str | None) -> str | None:
    if not path:
        return None
    return pathlib.Path(path).expanduser().read_text(encoding="utf-8")


def build_prompt(topic: str, region: str, language: str, custom_prompt: str | None) -> str:
    if custom_prompt:
        return custom_prompt.format(topic=topic, region=region, language=language)
    return DEFAULT_PROMPT_TEMPLATE.format(topic=topic, region=region, language=language)


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    topic = args.topic
    region = args.region or nested_get(cfg, "locale.country") or "global"
    language = args.language or nested_get(cfg, "locale.language") or "ru"
    prompt_version = args.prompt_version
    mode = args.mode
    prompt = build_prompt(topic, region, language, read_optional_text(args.prompt_file) or args.prompt)
    cache_key = stable_cache_key(
        {
            "provider": "perplexity",
            "topic": topic,
            "region": region,
            "language": language,
            "prompt_version": prompt_version,
            "mode": mode,
            "prompt": prompt,
        },
        label=topic,
    )
    cached = None if args.refresh else read_cached_distillate(project_root, "perplexity", cache_key)
    if cached:
        return {
            "provider": "perplexity",
            "status": "cache_hit",
            "generated_at": utc_now_iso(),
            "cache_key": cache_key,
            "topic": topic,
            "region": region,
            "language": language,
            "mode": mode,
            "prompt_version": prompt_version,
            "distillate": cached,
            "writes_to_site": False,
            "paid_api_used": False,
        }

    app_paths = [pathlib.Path(path).expanduser() for path in args.app_path] if args.app_path else None
    health = perplexity_health(app_paths=app_paths, browser_available=args.browser_available)
    raw_text = read_optional_text(args.raw_file)
    if args.stdin_raw:
        raw_text = sys.stdin.read()

    if raw_text:
        status = "ready"
        summary = compact_text(raw_text, max_chars=args.max_distillate_chars)
        citations = extract_urls(raw_text)
        raw_payload = {
            "provider": "perplexity",
            "status": status,
            "collected_at": utc_now_iso(),
            "topic": topic,
            "region": region,
            "language": language,
            "mode": mode,
            "prompt_version": prompt_version,
            "prompt": prompt,
            "response_text": raw_text,
        }
        distillate_payload = {
            "provider": "perplexity",
            "status": status,
            "cache_key": cache_key,
            "topic": topic,
            "region": region,
            "language": language,
            "mode": mode,
            "prompt_version": prompt_version,
            "summary": summary,
            "citations": citations,
            "source_policy": "Use distillate and citations downstream; keep raw out of LLM context.",
        }
    else:
        status = "needs_manual_export" if health["status"] == "available" else "degraded_source"
        citations = []
        summary = "Perplexity response is not collected yet. Use the prompt packet in persistent browser/app mode, then rerun with --raw-file or --stdin-raw."
        raw_payload = {
            "provider": "perplexity",
            "status": status,
            "created_at": utc_now_iso(),
            "topic": topic,
            "region": region,
            "language": language,
            "mode": mode,
            "prompt_version": prompt_version,
            "prompt": prompt,
            "health": health,
            "response_text": None,
        }
        distillate_payload = {
            "provider": "perplexity",
            "status": status,
            "cache_key": cache_key,
            "topic": topic,
            "region": region,
            "language": language,
            "mode": mode,
            "prompt_version": prompt_version,
            "summary": summary,
            "citations": citations,
            "prompt_packet": prompt,
            "fallback": "Continue with Codex/Antigravity/NotebookLM until Perplexity export is available.",
            "source_policy": "No paid API call was made.",
        }

    markdown = render_markdown(distillate_payload)
    vector_record = make_vector_record(
        provider="perplexity",
        cache_key=cache_key,
        topic=topic,
        region=str(region),
        mode=mode,
        status=status,
        summary=summary[:1000],
        citations=citations,
        metadata={"language": language, "prompt_version": prompt_version, "paid_api_used": False},
    )
    paths: dict[str, str] = {}
    if args.write:
        paths = write_source_artifacts(
            project_root,
            "perplexity",
            cache_key,
            raw_payload=raw_payload,
            distillate_markdown=markdown,
            distillate_payload=distillate_payload,
            vector_record=vector_record,
        )

    return {
        "provider": "perplexity",
        "status": status,
        "generated_at": utc_now_iso(),
        "cache_key": cache_key,
        "topic": topic,
        "region": region,
        "language": language,
        "mode": mode,
        "prompt_version": prompt_version,
        "health": health,
        "distillate": distillate_payload,
        "paths": paths,
        "writes_to_site": False,
        "paid_api_used": False,
    }


def render_markdown(distillate: dict[str, Any]) -> str:
    lines = [
        "# Perplexity Evidence Distillate",
        "",
        f"- Topic: {distillate['topic']}",
        f"- Region: {distillate['region']}",
        f"- Language: {distillate['language']}",
        f"- Status: `{distillate['status']}`",
        f"- Cache key: `{distillate['cache_key']}`",
        "",
        "## Summary",
        distillate.get("summary") or "",
        "",
        "## Citations",
    ]
    citations = distillate.get("citations") or []
    lines.extend(f"- {url}" for url in citations) if citations else lines.append("- none")
    if distillate.get("prompt_packet"):
        lines.extend(["", "## Prompt Packet", "```text", distillate["prompt_packet"], "```"])
    lines.extend(["", "## Source Policy", distillate.get("source_policy", "Use distillate only downstream.")])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--topic", required=True, help="Research topic/query.")
    parser.add_argument("--region", help="Target country/region. Defaults to config locale.country.")
    parser.add_argument("--language", help="Target language. Defaults to config locale.language.")
    parser.add_argument("--mode", choices=("persistent_browser", "app_detected", "manual_browser", "api_optional"), default="persistent_browser")
    parser.add_argument("--prompt-version", default="v1")
    parser.add_argument("--prompt", help="Custom prompt template. May use {topic}, {region}, {language}.")
    parser.add_argument("--prompt-file", help="Custom prompt template file.")
    parser.add_argument("--raw-file", help="Perplexity exported/raw response text to cache.")
    parser.add_argument("--stdin-raw", action="store_true", help="Read Perplexity response text from stdin.")
    parser.add_argument("--browser-available", action="store_true", help="Mark persistent browser/app session as available.")
    parser.add_argument("--app-path", action="append", default=[], help="Additional Perplexity.app path to test.")
    parser.add_argument("--max-distillate-chars", type=int, default=6000)
    parser.add_argument("--refresh", action="store_true", help="Ignore existing distillate cache.")
    parser.add_argument("--write", action="store_true", help="Write raw/distillate/vector artifacts.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    if args.config:
        cfg_path = pathlib.Path(args.config).expanduser().resolve()
    else:
        found = find_config(pathlib.Path.cwd())
        if not found:
            print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
            return 2
        cfg_path = found.resolve()
    if not cfg_path.exists():
        print(f"ERROR: {cfg_path} not found", file=sys.stderr)
        return 2

    report = build_report(cfg_path, args)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report["distillate"]), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
