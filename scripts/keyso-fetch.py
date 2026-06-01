#!/usr/bin/env python3
"""
keyso-fetch.py — клиент Keys.so API (РФ SEO-сервис). Сильная сторона — данные по
Яндексу для РФ/СНГ: частоты Wordstat (ws/wsk), позиции домена, видимость и метрики
конкурентов, потерянные ключи. Дополняет Wordstat (частоты) и Serpstat (Google).

Endpoint: https://api.keys.so · Auth: header X-Keyso-TOKEN (env KEYSO_API_TOKEN).
Лимит: 10 запросов / 10 секунд (HTTP 429 + Retry-After) → клиент троттлит ~1 req/sec
и делает 1 повтор по 429. Кэш на диск (--ttl) предотвращает повторные запросы.

Подкоманды:
  keyword-info KEYWORD          — ws/wsk/cpc/kei/adscnt по ключу (keyword_dashboard)
  keywords     DOMAIN           — органические ключи домена (word/pos/ws/url)
  competitors  DOMAIN           — домены-конкуренты (видимость, топ-10, реклама)
  lost         DOMAIN           — потерянные ключи домена

Опции: --base msk (региональная база) | --per-page 50 | --ttl 60 | --out DIR | --md
Расход: кэш на диск (TTL 60д) + локальный счётчик запросов (_usage.json). Повторный
запрос той же темы в пределах TTL = 0 обращений к API (экономия лимита Pro-тарифа).

Пример:
  python3 keyso-fetch.py keyword-info "минеральная вата"
  python3 keyso-fetch.py competitors emwoody.ru --md
  python3 keyso-fetch.py lost emwoody.ru
"""

from __future__ import annotations
import argparse, hashlib, json, os, pathlib, sys, time, urllib.parse, urllib.request, urllib.error

BASE_URL = "https://api.keys.so"
_LAST = [0.0]
RATE_DELAY = 1.1   # 10 req / 10 sec → ~1/sec

ENDPOINTS = {
    "keyword-info": ("/report/simple/keyword_dashboard", "keyword"),
    "keywords":     ("/report/simple/organic/keywords", "domain"),
    "competitors":  ("/report/simple/organic/concurents", "domain"),
    "lost":         ("/report/simple/organic/lost_keywords", "domain"),
}


def load_token() -> str:
    tok = os.environ.get("KEYSO_API_TOKEN")
    if tok:
        return tok.strip()
    for rel in (".env", "seo/.env"):
        p = pathlib.Path.cwd() / rel
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line.startswith("KEYSO_API_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("ERROR: KEYSO_API_TOKEN не найден (env или .env)")


def bump_usage(out_dir, n=1):
    """Локальный счётчик реальных запросов Keys.so (месячный сброс) — визибилити расхода."""
    import datetime
    f = pathlib.Path(out_dir) / "_usage.json"
    month = datetime.date.today().strftime("%Y-%m")
    u = {"month": month, "requests": 0}
    if f.exists():
        try:
            old = json.loads(f.read_text())
            if old.get("month") == month:
                u = old
        except Exception:
            pass
    u["requests"] = u.get("requests", 0) + n
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(u, ensure_ascii=False, indent=2), encoding="utf-8")
    return u["requests"]


def call(token: str, path: str, params: dict, _retry=True):
    wait = RATE_DELAY - (time.time() - _LAST[0])
    if wait > 0:
        time.sleep(wait)
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(f"{BASE_URL}{path}?{qs}",
                                 headers={"X-Keyso-TOKEN": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            _LAST[0] = time.time()
            data = json.loads(r.read())
            cnt = bump_usage(CACHE_DIR := pathlib.Path("./seo/research/keyso"))
            print(f"  [keyso usage: {cnt} запросов за месяц]", file=sys.stderr)
            return data
    except urllib.error.HTTPError as e:
        _LAST[0] = time.time()
        if e.code == 429 and _retry:
            wait = int(e.headers.get("Retry-After", 10))
            print(f"  429 rate limit — ждём {wait}с", file=sys.stderr)
            time.sleep(wait + 1)
            return call(token, path, params, _retry=False)
        sys.exit(f"ERROR Keys.so HTTP {e.code}: {e.read()[:200]}")


def cache_path(out_dir, cmd, params):
    key = hashlib.md5((cmd + json.dumps(params, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:12]
    return out_dir / f"keyso-{cmd}-{key}.json"


# ---- дистилляторы ----
def d_keyword_info(d, md):
    print("| keyword | ws (Wordstat) | wsk (!точн) | cpc | kei | реклам |")
    print("|---|---|---|---|---|---|")
    print(f"| {d.get('word','')} | {d.get('ws',0)} | {d.get('wsk',0)} | {d.get('cpc',0)} | {d.get('kei',0)} | {d.get('adscnt',0)} |")


def d_keywords(data, md):
    rows = data.get("data", [])
    print(f"| keyword | поз | ws | Δ | url |")
    print("|---|---|---|---|---|")
    for r in rows[:50]:
        print(f"| {r.get('word','')} | {r.get('pos','')} | {r.get('ws',0)} | {r.get('delta',0)} | {r.get('url','')} |")
    print(f"\n(всего страниц: {data.get('last_page','?')})")


def d_competitors(data, md):
    rows = data.get("data", [])
    print(f"| домен | в топ-10 | в топ-3 | видимость | реклама(ключей) |")
    print("|---|---|---|---|---|")
    for r in rows[:50]:
        print(f"| {r.get('name','')} | {r.get('it10',0)} | {r.get('it3',0)} | {r.get('vis',0)} | {r.get('adkeyscnt',0)} |")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=list(ENDPOINTS.keys()))
    ap.add_argument("arg", help="keyword или domain")
    ap.add_argument("--base", default="msk", help="региональная база Keys.so (msk=Яндекс Москва)")
    ap.add_argument("--per-page", type=int, default=50)
    ap.add_argument("--ttl", type=float, default=60, help="кэш в днях (дефолт 60 — экономия лимита)")
    ap.add_argument("--out", default="./seo/research/keyso")
    ap.add_argument("--md", action="store_true")
    args = ap.parse_args()

    token = load_token()
    path, arg_key = ENDPOINTS[args.cmd]
    params = {arg_key: args.arg, "base": args.base}
    if args.cmd != "keyword-info":
        params["per_page"] = args.per_page

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cpath = cache_path(out_dir, args.cmd, params)

    if cpath.exists() and (time.time() - cpath.stat().st_mtime) / 86400.0 <= args.ttl:
        print(f"↩ cache hit (<{args.ttl}д): {cpath}", file=sys.stderr)
        data = json.loads(cpath.read_text(encoding="utf-8"))
    else:
        data = call(token, path, params)
        cpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✓ → {cpath}", file=sys.stderr)

    if args.cmd == "keyword-info":
        d_keyword_info(data, args.md)
    elif args.cmd == "competitors":
        d_competitors(data, args.md)
    else:  # keywords, lost
        d_keywords(data, args.md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
