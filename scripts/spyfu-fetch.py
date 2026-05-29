#!/usr/bin/env python3
"""
spyfu-fetch.py — клиент SpyFu API для competitor/PPC/SEO-аналитики.

⚠ ОБЛАСТЬ ПРИМЕНЕНИЯ: SpyFu покрывает Google US/UK и ряд западных стран
(countryCode: US, GB, CA, DE, FR, AU, ...). **РФ/Яндекс НЕ покрывает** (RU
отвергается API). Поэтому источник включён в профили us/eu/global, НЕ ru.
Для РФ-проектов полезен только для анализа международных конкурентов.

💳 БИЛЛИНГ: pay-as-you-go по строкам. Pro = $40 кредита/мес. CPM по эндпоинту:
  domain-stats $0.50 · competitors/keyword-info $0.20 · ad-history/ppc $2-3 ·
  top-pages $5.00 (формула: rows/1000 * CPM). Клиент ведёт локальный
  usage-трекер (seo/research/spyfu/_usage.json) с месячным сбросом и блокирует
  при достижении --budget (default $40), кроме --force. SpyFu не отдаёт остаток
  через API — точную сверку смотри на spyfu.com/account/api.

Auth: Basic base64(API_SpyFu_ID:API_SpyFu_secret_key) — собирается из .env,
либо берётся готовый *_SpyFu_base-64_key.

Подкоманды:
  usage                              — показать локальный трекер расходов
  domain-stats DOMAIN [--all] [--cc US]
                                     — latest (1 строка, дёшево) или вся история (--all)
  raw PATH [--param k=v ...] [--cpm N]
                                     — произвольный эндпоинт SpyFu API v2

Опции: --cc US | --budget 40 | --ttl 30 | --force | --out ./seo/research/spyfu

Пример:
  python3 spyfu-fetch.py domain-stats competitor.com --cc US
  python3 spyfu-fetch.py usage
"""

from __future__ import annotations
import argparse, base64, datetime, hashlib, json, os, pathlib, sys, time, urllib.parse, urllib.request

API_BASE = "https://api.spyfu.com/apis"
RATE_DELAY = 0.5

ENDPOINTS = {
    "domain-stats-latest": ("domain_stats_api/v2/getLatestDomainStats", 0.50),
    "domain-stats-all":    ("domain_stats_api/v2/getAllDomainStats", 0.50),
}


def load_auth() -> str:
    """Вернёт base64 для Authorization: Basic. Собирает из ID:secret, либо готовый ключ."""
    env = dict(os.environ)
    for rel in (".env", "seo/.env"):
        p = pathlib.Path.cwd() / rel
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    app_id = env.get("API_SpyFu_ID")
    secret = env.get("API_SpyFu_secret_key")
    if app_id and secret:
        return base64.b64encode(f"{app_id}:{secret}".encode()).decode()
    # fallback: готовый base64 (имя может варьироваться из-за опечатки)
    for k, v in env.items():
        if "spyfu" in k.lower() and "base-64" in k.lower():
            return v
    sys.exit("ERROR: нет SpyFu ключей в .env (API_SpyFu_ID + API_SpyFu_secret_key)")


# ---- usage-трекер ($-бюджет, месячный сброс) ----

def usage_file(out_dir: pathlib.Path) -> pathlib.Path:
    return out_dir / "_usage.json"


def load_usage(out_dir: pathlib.Path) -> dict:
    f = usage_file(out_dir)
    month = datetime.date.today().strftime("%Y-%m")
    if f.exists():
        u = json.loads(f.read_text())
        if u.get("month") == month:
            return u
    return {"month": month, "spent_usd": 0.0, "rows": 0}


def save_usage(out_dir: pathlib.Path, u: dict):
    usage_file(out_dir).write_text(json.dumps(u, indent=2), encoding="utf-8")


def call(b64: str, path: str, params: dict) -> dict:
    time.sleep(RATE_DELAY)
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(f"{API_BASE}/{path}?{qs}",
                                 headers={"Authorization": f"Basic {b64}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def cache_path(out_dir, path, params):
    key = hashlib.md5((path + json.dumps(params, sort_keys=True)).encode()).hexdigest()[:12]
    return out_dir / f"spyfu-{path.split('/')[-1]}-{key}.json"


def run(b64, path, cpm, params, args, distill):
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cpath = cache_path(out_dir, path, params)

    if cpath.exists() and (time.time() - cpath.stat().st_mtime) / 86400.0 <= args.ttl:
        print(f"↩ cache hit (<{args.ttl}д): {cpath} — без расходов", file=sys.stderr)
        distill(json.loads(cpath.read_text(encoding="utf-8")))
        return

    u = load_usage(out_dir)
    if u["spent_usd"] >= args.budget and not args.force:
        sys.exit(f"ERROR: месячный бюджет SpyFu исчерпан "
                 f"(${u['spent_usd']:.2f}/${args.budget}, месяц {u['month']}). --force чтобы продолжить.")

    resp = call(b64, path, params)
    if isinstance(resp, dict) and resp.get("status") == 400:
        sys.exit(f"ERROR SpyFu: {resp.get('errors', resp.get('title'))}")
    rows = len(resp.get("results", [])) if isinstance(resp, dict) else 0
    cost = rows / 1000.0 * cpm
    u["spent_usd"] = round(u["spent_usd"] + cost, 4)
    u["rows"] += rows
    save_usage(out_dir, u)
    cpath.write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {rows} строк, ~${cost:.4f} (CPM ${cpm}); месяц: ${u['spent_usd']:.2f}/${args.budget} → {cpath}",
          file=sys.stderr)
    distill(resp)


def d_domain_stats(resp):
    rows = resp.get("results", []) if isinstance(resp, dict) else []
    print(f"domain: {resp.get('domain','')}")
    print("| мес | organic clicks | organic results | paid clicks | бюджет PPC $ | strength |")
    print("|---|---|---|---|---|---|")
    for r in rows[-12:]:  # последние 12 месяцев максимум
        print(f"| {r.get('searchYear')}-{r.get('searchMonth'):02d} | {r.get('monthlyOrganicClicks')} | "
              f"{r.get('totalOrganicResults')} | {r.get('monthlyPaidClicks')} | "
              f"{r.get('monthlyBudget')} | {r.get('strength')} |")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["usage", "domain-stats", "raw"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--all", action="store_true", help="domain-stats: вся история (дороже)")
    ap.add_argument("--cc", default="US", help="countryCode: US|GB|CA|DE|FR|AU... (НЕ RU)")
    ap.add_argument("--budget", type=float, default=40, help="месячный бюджет $ (Pro=$40)")
    ap.add_argument("--ttl", type=float, default=30)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--cpm", type=float, default=0.50, help="для raw: CPM эндпоинта")
    ap.add_argument("--param", action="append", default=[], help="для raw: k=v (повторяемо)")
    ap.add_argument("--out", default="./seo/research/spyfu")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out)

    if args.cmd == "usage":
        out_dir.mkdir(parents=True, exist_ok=True)
        u = load_usage(out_dir)
        print(f"SpyFu usage за {u['month']}: ${u['spent_usd']:.2f}/${args.budget} "
              f"({u['rows']} строк). Точная сверка: spyfu.com/account/api")
        return 0

    b64 = load_auth()

    if args.cmd == "domain-stats":
        if not args.args:
            sys.exit("ERROR: domain-stats требует DOMAIN")
        key = "domain-stats-all" if args.all else "domain-stats-latest"
        path, cpm = ENDPOINTS[key]
        run(b64, path, cpm, {"domain": args.args[0], "countryCode": args.cc}, args, d_domain_stats)
    elif args.cmd == "raw":
        if not args.args:
            sys.exit("ERROR: raw требует PATH (напр. competitors_api/v2/...)")
        params = dict(p.split("=", 1) for p in args.param)
        run(b64, args.args[0], args.cpm, params, args,
            lambda r: print(json.dumps(r, ensure_ascii=False, indent=2)[:2000]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
