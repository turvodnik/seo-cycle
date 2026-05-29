#!/usr/bin/env python3
"""
serpstat-fetch.py — клиент Serpstat API v4 для Phase 2 (keyword research,
competitor analysis). Serpstat ценен тем, что даёт Google-данные по РФ/СНГ
(`g_ru`, `g_ua` и т.д.) — там, где Ahrefs/SEMrush гео-ограничены.

⚠ ЛИМИТ КРЕДИТОВ МАЛ (план Appsumo: 1000 строк/месяц, 1 запрос/сек).
Поэтому клиент:
  - перед списывающим запросом проверяет остаток через getStats (бесплатно)
    и блокирует, если осталось меньше --min-credits (default 50), кроме --force;
  - ограничивает строки через --size (= кредиты);
  - кэширует результат на диск (--ttl дней) — повтор не тратит кредиты;
  - соблюдает rate-limit 1 req/sec.

Токен: SERPSTAT_API_KEY (env или .env проекта).

Подкоманды:
  stats                              — остаток лимитов (бесплатно)
  keywords-info  KW [KW...]          — volume/CPC/difficulty/concurrency (~1 кредит/ключ)
  related        KW   [--size N]     — связанные ключи
  suggestions    KW   [--size N]     — поисковые подсказки (дёшево, semantic)
  domain-keywords DOMAIN [--size N]  — ключи домена (конкурента)
  competitors    KW   [--size N]     — домены-конкуренты по ключу

Общие опции: --se g_ru (default) | --ttl 30 | --min-credits 50 | --force
             --out DIR (default ./seo/research/serpstat)

Пример:
  python3 serpstat-fetch.py keywords-info "минеральная вата" "осп плита" --se g_ru
  python3 serpstat-fetch.py related "плиточный клей" --size 100
"""

from __future__ import annotations
import argparse, hashlib, json, os, pathlib, sys, time, urllib.request

ENDPOINT = "https://api.serpstat.com/v4"
_LAST_CALL = [0.0]
RATE_DELAY = 1.1   # сек между запросами (план: delayBetweenRequests=1)


def load_token() -> str:
    tok = os.environ.get("SERPSTAT_API_KEY")
    if tok:
        return tok.strip()
    for rel in (".env", "seo/.env"):
        p = pathlib.Path.cwd() / rel
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line.startswith("SERPSTAT_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("ERROR: SERPSTAT_API_KEY не найден (env или .env)")


def call(token: str, method: str, params: dict) -> dict:
    # rate-limit
    wait = RATE_DELAY - (time.time() - _LAST_CALL[0])
    if wait > 0:
        time.sleep(wait)
    body = json.dumps({"id": "1", "method": method, "params": params}).encode()
    req = urllib.request.Request(f"{ENDPOINT}?token={token}", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
    _LAST_CALL[0] = time.time()
    if "error" in out:
        sys.exit(f"ERROR Serpstat: {out['error']}")
    return out.get("result", {})


def get_left_credits(token: str) -> int:
    res = call(token, "SerpstatLimitsProcedure.getStats", {})
    return int(res.get("data", {}).get("left_lines", 0))


def preflight(token: str, min_credits: int, force: bool):
    left = get_left_credits(token)
    print(f"  [credits] осталось {left}/мес", file=sys.stderr)
    if left < min_credits and not force:
        sys.exit(f"ERROR: осталось {left} кредитов (< --min-credits {min_credits}). "
                 f"Используй --force чтобы всё равно выполнить.")
    return left


def cache_path(out_dir: pathlib.Path, method: str, params: dict) -> pathlib.Path:
    key = hashlib.md5((method + json.dumps(params, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:12]
    safe = method.split(".")[-1]
    return out_dir / f"serpstat-{safe}-{key}.json"


def fresh_cache(path: pathlib.Path, ttl_days: float):
    if path.exists() and (time.time() - path.stat().st_mtime) / 86400.0 <= ttl_days:
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def run(token, method, params, args, distill):
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cpath = cache_path(out_dir, method, params)

    cached = fresh_cache(cpath, args.ttl)
    if cached is not None:
        print(f"↩ cache hit (<{args.ttl}д): {cpath} — без списания кредитов", file=sys.stderr)
        data = cached
    else:
        preflight(token, args.min_credits, args.force)
        res = call(token, method, params)
        data = res.get("data", [])
        cpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        left = res.get("summary_info", {}).get("left_lines")
        print(f"  ✓ {len(data)} строк → {cpath} (осталось {left})", file=sys.stderr)
    distill(data)


# ---- дистилляторы (markdown-таблица в stdout) ----

def d_keywords_info(data):
    print("| keyword | volume | CPC | difficulty | concurrency |")
    print("|---|---|---|---|---|")
    for r in data:
        print(f"| {r.get('keyword','')} | {r.get('region_queries_count',0)} | "
              f"{r.get('cost',0)} | {r.get('difficulty','')} | {r.get('concurrency','')} |")


def d_keywords_list(data):
    print("| keyword | volume | CPC | difficulty |")
    print("|---|---|---|---|")
    for r in data:
        print(f"| {r.get('keyword','')} | {r.get('region_queries_count', r.get('queries',0))} | "
              f"{r.get('cost','')} | {r.get('difficulty','')} |")


def d_competitors(data):
    print("| domain | common_keywords | visibility |")
    print("|---|---|---|")
    for r in data:
        print(f"| {r.get('domain','')} | {r.get('common', r.get('common_keywords',''))} | "
              f"{r.get('visible', r.get('visibility',''))} |")


def d_raw(data):
    print(f"(получено {len(data)} строк; сырьё на диске)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["stats", "keywords-info", "related",
                                    "suggestions", "domain-keywords", "competitors"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--se", default="g_ru", help="search engine code (g_ru, g_ua, g_us, g_uk, g_de...)")
    ap.add_argument("--size", type=int, default=100, help="макс. строк = кредитов (для списка)")
    ap.add_argument("--ttl", type=float, default=30, help="кэш в днях")
    ap.add_argument("--min-credits", type=int, default=50)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--out", default="./seo/research/serpstat")
    args = ap.parse_args()

    token = load_token()

    if args.cmd == "stats":
        res = call(token, "SerpstatLimitsProcedure.getStats", {})
        d = res.get("data", {})
        print(f"API кредиты: {d.get('left_lines')}/{d.get('max_lines')} осталось "
              f"(использовано {d.get('used_lines')})")
        pl = d.get("plugin_limits", {})
        print(f"Website SEO Checker (день): {pl.get('left')}/{pl.get('total')}; "
              f"delay {pl.get('delayBetweenRequests')}s/req")
        return 0

    if not args.args:
        sys.exit(f"ERROR: команда {args.cmd} требует аргумент(ы)")

    if args.cmd == "keywords-info":
        run(token, "SerpstatKeywordProcedure.getKeywordsInfo",
            {"keywords": args.args, "se": args.se}, args, d_keywords_info)
    elif args.cmd == "related":
        run(token, "SerpstatKeywordProcedure.getRelatedKeywords",
            {"keyword": args.args[0], "se": args.se, "size": args.size}, args, d_keywords_list)
    elif args.cmd == "suggestions":
        run(token, "SerpstatKeywordProcedure.getSuggestions",
            {"keyword": args.args[0], "se": args.se, "size": args.size}, args, d_keywords_list)
    elif args.cmd == "domain-keywords":
        run(token, "SerpstatDomainProcedure.getDomainKeywords",
            {"domain": args.args[0], "se": args.se, "size": args.size}, args, d_keywords_list)
    elif args.cmd == "competitors":
        run(token, "SerpstatKeywordProcedure.getCompetitors",
            {"keyword": args.args[0], "se": args.se, "size": args.size}, args, d_competitors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
