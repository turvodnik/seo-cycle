#!/usr/bin/env python3
"""
webmaster-fetch.py — Яндекс.Вебмастер API клиент.

Использует OAuth токен (env YANDEX_WEBMASTER_OAUTH_TOKEN или
YANDEX_OAUTH_TOKEN) + host_id (env YANDEX_WEBMASTER_HOST_ID /
YANDEX_HOST_ID, либо --host) + user_id (env YANDEX_WEBMASTER_USER_ID /
YANDEX_USER_ID).

Получает popular search queries за период (аналог GSC «История запросов»).
Output совместим с snapshot-build.py --source webmaster.

API docs: https://yandex.ru/dev/webmaster/doc/dg/concepts/about.html

Получение user_id:
    curl -H "Authorization: OAuth $YANDEX_OAUTH_TOKEN" \
        https://api.webmaster.yandex.net/v4/user/

Получение host_id:
    curl -H "Authorization: OAuth $YANDEX_OAUTH_TOKEN" \
        https://api.webmaster.yandex.net/v4/user/<USER_ID>/hosts/

Использование:
    python3 webmaster-fetch.py --days 28 > webmaster-raw.json
    python3 webmaster-fetch.py --host https:example.com:443 --days 90 --output webmaster.json

В pipeline:
    python3 webmaster-fetch.py --days 28 | \
      python3 snapshot-build.py --source webmaster --output snapshot.json --merge

Опции:
    --user-id ID            Yandex user ID (env YANDEX_WEBMASTER_USER_ID / YANDEX_USER_ID)
    --host HOST_ID          Host ID в формате https:example.com:443 (env YANDEX_WEBMASTER_HOST_ID)
    --token TOKEN           OAuth (env YANDEX_OAUTH_TOKEN)
    --days N                (default: 28)
    --start-date YYYY-MM-DD / --end-date YYYY-MM-DD
    --order-by              TOTAL_SHOWS (default) | TOTAL_CLICKS
    --limit N               (default: 500, max 500 на страницу)
    --output PATH
"""

from __future__ import annotations
import argparse, json, os, pathlib, sys, urllib.parse, urllib.request
from datetime import date, timedelta
from urllib.error import HTTPError


API_BASE = "https://api.webmaster.yandex.net/v4"


def fetch(user_id: str, host_id: str, token: str, start: str, end: str,
          order_by: str, limit: int) -> dict:
    params = [
        ("date_from", start),
        ("date_to", end),
        ("order_by", order_by),
        ("device_type_indicator", "ALL"),
        ("limit", min(limit, 500)),
    ]
    # Yandex Webmaster API expects repeated query_indicator params, not a CSV.
    # CSV is rejected as a single enum value by the current API.
    for indicator in ("TOTAL_SHOWS", "TOTAL_CLICKS", "AVG_SHOW_POSITION", "AVG_CLICK_POSITION"):
        params.append(("query_indicator", indicator))
    url = f"{API_BASE}/user/{user_id}/hosts/{host_id}/search-queries/popular/?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"OAuth {token}",
        "Accept": "application/json",
        "User-Agent": "seo-cycle/1.1 webmaster-fetch",
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
    ap.add_argument("--user-id", default=os.environ.get("YANDEX_WEBMASTER_USER_ID") or os.environ.get("YANDEX_USER_ID"))
    ap.add_argument("--host", default=os.environ.get("YANDEX_WEBMASTER_HOST_ID") or os.environ.get("YANDEX_HOST_ID"))
    ap.add_argument("--token", default=os.environ.get("YANDEX_WEBMASTER_OAUTH_TOKEN") or os.environ.get("YANDEX_OAUTH_TOKEN"))
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--start-date")
    ap.add_argument("--end-date")
    ap.add_argument("--order-by", default="TOTAL_SHOWS",
                    choices=["TOTAL_SHOWS", "TOTAL_CLICKS"])
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--output", type=pathlib.Path)
    args = ap.parse_args()

    if not args.user_id:
        ap.error("Provide --user-id or set YANDEX_USER_ID env var")
    if not args.host:
        ap.error("Provide --host or set YANDEX_WEBMASTER_HOST_ID env var")
    if not args.token:
        ap.error("Provide --token or set YANDEX_OAUTH_TOKEN env var")

    if args.start_date and args.end_date:
        start, end = args.start_date, args.end_date
    else:
        end_d = date.today()
        start_d = end_d - timedelta(days=args.days)
        start, end = start_d.isoformat(), end_d.isoformat()

    print(f"Webmaster fetch: host={args.host} {start} → {end}", file=sys.stderr)
    try:
        data = fetch(args.user_id, args.host, args.token, start, end,
                     args.order_by, args.limit)
    except Exception as e:
        print(f"ERROR: Webmaster API failed: {e}", file=sys.stderr)
        sys.exit(1)

    queries = data.get("queries", [])
    print(f"✓ {len(queries)} queries", file=sys.stderr)

    out = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out)


if __name__ == "__main__":
    main()
