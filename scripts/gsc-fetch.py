#!/usr/bin/env python3
"""
gsc-fetch.py — Search Console API клиент через service account.

Вызывает GSC searchanalytics.query → возвращает rows по query + page с
impressions/clicks/ctr/position. Output совместим с snapshot-build.py --source gsc.

Установка зависимости (опционально):
    pip3 install google-api-python-client google-auth

Аутентификация: service account JSON в env GOOGLE_APPLICATION_CREDENTIALS,
либо ADC (gcloud auth application-default login). Site URL — в env GSC_SITE_URL
или через --site (формат: sc-domain:example.com или https://example.com/).

Использование:
    python3 gsc-fetch.py --days 90 > gsc-raw.json
    python3 gsc-fetch.py --site sc-domain:example.com --days 28 --output gsc.json
    python3 gsc-fetch.py --start-date 2026-01-01 --end-date 2026-03-01 --dimensions query,page

В pipeline:
    python3 gsc-fetch.py --days 90 | \
      python3 snapshot-build.py --source gsc --output snapshot.json --merge

Опции:
    --site URL           sc-domain:... или https://... (env GSC_SITE_URL)
    --days N             Период от сегодня (default: 28)
    --start-date YYYY-MM-DD / --end-date YYYY-MM-DD  Точный период
    --dimensions LIST    Comma-separated: query,page,country,device (default: query,page)
    --row-limit N        До 25000 (default: 5000)
    --output PATH        JSON в файл (default: stdout)
"""

from __future__ import annotations
import argparse, json, os, pathlib, sys
from datetime import date, timedelta


def _import_deps():
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
        from google.auth import default as adc_default
        return build, service_account, adc_default
    except ImportError:
        print("ERROR: google-api-python-client не установлен.", file=sys.stderr)
        print("  pip3 install google-api-python-client google-auth", file=sys.stderr)
        sys.exit(2)


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def get_credentials():
    build, service_account, adc_default = _import_deps()
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path and pathlib.Path(creds_path).exists():
        return service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    # Fallback на ADC
    creds, _ = adc_default(scopes=SCOPES)
    return creds


def fetch(site: str, start: str, end: str, dimensions: list[str], row_limit: int) -> dict:
    build, _, _ = _import_deps()
    creds = get_credentials()
    service = build("searchconsole", "v1", credentials=creds)
    request = {
        "startDate": start,
        "endDate": end,
        "dimensions": dimensions,
        "rowLimit": min(row_limit, 25000),
        "dataState": "final",
    }
    return service.searchanalytics().query(siteUrl=site, body=request).execute()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default=os.environ.get("GSC_SITE_URL"))
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--start-date")
    ap.add_argument("--end-date")
    ap.add_argument("--dimensions", default="query,page")
    ap.add_argument("--row-limit", type=int, default=5000)
    ap.add_argument("--output", type=pathlib.Path)
    args = ap.parse_args()

    if not args.site:
        ap.error("Provide --site or set GSC_SITE_URL env var")

    if args.start_date and args.end_date:
        start, end = args.start_date, args.end_date
    else:
        end_d = date.today() - timedelta(days=3)  # GSC лагает ~3 дня
        start_d = end_d - timedelta(days=args.days)
        start, end = start_d.isoformat(), end_d.isoformat()

    dimensions = [d.strip() for d in args.dimensions.split(",") if d.strip()]

    print(f"GSC fetch: {args.site} {start} → {end}, dims={dimensions}", file=sys.stderr)
    try:
        data = fetch(args.site, start, end, dimensions, args.row_limit)
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: GSC API failed: {e}", file=sys.stderr)
        sys.exit(1)

    rows = data.get("rows", [])
    print(f"✓ {len(rows)} rows", file=sys.stderr)

    out = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out)


if __name__ == "__main__":
    main()
