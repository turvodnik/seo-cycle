#!/usr/bin/env python3
"""
metrika-fetch.py — Яндекс.Метрика Stats API клиент.

Использует OAuth токен (env YANDEX_OAUTH_TOKEN) и counter ID (env
YANDEX_METRIKA_COUNTER_ID). Чистый HTTP без зависимостей.

API docs: https://yandex.ru/dev/metrika/doc/api2/api_v1/intro.html

Использование:
    python3 metrika-fetch.py --days 28 > metrika-raw.json
    python3 metrika-fetch.py --counter 123456 --days 90 --output metrika.json

В pipeline:
    python3 metrika-fetch.py --days 28 | \
      python3 snapshot-build.py --source metrika --output snapshot.json --merge

Опции:
    --counter ID            Counter ID (env YANDEX_METRIKA_COUNTER_ID)
    --token TOKEN           OAuth (env YANDEX_OAUTH_TOKEN)
    --days N                Период (default: 28)
    --start-date YYYY-MM-DD / --end-date YYYY-MM-DD
    --dimensions LIST       Comma-separated (default: ym:pv:URL)
    --metrics LIST          Comma-separated (default: ym:pv:visits,ym:pv:bounceRate,ym:pv:avgVisitDurationSeconds)
    --limit N               (default: 1000)
    --output PATH

OAuth токен: https://oauth.yandex.ru/ → создать приложение → permissions
«Яндекс.Метрика: получать показатели» → token через code flow.
"""

from __future__ import annotations
import argparse, json, os, pathlib, sys, urllib.parse, urllib.request
from datetime import date, timedelta
from urllib.error import HTTPError


API_BASE = "https://api-metrika.yandex.net/stat/v1/data"


def fetch(counter: str, token: str, start: str, end: str,
          dimensions: str, metrics: str, limit: int) -> dict:
    params = {
        "ids": counter,
        "date1": start,
        "date2": end,
        "dimensions": dimensions,
        "metrics": metrics,
        "limit": limit,
        "accuracy": "full",
    }
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"OAuth {token}",
        "Accept": "application/json",
        "User-Agent": "seo-cycle/1.1 metrika-fetch",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"⚠ HTTP {e.code}: {body[:300]}", file=sys.stderr)
        raise


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--counter", default=os.environ.get("YANDEX_METRIKA_COUNTER_ID"))
    ap.add_argument("--token", default=os.environ.get("YANDEX_OAUTH_TOKEN"))
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--start-date")
    ap.add_argument("--end-date")
    ap.add_argument("--dimensions", default="ym:pv:URL")
    ap.add_argument("--metrics", default="ym:pv:visits,ym:pv:bounceRate,ym:pv:avgVisitDurationSeconds")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--output", type=pathlib.Path)
    args = ap.parse_args()

    if not args.counter:
        ap.error("Provide --counter or set YANDEX_METRIKA_COUNTER_ID env var")
    if not args.token:
        ap.error("Provide --token or set YANDEX_OAUTH_TOKEN env var")

    if args.start_date and args.end_date:
        start, end = args.start_date, args.end_date
    else:
        end_d = date.today()
        start_d = end_d - timedelta(days=args.days)
        start, end = start_d.isoformat(), end_d.isoformat()

    print(f"Metrika fetch: counter={args.counter} {start} → {end}", file=sys.stderr)
    try:
        data = fetch(args.counter, args.token, start, end,
                     args.dimensions, args.metrics, args.limit)
    except Exception as e:
        print(f"ERROR: Metrika API failed: {e}", file=sys.stderr)
        sys.exit(1)

    rows = data.get("data", [])
    print(f"✓ {len(rows)} rows", file=sys.stderr)

    out = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out)


if __name__ == "__main__":
    main()
