#!/usr/bin/env python3
"""XMLRiver guarded SERP/Wordstat source-pack adapter.

Live HTTP is disabled by default. Without --live this script either ingests an
exported XML/JSON response or writes a secret-free request plan.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.source_artifacts import (
    compact_text,
    make_vector_record,
    stable_cache_key,
    utc_now_iso,
    write_source_artifacts,
)


PROVIDER = "xmlriver"
ENV_NAMES = ("XMLRIVER_USER_ID", "XMLRIVER_API_KEY")
PRICE_RUB_PER_1000 = {
    "basic": {"google": 25, "yandex": 25, "wordstat": 25, "yandex_search": 25},
    "pro": {"google": 20, "yandex": 20, "wordstat": 20, "yandex_search": 24},
    "mega": {"google": 15, "yandex": 15, "wordstat": 15, "yandex_search": 23},
    "giga": {"google": 12, "yandex": 12, "wordstat": 12, "yandex_search": 22},
}
OFFICIAL_DOCS = [
    "https://xmlriver.com/price.html",
    "https://xmlriver.com/api/api-connect/",
    "https://xmlriver.com/api/api-alt/",
    "https://xmlriver.com/apidoc/api-about/",
    "https://xmlriver.com/apiydoc/apiy-about/",
    "https://xmlriver.com/apiwordstatnew/apiwn-connect/",
]
ENDPOINTS = {
    "google": "https://xmlriver.com/search/xml",
    "yandex": "https://xmlriver.com/search_yandex/xml",
    "wordstat": "https://xmlriver.com/wordstat/new/json",
    "yandex_search": "https://xmlriver.com/yandex/xml",
}


def text_at(node: ET.Element | None, names: list[str]) -> str:
    if node is None:
        return ""
    for name in names:
        found = node.find(f".//{name}")
        if found is not None and found.text:
            return found.text.strip()
    return ""


def strip_xml_namespaces(root: ET.Element) -> ET.Element:
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]
    return root


def parse_serp_xml(text: str, *, top_n: int = 10) -> dict[str, Any]:
    root = strip_xml_namespaces(ET.fromstring(text))
    organic_results: list[dict[str, Any]] = []
    for idx, doc in enumerate(root.findall(".//group/doc"), start=1):
        if len(organic_results) >= top_n:
            break
        passages = [compact_text((p.text or "").strip(), max_chars=400) for p in doc.findall(".//passage") if (p.text or "").strip()]
        snippet = text_at(doc, ["extendedpassage"]) or " ".join(passages)
        organic_results.append(
            {
                "position": idx,
                "url": text_at(doc, ["url"]),
                "title": text_at(doc, ["title"]),
                "snippet": compact_text(snippet, max_chars=500),
            }
        )

    features: dict[str, Any] = {}
    zero = root.find(".//addresults/zeroposition")
    if zero is not None:
        features["zero_position"] = {
            "title": text_at(zero, ["title"]),
            "url": text_at(zero, ["url"]),
            "snippet": compact_text(text_at(zero, ["passage", "text"]), max_chars=500),
        }
    questions: list[str] = []
    for item in root.findall(".//relatedQuestions//item"):
        value = text_at(item, ["text", "question", "title"]) or (item.text or "").strip()
        if value and value not in questions:
            questions.append(value)
    if questions:
        features["related_questions"] = questions[:20]
    related_searches: list[str] = []
    for item in root.findall(".//relatedSearches//item") + root.findall(".//rs//item"):
        value = text_at(item, ["text", "query", "title"]) or (item.text or "").strip()
        if value and value not in related_searches:
            related_searches.append(value)
    if related_searches:
        features["related_searches"] = related_searches[:20]
    kg = root.find(".//knowledge_graph") or root.find(".//knowledgeGraph")
    if kg is not None:
        features["knowledge_graph"] = {
            "title": text_at(kg, ["title", "name"]),
            "url": text_at(kg, ["url"]),
            "description": compact_text(text_at(kg, ["description", "text"]), max_chars=500),
        }
    return {"organic_results": organic_results, "serp_features": features}


def iter_keyword_items(value: Any, source_group: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        candidates: list[Any] = []
        for key in ("items", "data", "phrases", "rows"):
            nested = value.get(key)
            if isinstance(nested, list):
                candidates = nested
                break
        if not candidates and any(key in value for key in ("text", "query", "phrase")):
            candidates = [value]
    elif isinstance(value, list):
        candidates = value
    else:
        candidates = []
    for item in candidates:
        if isinstance(item, str):
            rows.append({"query": item, "value": None, "source_group": source_group})
        elif isinstance(item, dict):
            query = item.get("text") or item.get("query") or item.get("phrase") or item.get("keyword") or item.get("name")
            if query:
                rows.append(
                    {
                        "query": str(query),
                        "value": item.get("value") or item.get("count") or item.get("frequency") or item.get("totalValue"),
                        "source_group": source_group,
                    }
                )
    return rows


def parse_wordstat_json(text: str) -> dict[str, Any]:
    data = json.loads(text)
    queries: list[dict[str, Any]] = []
    for group in ("associations", "popular", "words", "items"):
        if group in data:
            queries.extend(iter_keyword_items(data[group], group))
    history = data.get("timeSeries") or data.get("history") or data.get("graph") or []
    if isinstance(history, dict):
        history_points = len(history.get("items") or history.get("data") or [])
    elif isinstance(history, list):
        history_points = len(history)
    else:
        history_points = 0
    total_value = data.get("totalValue") or data.get("TotalValue") or data.get("total_value")
    return {
        "wordstat": {
            "query": data.get("query"),
            "total_value": total_value,
            "queries": queries[:200],
            "history_points": history_points,
        }
    }


def params_for(cfg: dict[str, Any], args: argparse.Namespace, env: dict[str, str]) -> dict[str, str]:
    params = {
        "user": env.get("XMLRIVER_USER_ID", "{XMLRIVER_USER_ID}"),
        "key": env.get("XMLRIVER_API_KEY", "{XMLRIVER_API_KEY}"),
        "query": args.query,
    }
    if args.engine == "google":
        if args.country or nested_get(cfg, "locale.google_gl"):
            params["country"] = str(args.country or nested_get(cfg, "locale.google_gl"))
        if args.lang or nested_get(cfg, "locale.google_hl"):
            params["lr"] = str(args.lang or nested_get(cfg, "locale.google_hl"))
    elif args.engine in {"yandex", "wordstat"}:
        lr = args.lr or nested_get(cfg, "locale.yandex_region_code") or nested_get(cfg, "locale.yandex_lr")
        if lr:
            params["lr" if args.engine == "yandex" else "regions"] = str(lr)
        if args.lang or nested_get(cfg, "locale.language"):
            params["lang"] = str(args.lang or nested_get(cfg, "locale.language"))
    if args.device:
        params["device"] = args.device
    if args.additional:
        params["additional"] = args.additional
    if args.ai:
        params["ai"] = "1"
    if args.ads:
        params["ads"] = "1"
    if args.inindex:
        params["inindex"] = "1"
        params["strict"] = "1"
    if args.delayed:
        params["delayed"] = "1"
    return params


def redact_params(params: dict[str, str]) -> dict[str, str]:
    redacted = dict(params)
    redacted["user"] = "{XMLRIVER_USER_ID}"
    redacted["key"] = "{XMLRIVER_API_KEY}"
    return redacted


def build_url_template(engine: str, params: dict[str, str]) -> str:
    redacted = redact_params(params)
    return ENDPOINTS[engine] + "?" + urllib.parse.urlencode(redacted, safe="{},")


def request_plan(cfg: dict[str, Any], args: argparse.Namespace, env: dict[str, str]) -> dict[str, Any]:
    params = params_for(cfg, args, env)
    plan = {
        "engine": args.engine,
        "endpoint": ENDPOINTS[args.engine],
        "url_template": build_url_template(args.engine, params),
        "params": redact_params(params),
        "env_names": list(ENV_NAMES),
        "credentials_present": all(env.get(name) for name in ENV_NAMES),
        "live_allowed_only_with": ["--live", "--allow-paid"],
        "collection_mode": "delayed" if args.delayed else "realtime",
        "cache_policy": "Write raw to seo/research/raw/xmlriver and use distillates downstream.",
    }
    if args.ai:
        plan["paid_slow_options"] = ["ai=1"]
    return plan


def live_fetch(cfg: dict[str, Any], args: argparse.Namespace, env: dict[str, str]) -> str:
    if not args.allow_paid:
        raise RuntimeError("XMLRiver live requests require --allow-paid in addition to --live.")
    missing = [name for name in ENV_NAMES if not env.get(name)]
    if missing:
        raise RuntimeError(f"Missing required XMLRiver env names: {', '.join(missing)}")
    params = params_for(cfg, args, env)
    url = ENDPOINTS[args.engine] + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "seo-cycle-xmlriver/1"})
    with urllib.request.urlopen(request, timeout=args.timeout_seconds) as response:  # nosec - explicit paid live mode
        return response.read().decode("utf-8", errors="replace")


def read_input(args: argparse.Namespace, cfg: dict[str, Any], env: dict[str, str]) -> tuple[str | None, str]:
    if args.input_file:
        return pathlib.Path(args.input_file).expanduser().read_text(encoding="utf-8"), "file_export"
    if args.stdin_raw:
        return sys.stdin.read(), "stdin_export"
    if args.live:
        return live_fetch(cfg, args, env), "live_api"
    return None, "planned_request"


def build_distillate(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    env = os.environ
    region = args.region or nested_get(cfg, "locale.region") or nested_get(cfg, "locale.country") or "global"
    raw_text, source_type = read_input(args, cfg, env)
    plan = request_plan(cfg, args, env)
    cache_key = stable_cache_key(
        {
            "provider": PROVIDER,
            "engine": args.engine,
            "query": args.query,
            "region": region,
            "source_type": source_type,
            "additional": args.additional,
            "ai": args.ai,
            "ads": args.ads,
            "input": raw_text or "",
        },
        label=f"{args.engine}-{args.query}",
    )

    if raw_text:
        status = "ready"
        input_format = args.input_format
        if input_format == "auto":
            stripped = raw_text.lstrip()
            input_format = "json" if stripped.startswith("{") or stripped.startswith("[") else "xml"
        if args.engine == "wordstat" or input_format == "json":
            parsed = parse_wordstat_json(raw_text)
            organic_results: list[dict[str, Any]] = []
            serp_features: dict[str, Any] = {}
            wordstat = parsed["wordstat"]
            summary = f"XMLRiver Wordstat distillate for `{args.query}`: {len(wordstat['queries'])} keyword rows, total={wordstat.get('total_value') or 'unknown'}."
        else:
            parsed = parse_serp_xml(raw_text, top_n=args.top_n)
            organic_results = parsed["organic_results"]
            serp_features = parsed["serp_features"]
            wordstat = {}
            summary = f"XMLRiver {args.engine} SERP distillate for `{args.query}`: {len(organic_results)} organic results, {len(serp_features)} SERP feature groups."
        distillate = {
            "provider": PROVIDER,
            "status": status,
            "cache_key": cache_key,
            "query": args.query,
            "engine": args.engine,
            "region": region,
            "source_type": source_type,
            "summary": summary,
            "organic_results": organic_results,
            "serp_features": serp_features,
            "wordstat": wordstat,
            "request_plan": plan,
            "price_reference": PRICE_RUB_PER_1000,
            "official_docs": OFFICIAL_DOCS,
            "source_policy": "Use XMLRiver distillate downstream; keep raw API responses out of LLM context.",
        }
        raw_payload = {
            "provider": PROVIDER,
            "status": status,
            "engine": args.engine,
            "query": args.query,
            "region": region,
            "source_type": source_type,
            "collected_at": utc_now_iso(),
            "request_plan": plan,
            "raw_text": raw_text,
        }
        paid_api_used = source_type == "live_api"
    else:
        status = "planned"
        summary = "No XMLRiver response supplied. This is a guarded request plan; no live HTTP/API call was made."
        distillate = {
            "provider": PROVIDER,
            "status": status,
            "cache_key": cache_key,
            "query": args.query,
            "engine": args.engine,
            "region": region,
            "source_type": source_type,
            "summary": summary,
            "organic_results": [],
            "serp_features": {},
            "wordstat": {},
            "request_plan": plan,
            "price_reference": PRICE_RUB_PER_1000,
            "official_docs": OFFICIAL_DOCS,
            "source_policy": "Run with --input-file for exported data or --live --allow-paid only after spend approval.",
        }
        raw_payload = {
            "provider": PROVIDER,
            "status": status,
            "engine": args.engine,
            "query": args.query,
            "region": region,
            "source_type": source_type,
            "created_at": utc_now_iso(),
            "request_plan": plan,
            "raw_text": None,
        }
        paid_api_used = False

    markdown = render_markdown(distillate)
    paths: dict[str, str] = {}
    if args.write:
        paths = write_source_artifacts(
            project_root,
            PROVIDER,
            cache_key,
            raw_payload=raw_payload,
            distillate_markdown=markdown,
            distillate_payload=distillate,
            vector_record=make_vector_record(
                provider=PROVIDER,
                cache_key=cache_key,
                topic=args.query,
                region=str(region),
                mode=f"{args.engine}:{source_type}",
                status=status,
                summary=summary[:1000],
                citations=[row.get("url", "") for row in distillate.get("organic_results", []) if row.get("url")],
                metadata={
                    "engine": args.engine,
                    "source_type": source_type,
                    "serp_feature_groups": sorted((distillate.get("serp_features") or {}).keys()),
                    "wordstat_rows": len((distillate.get("wordstat") or {}).get("queries") or []),
                    "paid_api_used": paid_api_used,
                },
            ),
        )

    approval_gates = []
    if args.live or not raw_text:
        approval_gates.append("paid_api_run")
    if args.ai:
        approval_gates.append("xmlriver_ai_overview_paid_slow_option")
    return {
        "provider": PROVIDER,
        "status": status,
        "generated_at": utc_now_iso(),
        "cache_key": cache_key,
        "query": args.query,
        "engine": args.engine,
        "region": region,
        "source_type": source_type,
        "request_plan": plan,
        "approval_gates": approval_gates,
        "distillate": distillate,
        "paths": paths,
        "writes_to_site": False,
        "paid_api_used": paid_api_used,
    }


def render_markdown(distillate: dict[str, Any]) -> str:
    lines = [
        "# XMLRiver Source Pack",
        "",
        f"- Query: {distillate['query']}",
        f"- Engine: `{distillate['engine']}`",
        f"- Region: {distillate['region']}",
        f"- Status: `{distillate['status']}`",
        f"- Source type: `{distillate['source_type']}`",
        f"- Cache key: `{distillate['cache_key']}`",
        "",
        "## Summary",
        distillate.get("summary") or "",
        "",
        "## Organic Results",
    ]
    organic = distillate.get("organic_results") or []
    if organic:
        lines.extend(f"- {row.get('position')}. {row.get('title')} — {row.get('url')}" for row in organic[:20])
    else:
        lines.append("- none")
    lines.extend(["", "## SERP Features"])
    features = distillate.get("serp_features") or {}
    if features:
        lines.extend(f"- {name}: present" for name in sorted(features))
    else:
        lines.append("- none")
    wordstat = distillate.get("wordstat") or {}
    if wordstat:
        lines.extend(["", "## Wordstat", f"- Total value: {wordstat.get('total_value') or 'unknown'}"])
        for row in (wordstat.get("queries") or [])[:20]:
            lines.append(f"- {row.get('source_group')}: {row.get('query')} ({row.get('value') or 'n/a'})")
    lines.extend(
        [
            "",
            "## Request Plan",
            f"- URL template: `{distillate['request_plan']['url_template']}`",
            f"- Env names: {', '.join(distillate['request_plan']['env_names'])}",
            "",
            "## Source Policy",
            distillate.get("source_policy", "Use distillate only downstream."),
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--query", required=True, help="Search query or URL when --inindex is used.")
    parser.add_argument("--engine", choices=("google", "yandex", "wordstat", "yandex_search"), default="yandex")
    parser.add_argument("--region", help="Human target region label.")
    parser.add_argument("--lr", help="Yandex/Wordstat region id override.")
    parser.add_argument("--country", help="Google country id/code override accepted by XMLRiver account settings.")
    parser.add_argument("--lang", help="Search language override.")
    parser.add_argument("--device", choices=("desktop", "tablet", "mobile", "phone"), help="Device override.")
    parser.add_argument("--additional", help="Comma-separated XMLRiver additional blocks.")
    parser.add_argument("--ai", action="store_true", help="Request AI Overview parsing in live mode. Paid/slower in XMLRiver.")
    parser.add_argument("--ads", action="store_true", help="Request ad blocks in live mode.")
    parser.add_argument("--inindex", action="store_true", help="Indexation check mode; query should be a URL.")
    parser.add_argument("--delayed", action="store_true", help="Use delayed collection mode where supported.")
    parser.add_argument("--input-file", help="Exported XMLRiver XML/JSON response to ingest.")
    parser.add_argument("--input-format", choices=("auto", "xml", "json"), default="auto")
    parser.add_argument("--stdin-raw", action="store_true", help="Read exported XML/JSON response from stdin.")
    parser.add_argument("--live", action="store_true", help="Perform a live XMLRiver HTTP request. Requires env and --allow-paid.")
    parser.add_argument("--allow-paid", action="store_true", help="Explicit approval for paid XMLRiver live request.")
    parser.add_argument("--timeout-seconds", type=int, default=70)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    try:
        report = build_distillate(cfg_path, args)
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_markdown(report["distillate"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
