#!/usr/bin/env python3
"""
atp-fetch.py — AnswerThePublic Public API клиент для сбора вопросов и related-ключей.

ВАЖНО: ATP **не поддерживает регион Россия** (region=ru → 422). Поэтому:
- Запрос делаем на en/us — это даёт универсальные шаблоны вопросов
- Полученные вопросы переводим/адаптируем на русский для FAQ и AEO
  (через LLM CLI: agy --print или codex exec, см. llm-cli-collect.sh)

Стоимость: 1 POST = ~1 кредит на каждый запрошенный провайдер.
В alpha API даже при provider=gweb создаются все 8 child-search (известный баг/особенность).
Рекомендация: используй ATP экономно — 1 запрос на тему = ~8 кредитов.
24h dedupe: повтор того же keyword+lang+region за сутки — БЕЗ повторного списания.

Использование:
    # Health check
    python3 atp-fetch.py --me

    # Сбор полного отчёта на тему (создаёт search + ждёт + сохраняет markdown)
    python3 atp-fetch.py "mineral wool insulation" \\
        --lang en --region us \\
        --output seo/research/atp/results/minvata-atp-$(date +%F).md

    # Только pull уже существующего отчёта (free)
    python3 atp-fetch.py --report-id <parent_search_id> \\
        --output seo/research/atp/results/minvata-atp-$(date +%F).md
"""

from __future__ import annotations
import argparse, json, os, pathlib, sys, time, urllib.parse, urllib.request

BASE = "https://api.answerthepublic.com/api/public/v1"


def _env_token() -> str:
    # Сначала ищем в текущем env, потом подгружаем .env
    tok = os.environ.get("TOKEN_ANSWERTHEPUBLIC")
    if tok:
        return tok
    # Поиск .env по родительским папкам
    cur = pathlib.Path(__file__).resolve().parent
    for p in [cur, *cur.parents]:
        envf = p / ".env"
        if envf.exists():
            for line in envf.read_text().splitlines():
                if line.startswith("TOKEN_ANSWERTHEPUBLIC="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("TOKEN_ANSWERTHEPUBLIC not found in env or .env")


def _req(method: str, path: str, token: str, body=None, query=None) -> dict:
    url = f"{BASE}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body).encode() if body else None
    # User-Agent обязателен — Cloudflare блокирует дефолтный Python-urllib UA (Error 1010 browser_signature_banned)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    if body:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return json.loads(body)
        except Exception:
            return {"error": {"code": e.code, "message": body[:500]}}


def me(token: str) -> dict:
    return _req("GET", "/me", token)


def create_search(token: str, keyword: str, language: str, region: str, provider: str | None = None) -> dict:
    body = {"search": {"keyword": keyword, "language": language, "region": region}}
    if provider:
        body["search"]["provider"] = provider
    return _req("POST", "/searches", token, body=body)


def wait_completed(token: str, parent_id: str, max_wait_sec: int = 300, poll_sec: int = 8) -> dict:
    """Polls report endpoint until at least one provider is completed."""
    deadline = time.time() + max_wait_sec
    while time.time() < deadline:
        rep = _req("GET", f"/reports/{parent_id}", token, query={"per_page": 1})
        if "error" in rep:
            # search not found right after POST — wait a bit
            time.sleep(poll_sec)
            continue
        data = rep.get("data", {})
        # Are any providers in completed status?
        completed = []
        for bucket in ("search_engine", "social_media", "shopping", "ai"):
            for prov, prov_data in (data.get(bucket) or {}).items():
                if prov_data.get("status") == "completed" and prov_data.get("total_results_count", 0):
                    completed.append(prov)
        if completed:
            print(f"  ✓ completed providers: {', '.join(completed)}", file=sys.stderr)
            return rep
        time.sleep(poll_sec)
        print(f"  ... waiting ({int(time.time() - (deadline - max_wait_sec))}s)", file=sys.stderr)
    raise TimeoutError(f"No providers completed within {max_wait_sec}s")


def fetch_source(token: str, parent_id: str, provider: str, source: str, per_page: int = 100) -> list[dict]:
    """Pulls one source bucket (questions / prepositions / comparisons / alphabeticals / related)."""
    rep = _req("GET", f"/reports/{parent_id}", token, query={
        "providers": provider,
        "source_name": source,
        "per_page": per_page,
        "sort_by": "volume",
        "sort_order": "desc",
    })
    data = rep.get("data", {})
    for bucket in ("search_engine", "social_media", "shopping", "ai"):
        prov_data = (data.get(bucket) or {}).get(provider)
        if prov_data and prov_data.get("results", {}).get("data"):
            return prov_data["results"]["data"]
    return []


def render_markdown(parent_id: str, keyword: str, lang: str, region: str, sections: dict[str, list[dict]]) -> str:
    lines = [
        f"---",
        f"keyword: {keyword!r}",
        f"language: {lang}",
        f"region: {region}",
        f"parent_search_id: {parent_id}",
        f"source: AnswerThePublic Public API",
        f"note: Регион Россия не поддерживается ATP — это en/{region} отчёт с универсальными шаблонами вопросов для перевода/адаптации",
        f"---",
        f"",
        f"# AnswerThePublic: «{keyword}» ({lang}/{region})",
        f"",
    ]
    for src, rows in sections.items():
        if not rows:
            continue
        lines.append(f"## {src.title()} ({len(rows)} строк)")
        lines.append("")
        lines.append("| Volume | CPC | Suggestion | Modifier |")
        lines.append("|---|---|---|---|")
        for r in rows:
            vol = int(r.get("search_volume") or 0)
            cpc = r.get("cost_per_click") or "—"
            sug = (r.get("suggestion") or "").replace("|", "\\|")
            mod = r.get("modifier_name") or ""
            lines.append(f"| {vol} | {cpc} | {sug} | {mod} |")
        lines.append("")
    lines += [
        "## Как использовать",
        "",
        "1. **Перевод вопросов на русский** через `agy --print` или `codex exec` — сохранить адаптированные формулировки с учётом Москвы+МО.",
        "2. **Высокообъёмные questions** (volume > 10) → приоритет в FAQ-репитере страницы.",
        "3. **Comparisons** («X vs Y») → темы сравнительных статей блога.",
        "4. **Prepositions** (с / для / без / без X) → расширение long-tail для NW terms.",
        "5. **Alphabeticals** → выявление brand-related queries (mineral wool **rockwool**, mineral wool **knauf** и т.д.).",
        "",
    ]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("keyword", nargs="?", help="Ключевая фраза для исследования")
    p.add_argument("--lang", default="en", help="Язык (default: en, т.к. ru не поддерживается ATP)")
    p.add_argument("--region", default="us", help="Регион (default: us, ru → 422 unsupported)")
    p.add_argument("--provider", default="gweb", help="Провайдер: gweb, youtube, bing, amazon, tiktok, instagram, chatgpt, gemini")
    p.add_argument("--output", type=pathlib.Path, help="Markdown файл для сохранения отчёта")
    p.add_argument("--me", action="store_true", help="Только health check")
    p.add_argument("--report-id", help="UUID уже созданного parent_search — только pull отчёта (free)")
    args = p.parse_args()

    token = _env_token()

    if args.me:
        print(json.dumps(me(token), indent=2, ensure_ascii=False))
        return

    parent_id = args.report_id
    if not parent_id:
        if not args.keyword:
            p.error("Either provide a keyword or use --report-id / --me")
        print(f"== Create ATP search: {args.keyword!r} ({args.lang}/{args.region}, provider={args.provider}) ==", file=sys.stderr)
        resp = create_search(token, args.keyword, args.lang, args.region, args.provider)
        if "error" in resp:
            print(f"ERROR: {resp['error']}", file=sys.stderr)
            sys.exit(1)
        parent_id = resp["data"]["parent_search_id"]
        print(f"  parent_search_id: {parent_id}", file=sys.stderr)
        print(f"  ⏳ Polling for completion (max 5 min)...", file=sys.stderr)
        wait_completed(token, parent_id)

    print(f"== Fetch report sources for {parent_id} ==", file=sys.stderr)
    sections = {}
    for src in ("questions", "prepositions", "comparisons", "alphabeticals", "related"):
        rows = fetch_source(token, parent_id, args.provider, src, per_page=100)
        sections[src] = rows
        print(f"  {src}: {len(rows)} rows", file=sys.stderr)

    md = render_markdown(parent_id, args.keyword or "(by-id)", args.lang, args.region, sections)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md, encoding="utf-8")
        print(f"\n✓ Saved → {args.output}", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()
