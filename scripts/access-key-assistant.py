#!/usr/bin/env python3
"""Generate project-specific key/token setup instructions.

The assistant reads the tool-stack decision report and emits only the access
steps that are relevant for the current project. It never stores or prints
secret values; it only lists env var names, provider links, and short steps.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import pathlib
import subprocess
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, policy_path, project_root_for
from seo_cycle_core.reports import write_artifacts

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. `pip3 install pyyaml`", file=sys.stderr)
    sys.exit(2)


ACTIVE_DECISIONS = {"enabled", "report_only", "approval_required"}

ACCESS_CATALOG: dict[str, dict[str, Any]] = {
    "google_service_account": {
        "title": "Google service account JSON",
        "env": ["GOOGLE_APPLICATION_CREDENTIALS"],
        "tools": ["google_search_console", "google_cloud_nlp", "google_merchant", "google_business_profile", "google_analytics_4", "google_youtube"],
        "url": "https://console.cloud.google.com/iam-admin/serviceaccounts",
        "doc": "docs/oauth-setup.md#1-google-cloud-platform-setup-одноразово",
        "steps": [
            "Create or reuse a Google Cloud project.",
            "Create a service account and download one JSON key.",
            "Store the JSON outside the repo, chmod 600, and put only its path in GOOGLE_APPLICATION_CREDENTIALS.",
        ],
        "notes": "One service account can be reused across projects when you add its email to each property/account.",
    },
    "google_search_console": {
        "title": "Google Search Console property access",
        "env": ["GSC_SITE_URL", "GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN"],
        "tools": ["google_search_console"],
        "url": "https://search.google.com/search-console",
        "doc": "docs/oauth-setup.md#2-search-console-gsc-доступ",
        "steps": [
            "Open the verified property.",
            "Add the service-account client_email as a user.",
            "Set GSC_SITE_URL as sc-domain:example.com or https://example.com/.",
            "For URL Inspection API live checks, provide a short-lived OAuth access token in GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN or pass an exported JSON response instead.",
        ],
        "notes": "Read-only/off-site evidence; no analytics tag is installed.",
    },
    "google_merchant": {
        "title": "Google Merchant Center access",
        "env": ["GOOGLE_MERCHANT_ACCOUNT_ID"],
        "tools": ["google_merchant"],
        "url": "https://merchants.google.com/",
        "doc": "docs/oauth-setup.md#7-google-merchant-business-profile-и-youtube",
        "steps": [
            "Open the Merchant Center account for this project.",
            "Add the service account/user where API access is supported.",
            "Copy only the Merchant account ID into GOOGLE_MERCHANT_ACCOUNT_ID.",
        ],
        "notes": "Feed diagnostics/free listings only; paid campaigns stay approval-gated.",
    },
    "google_business_profile": {
        "title": "Google Business Profile / Maps",
        "env": ["GOOGLE_BUSINESS_ACCOUNT_ID", "GOOGLE_BUSINESS_LOCATION_ID"],
        "tools": ["google_business_profile"],
        "url": "https://business.google.com/",
        "doc": "docs/oauth-setup.md#7-google-merchant-business-profile-и-youtube",
        "steps": [
            "Open the Business Profile manager.",
            "Confirm this project has a real public location/profile.",
            "Record only account/location IDs in .env.",
        ],
        "notes": "Use only for local/profile quality work; no tracking tag.",
    },
    "google_analytics_4": {
        "title": "Google Analytics 4 property access",
        "env": ["GA4_PROPERTY_ID"],
        "tools": ["google_analytics_4"],
        "url": "https://analytics.google.com/",
        "doc": "docs/oauth-setup.md#3-google-analytics-4-ga4-доступ",
        "steps": [
            "Use only if the project policy allows analytics/tracking.",
            "Add service-account email as Viewer on the GA4 property.",
            "Record the numeric property ID in GA4_PROPERTY_ID.",
        ],
        "notes": "For RF projects, do not install a new foreign analytics tag without written policy approval.",
    },
    "youtube": {
        "title": "YouTube channel/API setup",
        "env": ["YOUTUBE_CHANNEL_ID"],
        "tools": ["google_youtube"],
        "url": "https://console.cloud.google.com/apis/library/youtube.googleapis.com",
        "doc": "docs/oauth-setup.md#7-google-merchant-business-profile-и-youtube",
        "steps": [
            "Enable YouTube Data API only if video SEO/publishing is in scope.",
            "Use API key for public reads; OAuth is needed for publishing/managing.",
            "Record the channel ID in YOUTUBE_CHANNEL_ID.",
        ],
        "notes": "Publishing remains separate approval.",
    },
    "yandex_webmaster": {
        "title": "Yandex Webmaster OAuth token",
        "env": ["YANDEX_OAUTH_TOKEN", "YANDEX_USER_ID", "YANDEX_WEBMASTER_HOST_ID"],
        "tools": ["yandex_webmaster"],
        "url": "https://oauth.yandex.ru/client/new",
        "doc": "docs/oauth-setup.md#5-яндекс-oauth-для-метрики-и-вебмастера",
        "steps": [
            "Create a Yandex OAuth app with the Webmaster scopes required by docs/oauth-setup.md.",
            "Use the verification_code/manual flow to get a token.",
            "Fetch user_id and webmaster host_id with the documented curl commands.",
        ],
        "notes": "Do not paste OAuth token into reports or questionnaire files; only .env.",
    },
    "yandex_metrika": {
        "title": "Yandex Metrica OAuth token",
        "env": ["YANDEX_OAUTH_TOKEN", "YANDEX_METRIKA_COUNTER_ID"],
        "tools": ["yandex_metrika"],
        "url": "https://oauth.yandex.ru/client/new",
        "doc": "docs/oauth-setup.md#5-яндекс-oauth-для-метрики-и-вебмастера",
        "steps": [
            "Use only when the project policy allows the Metrica counter.",
            "Create/reuse a Yandex OAuth app with the Metrica read scopes required by docs/oauth-setup.md.",
            "Record only the counter ID and token in .env.",
        ],
        "notes": "For projects where counters/tracking are not allowed, leave Metrica disabled.",
    },
    "yandex_merchant": {
        "title": "Yandex Merchant / Товары",
        "env": ["YANDEX_MERCHANT_BUSINESS_ID"],
        "tools": ["yandex_merchant"],
        "url": "https://merchants.yandex.ru/",
        "doc": "docs/oauth-setup.md#9-яндекс-дополнительные-сервисы",
        "steps": [
            "Open the project business in Yandex Merchant / Товары.",
            "Confirm feed/product diagnostics are needed.",
            "Record only the business ID in YANDEX_MERCHANT_BUSINESS_ID.",
        ],
        "notes": "Product/feed diagnostics only; ads and paid promotion stay separate.",
    },
    "yandex_direct": {
        "title": "Yandex Direct client login",
        "env": ["YANDEX_DIRECT_CLIENT_LOGIN"],
        "tools": ["yandex_direct"],
        "url": "https://direct.yandex.ru/",
        "doc": "docs/oauth-setup.md#9-яндекс-дополнительные-сервисы",
        "steps": [
            "Use only for planning/audits when paid media is approved.",
            "Record the client login, not passwords or campaign secrets.",
            "Keep campaign launch/spend behind approval.",
        ],
        "notes": "No ad spend without budget and explicit approval.",
    },
    "bing_webmaster": {
        "title": "Bing Webmaster Tools API key",
        "env": ["BING_WEBMASTER_API_KEY", "BING_SITE_URL"],
        "tools": ["bing_webmaster"],
        "url": "https://www.bing.com/webmasters/",
        "doc": "docs/oauth-setup.md#81-bing-webmaster",
        "steps": [
            "Add or import the site in Bing Webmaster.",
            "Create/copy the API key in account settings.",
            "Record BING_SITE_URL as the verified site URL.",
        ],
        "notes": "Read-only Bing/Copilot evidence; no tracking tag.",
    },
    "indexnow": {
        "title": "IndexNow key",
        "env": ["INDEXNOW_KEY", "INDEXNOW_KEY_LOCATION"],
        "tools": ["indexnow"],
        "url": "https://www.indexnow.org/documentation",
        "doc": "docs/oauth-setup.md#82-indexnow",
        "steps": [
            "Generate a random key.",
            "Host it as a public .txt file at the site root.",
            "Record key and public key location in .env.",
        ],
        "notes": "Mutates search engine submission queues; run only after approval.",
    },
    "neuronwriter": {
        "title": "NeuronWriter API key and project ID",
        "env": ["NEURON_API_KEY"],
        "tools": ["neuronwriter"],
        "url": "https://app.neuronwriter.com/",
        "doc": "docs/oauth-setup.md#11-paidsubscription-tools",
        "steps": [
            "Open NeuronWriter account/API settings.",
            "Copy the API key only into .env.",
            "Record the project ID and current monthly limits in seo/neuronwriter-limits.yaml.",
        ],
        "notes": "Use only priority pages; no whole-catalog runs without an approved queue.",
    },
    "writerzen": {
        "title": "WriterZen browser/export setup",
        "env": [],
        "tools": ["writerzen"],
        "url": "https://app.writerzen.net/",
        "doc": "docs/oauth-setup.md#112-writerzen-browserexport",
        "manual_setup": True,
        "steps": [
            "Open WriterZen in the browser and log in manually; do not store the password in seo-cycle.",
            "Run writerzen-browser-collect.py with --topic and --force-new-report so the assistant creates Topic Discovery, Keyword Explorer, Keyword Planner and Domain Focus, downloads CSV/XLSX, and imports them.",
            "If the WriterZen UI changes, rerun with --manual-fallback-seconds and click Export manually while the script captures the download.",
            "Run writerzen-health.py --browser-available --write when the logged-in browser session is ready.",
        ],
        "notes": "WriterZen has no public API in this workflow. The assistant uses browser/export mode, caches raw exports on disk, and sends only distillates/vector records downstream.",
    },
    "keyso": {
        "title": "Keys.so API token",
        "env": ["KEYSO_API_TOKEN"],
        "tools": ["keyso"],
        "url": "https://keys.so/",
        "doc": "docs/oauth-setup.md#11-paidsubscription-tools",
        "steps": [
            "Open account/API settings.",
            "Copy token only into .env.",
            "Set monthly request caps and reserve in seo/tool-budget.yaml.",
        ],
        "notes": "Use request caps and cache for RU keyword evidence.",
    },
    "serpstat": {
        "title": "Serpstat API key",
        "env": ["SERPSTAT_API_KEY"],
        "tools": ["serpstat"],
        "url": "https://serpstat.com/api/",
        "doc": "docs/oauth-setup.md#11-paidsubscription-tools",
        "steps": [
            "Open Serpstat API settings.",
            "Copy API key only into .env.",
            "Set credit caps/reserve before first run.",
        ],
        "notes": "Quota-based; always run spend guard first.",
    },
    "xmlriver": {
        "title": "XMLRiver user ID and API key",
        "env": ["XMLRIVER_USER_ID", "XMLRIVER_API_KEY"],
        "tools": ["xmlriver"],
        "url": "https://xmlriver.com/",
        "doc": "docs/oauth-setup.md#13-xmlriver",
        "steps": [
            "Register or open the XMLRiver account.",
            "Open collection settings and confirm Google/Yandex/Wordstat parameters needed by this project.",
            "Copy only the numeric user ID and API key into .env as XMLRIVER_USER_ID and XMLRIVER_API_KEY.",
            "Run spend-guard/usage-ledger preflight before any --live --allow-paid XMLRiver call.",
        ],
        "notes": "Use exported XML/JSON or cached distillates by default. Live XMLRiver requests are paid API calls and stay approval-gated.",
    },
    "answerthepublic": {
        "title": "AnswerThePublic token",
        "env": ["TOKEN_ANSWERTHEPUBLIC"],
        "tools": ["answerthepublic"],
        "url": "https://answerthepublic.com/",
        "doc": "docs/oauth-setup.md#11-paidsubscription-tools",
        "steps": [
            "Use only if question research is in scope.",
            "Copy token only into .env.",
            "Set monthly usage caps if the plan is limited.",
        ],
        "notes": "Skip when Yandex/Google suggest already covers the needed question layer.",
    },
    "gemini": {
        "title": "Gemini API key",
        "env": ["GEMINI_API_KEY"],
        "tools": ["gemini"],
        "url": "https://aistudio.google.com/app/apikey",
        "doc": "docs/oauth-setup.md#12-ai-api-keys",
        "steps": [
            "Create a project/API key only if Gemini checks are needed.",
            "Restrict the key where possible.",
            "Record it only in .env and ledger token spend.",
        ],
        "notes": "Optional AI comparison layer; skip unless requested by project policy.",
    },
    "deepseek": {
        "title": "DeepSeek API key",
        "env": ["DEEPSEEK_API_KEY"],
        "tools": ["deepseek"],
        "url": "https://platform.deepseek.com/api_keys",
        "doc": "docs/oauth-setup.md#12-ai-api-keys",
        "steps": [
            "Create key only if DeepSeek comparison is needed.",
            "Record it only in .env.",
            "Set a monthly LLM cap before first run.",
        ],
        "notes": "Optional; skip by default when no explicit AI-comparison task exists.",
    },
}


def skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_tool_stack(cfg_path: pathlib.Path, project_root: pathlib.Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(skill_root() / "scripts" / "tool-stack-recommender.py"), str(cfg_path), "--format", "json"],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return {}
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def load_tool_stack(cfg_path: pathlib.Path, cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    existing = policy_path(cfg, project_root, "tool_stack_report", "seo/setup/tool-stack-report.md").with_suffix(".json")
    return load_json(existing) or run_tool_stack(cfg_path, project_root)


def env_present(project_root: pathlib.Path) -> set[str]:
    env_file = project_root / ".env"
    names: set[str] = set()
    if not env_file.exists():
        return names
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if value.strip():
            names.add(name.strip())
    return names


def runtime_contract(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, str]:
    env_file = project_root / ".env"
    env_runtime = ""
    env_search = ""
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            if raw.startswith("SEO_RUNTIME="):
                env_runtime = raw.split("=", 1)[1].strip()
            if raw.startswith("SEO_SEARCH_RUNTIME="):
                env_search = raw.split("=", 1)[1].strip()
    runtime = env_runtime or str(cfg.get("runtime") or "auto")
    if env_search:
        search_runtime = env_search
    elif runtime == "claude":
        search_runtime = "codex_external"
    elif runtime == "codex":
        search_runtime = "direct"
    else:
        search_runtime = "auto"
    return {"runtime": runtime, "search_runtime": search_runtime}


def relevant_tools(tool_stack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    decisions = tool_stack.get("decisions", {}) if isinstance(tool_stack.get("decisions"), dict) else {}
    return {
        tool_id: row
        for tool_id, row in decisions.items()
        if isinstance(row, dict) and row.get("decision") in ACTIVE_DECISIONS
    }


def task_needed(catalog_row: dict[str, Any], tools: dict[str, dict[str, Any]], present: set[str]) -> bool:
    if not any(tool in tools for tool in catalog_row.get("tools", [])):
        return False
    if catalog_row.get("manual_setup"):
        return True
    return any(name not in present for name in catalog_row.get("env", []))


def build_report(cfg_path: pathlib.Path) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    tool_stack = load_tool_stack(cfg_path, cfg, project_root)
    present = env_present(project_root)
    tools = relevant_tools(tool_stack)
    tasks = []
    skipped = []
    for access_id, meta in ACCESS_CATALOG.items():
        if task_needed(meta, tools, present):
            related = [tool for tool in meta.get("tools", []) if tool in tools]
            decisions = sorted({tools[tool].get("decision") for tool in related if tool in tools})
            gates = sorted({gate for tool in related for gate in tools[tool].get("approval_gates", [])})
            missing_env = [name for name in meta.get("env", []) if name not in present]
            tasks.append(
                {
                    "id": access_id,
                    "title": meta["title"],
                    "related_tools": related,
                    "decisions": decisions,
                    "missing_env": missing_env,
                    "all_env": meta.get("env", []),
                    "url": meta.get("url"),
                    "doc": meta.get("doc"),
                    "steps": meta.get("steps", []),
                    "notes": meta.get("notes", ""),
                    "approval_gates": gates,
                    "status": "approval_required" if "approval_required" in decisions or gates else "needed",
                }
            )
        else:
            skipped.append(access_id)
    report = {
        "version": 1,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "project": cfg.get("project", {}),
        "runtime_contract": runtime_contract(cfg, project_root),
        "summary": {
            "tasks": len(tasks),
            "approval_required": sum(1 for task in tasks if task["status"] == "approval_required"),
            "skipped": len(skipped),
        },
        "tasks": tasks,
        "skipped": skipped,
        "rules": [
            "Never paste API keys, OAuth tokens, passwords, service-account JSON, or client secrets into reports.",
            "Write only env var names and file paths here; secret values live in .env or provider consoles.",
            "Skip a provider if the related tool is not applicable or blocked by project policy.",
        ],
        "next_actions": [
            "Fill only the needed .env names from this report.",
            "Run `python3 ~/.codex/skills/seo-cycle/scripts/validate-config.py` after editing .env.",
            "Run `python3 ~/.codex/skills/seo-cycle/scripts/spend-guard.py --write` before paid/quota/LLM/API work.",
        ],
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    runtime = report.get("runtime_contract", {})
    lines = [
        "# seo-cycle access key assistant",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Runtime/search runtime: {runtime.get('runtime')} / {runtime.get('search_runtime')}",
        f"- Needed access tasks: {report.get('summary', {}).get('tasks')}",
        f"- Approval-required tasks: {report.get('summary', {}).get('approval_required')}",
        "",
        "## Needed Keys And Tokens",
    ]
    if not report.get("tasks"):
        lines.append("- No project-specific missing keys detected from the current tool stack.")
    for task in report.get("tasks", []):
        lines.extend(
            [
                "",
                f"### {task['title']}",
                f"- Status: `{task['status']}`",
                f"- Related tools: {', '.join(task.get('related_tools', [])) or '-'}",
                f"- Missing env names: {', '.join(f'`{name}`' for name in task.get('missing_env', [])) or '-'}",
                f"- URL: {task.get('url')}",
                f"- Docs: `{task.get('doc')}`",
                f"- Approval gates: {', '.join(task.get('approval_gates', [])) or '-'}",
                "- Steps:",
            ]
        )
        for step in task.get("steps", []):
            lines.append(f"  - {step}")
        if task.get("notes"):
            lines.append(f"- Notes: {task['notes']}")
    lines.extend(["", "## Rules"])
    for rule in report.get("rules", []):
        lines.append(f"- {rule}")
    lines.extend(["", "## Next Actions"])
    for action in report.get("next_actions", []):
        lines.append(f"- {action}")
    return "\n".join(lines) + "\n"


def csv_report(report: dict[str, Any]) -> str:
    buffer = io.StringIO()
    fields = ["id", "title", "status", "related_tools", "missing_env", "url", "doc", "approval_gates", "notes"]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for task in report.get("tasks", []):
        writer.writerow(
            {
                "id": task.get("id", ""),
                "title": task.get("title", ""),
                "status": task.get("status", ""),
                "related_tools": ", ".join(task.get("related_tools", [])),
                "missing_env": ", ".join(task.get("missing_env", [])),
                "url": task.get("url", ""),
                "doc": task.get("doc", ""),
                "approval_gates": ", ".join(task.get("approval_gates", [])),
                "notes": task.get("notes", ""),
            }
        )
    return buffer.getvalue()


def write_outputs(project_root: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    setup_dir = project_root / "seo" / "setup"
    markdown = render_markdown(report)
    write_artifacts(
        text_files={
            setup_dir / "access-key-assistant.md": markdown,
            setup_dir / "latest-access-key-assistant.md": markdown,
            setup_dir / "access-key-assistant.csv": csv_report(report),
        },
        json_files={
            setup_dir / "access-key-assistant.json": report,
            setup_dir / "latest-access-key-assistant.json": report,
        },
    )
    return setup_dir / "access-key-assistant.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write access-key assistant artifacts under seo/setup.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    if args.config:
        cfg_path = pathlib.Path(args.config).expanduser().resolve()
    else:
        found = find_config(pathlib.Path.cwd())
        if not found:
            print(f"ERROR: seo-cycle.yaml не найден в {pathlib.Path.cwd()}", file=sys.stderr)
            return 2
        cfg_path = found.resolve()
    if not cfg_path.exists():
        print(f"ERROR: {cfg_path} не найден", file=sys.stderr)
        return 2

    project_root = project_root_for(cfg_path)
    report = build_report(cfg_path)
    if args.write:
        write_outputs(project_root, report)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
