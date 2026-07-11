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


def api_get(path: str, token: str) -> dict:
    req = urllib.request.Request(f"{API_BASE}{path}", headers={
        "Authorization": f"OAuth {token}",
        "Accept": "application/json",
        "User-Agent": "seo-cycle/1.1 webmaster-fetch",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def normalize_domain(value: str) -> str:
    v = (value or "").strip().lower()
    v = v.split("//")[-1].split("/")[0].split(":")[0]
    return v[4:] if v.startswith("www.") else v


def pick_host(hosts: list, domain: str) -> tuple:
    """(host_id, why_not): верифицированный host по домену; без домена —
    единственный верифицированный. Кандидаты https предпочитаются http."""
    verified = [h for h in hosts if h.get("verified")]
    pool = verified or list(hosts)
    if domain:
        want = normalize_domain(domain)
        matched = [h for h in pool if normalize_domain(
            h.get("unicode_host_url") or h.get("ascii_host_url") or h.get("host_id", "")) == want]
        if not matched:
            return None, f"домен {want} не найден среди {len(pool)} хостов аккаунта"
        https = [h for h in matched if str(h.get("host_id", "")).startswith("https")]
        return (https or matched)[0].get("host_id"), ""
    if len(pool) == 1:
        return pool[0].get("host_id"), ""
    return None, f"{len(pool)} хостов в аккаунте — укажите --domain или --host"


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
    ap.add_argument("--domain", default="", help="Домен проекта для автоподбора host_id (когда --host не задан)")
    ap.add_argument("--token", default=os.environ.get("YANDEX_WEBMASTER_OAUTH_TOKEN") or os.environ.get("YANDEX_OAUTH_TOKEN"))
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--start-date")
    ap.add_argument("--end-date")
    ap.add_argument("--order-by", default="TOTAL_SHOWS",
                    choices=["TOTAL_SHOWS", "TOTAL_CLICKS"])
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--output", type=pathlib.Path)
    args = ap.parse_args()

    if not args.token:
        ap.error("Provide --token or set YANDEX_OAUTH_TOKEN env var")
    # zero-config: user_id и host_id выводимы из API по одному токену
    if not args.user_id:
        try:
            args.user_id = str(api_get("/user/", args.token).get("user_id") or "")
        except Exception as e:
            print(f"⚠ авто-user_id не удался: {e}", file=sys.stderr)
        if args.user_id:
            print(f"↪ user_id обнаружен по токену: {args.user_id}", file=sys.stderr)
    if args.user_id and not args.host:
        try:
            hosts = api_get(f"/user/{args.user_id}/hosts/", args.token).get("hosts", [])
            host_id, why_not = pick_host(hosts, args.domain)
            if host_id:
                args.host = host_id
                print(f"↪ host обнаружен: {host_id}", file=sys.stderr)
            else:
                print(f"⚠ авто-host: {why_not}", file=sys.stderr)
        except Exception as e:
            print(f"⚠ авто-host не удался: {e}", file=sys.stderr)
    if not args.user_id:
        ap.error("Provide --user-id or set YANDEX_USER_ID env var")
    if not args.host:
        ap.error("Provide --host or set YANDEX_WEBMASTER_HOST_ID env var")

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
