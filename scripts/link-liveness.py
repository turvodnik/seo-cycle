#!/usr/bin/env python3
"""External-link liveness check for E-E-A-T: are cited sources still alive?

Collects external http(s) links from drafts, copywriter-ready files, and the
content mirror, then verifies them with HEAD requests (GET fallback for hosts
that reject HEAD). Dead or permanently-redirected sources undermine the
evidence layer — findings feed the refresh workflow.

Polite by design: --live required for network, per-host dedup, --max-urls cap,
результат кэшируется в seo/link-liveness.json (--max-age-days пропускает
недавно проверенные URL).

Usage:
  python3 scripts/link-liveness.py --live --write
  python3 scripts/link-liveness.py            # отчёт по последней проверке
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for, write_text
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("link-liveness")

USER_AGENT = "seo-cycle-linkcheck/1.0"
LINK_RE = re.compile(r"https?://[^\s)\]>\"'`]+")


def collect_links(project_root: pathlib.Path, own_domain: str) -> dict[str, list[str]]:
    """external url -> list of source files it appears in."""
    sources = [
        *(project_root / "seo" / "research-package" / "drafts").glob("*.md"),
        *(project_root / "seo" / "research-package" / "copywriter-ready").glob("*.md"),
        *(project_root / "seo" / "content-mirror" / "records").glob("*.json"),
    ]
    found: dict[str, list[str]] = {}
    for path in sources:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in LINK_RE.findall(text):
            url = match.rstrip(".,;:!?")
            host = urllib.parse.urlparse(url).netloc.lower()
            if not host or (own_domain and own_domain in host):
                continue
            found.setdefault(url, []).append(str(path.relative_to(project_root)))
    return found


def check_url(url: str, timeout: int) -> dict[str, Any]:
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return {"url": url, "status": response.status,
                        "final_url": response.geturl(),
                        "redirected": response.geturl().rstrip("/") != url.rstrip("/")}
        except urllib.error.HTTPError as err:
            if method == "HEAD" and err.code in (403, 405, 501):
                continue  # host dislikes HEAD — retry with GET
            return {"url": url, "status": err.code, "final_url": url, "redirected": False}
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            return {"url": url, "status": 0, "final_url": url, "redirected": False,
                    "error": str(getattr(err, "reason", err))[:120]}
    return {"url": url, "status": 0, "final_url": url, "redirected": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="Perform network checks")
    parser.add_argument("--max-urls", type=int, default=200)
    parser.add_argument("--max-age-days", type=int, default=7,
                        help="Skip URLs checked more recently than this")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    cfg_path = find_config(pathlib.Path.cwd())
    if not cfg_path:
        print("ERROR: seo-cycle.yaml not found", file=sys.stderr)
        return 2
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    global log
    log = setup_logging("link-liveness", project_root, cfg)
    own_domain = re.sub(r"^https?://", "", str(nested_get(cfg, "project.domain", "") or "")).strip("/")

    state_path = project_root / "seo" / "link-liveness.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {"checked": {}}

    links = collect_links(project_root, own_domain)
    now = dt.datetime.now(dt.timezone.utc)
    fresh_cutoff = (now - dt.timedelta(days=args.max_age_days)).isoformat()

    if args.live:
        pending = [url for url in links
                   if (state["checked"].get(url) or {}).get("at", "") < fresh_cutoff][:args.max_urls]
        log.info("checking %s urls (of %s found)", len(pending), len(links))
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as pool:
            for result in pool.map(lambda u: check_url(u, args.timeout), pending):
                state["checked"][result["url"]] = {**result, "at": now.isoformat(timespec="seconds")}
    elif not state["checked"]:
        print("Проверок ещё не было: запустите с --live (бесплатные HEAD-запросы, "
              f"cap {args.max_urls}).", file=sys.stderr)
        return 0

    dead, redirected, alive = [], [], 0
    for url, sources in sorted(links.items()):
        checked = state["checked"].get(url)
        if not checked:
            continue
        entry = {"url": url, "status": checked.get("status"), "sources": sorted(set(sources))[:5]}
        if not checked.get("status") or checked["status"] >= 400:
            dead.append(entry)
        elif checked.get("redirected"):
            redirected.append(entry)
        else:
            alive += 1

    report = {
        "audit_id": "link_liveness",
        "generated_at": now.isoformat(timespec="seconds"),
        "links_found": len(links),
        "alive": alive,
        "dead": dead,
        "redirected": redirected,
        "unchecked": len([u for u in links if u not in state["checked"]]),
    }
    if args.write:
        write_text(state_path, json.dumps({**state, "report": report}, ensure_ascii=False, indent=2) + "\n")
        print(f"✓ {state_path}", file=sys.stderr)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    lines = ["# Живость внешних источников", "",
             f"- Найдено внешних ссылок: {report['links_found']} · живых: {alive}"
             f" · мёртвых: {len(dead)} · через редирект: {len(redirected)}"
             f" · не проверено: {report['unchecked']}", ""]
    if dead:
        lines.append("## Мёртвые источники (заменить в текстах!)")
        lines.extend(f"- [{d['status'] or 'net'}] {d['url']}\n  - где: {', '.join(d['sources'])}" for d in dead)
    if redirected:
        lines.extend(["", "## Постоянные редиректы (обновить URL)"])
        lines.extend(f"- {r['url']}" for r in redirected[:15])
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
