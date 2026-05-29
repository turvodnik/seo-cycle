#!/usr/bin/env python3
"""
ga4-fetch.py — Google Analytics 4 Data API клиент через service account.

Вызывает GA4 runReport → возвращает rows по pagePath + поведенческими метриками.
Output совместим с snapshot-build.py --source ga4.

Установка (опц.):
    pip3 install google-analytics-data google-auth

Аутентификация: service account JSON в GOOGLE_APPLICATION_CREDENTIALS.
В GA4 нужно добавить service account как Viewer на property.

Property ID — в env GA4_PROPERTY_ID (числовой ID property, не measurement ID).

Использование:
    python3 ga4-fetch.py --days 28 > ga4-raw.json
    python3 ga4-fetch.py --property 123456789 --days 90 --output ga4.json

В pipeline:
    python3 ga4-fetch.py --days 28 | \
      python3 snapshot-build.py --source ga4 --output snapshot.json --merge

Опции:
    --property ID        GA4 property ID (env GA4_PROPERTY_ID)
    --days N             Период от сегодня (default: 28)
    --start-date YYYY-MM-DD / --end-date YYYY-MM-DD
    --dimensions LIST    Comma-separated GA4 dimension names (default: pagePath)
    --metrics LIST       (default: sessions,bounceRate,averageEngagementTime,conversions)
    --limit N            (default: 1000)
    --output PATH
"""

from __future__ import annotations
import argparse, json, os, pathlib, sys
from datetime import date, timedelta


def _import_deps():
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest, OrderBy,
        )
        from google.oauth2 import service_account
        return BetaAnalyticsDataClient, DateRange, Dimension, Metric, RunReportRequest, OrderBy, service_account
    except ImportError:
        print("ERROR: google-analytics-data не установлен.", file=sys.stderr)
        print("  pip3 install google-analytics-data google-auth", file=sys.stderr)
        sys.exit(2)


def fetch(property_id: str, start: str, end: str,
          dimensions: list[str], metrics: list[str], limit: int) -> dict:
    Client, DateRange, Dimension, Metric, RunReportRequest, OrderBy, sa = _import_deps()
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path and pathlib.Path(creds_path).exists():
        credentials = sa.Credentials.from_service_account_file(creds_path)
    else:
        credentials = None  # ADC
    client = Client(credentials=credentials) if credentials else Client()

    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start, end_date=end)],
        limit=limit,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name=metrics[0]), desc=True)],
    )
    response = client.run_report(request)

    # Конвертация proto → dict
    return {
        "rows": [
            {
                "dimensionValues": [{"value": v.value} for v in r.dimension_values],
                "metricValues": [{"value": v.value} for v in r.metric_values],
            }
            for r in response.rows
        ],
        "dimensionHeaders": [{"name": h.name} for h in response.dimension_headers],
        "metricHeaders": [{"name": h.name, "type": h.type_.name} for h in response.metric_headers],
        "rowCount": response.row_count,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--property", default=os.environ.get("GA4_PROPERTY_ID"))
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--start-date")
    ap.add_argument("--end-date")
    ap.add_argument("--dimensions", default="pagePath")
    ap.add_argument("--metrics", default="sessions,bounceRate,averageEngagementTime,conversions")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--output", type=pathlib.Path)
    args = ap.parse_args()

    if not args.property:
        ap.error("Provide --property or set GA4_PROPERTY_ID env var")

    if args.start_date and args.end_date:
        start, end = args.start_date, args.end_date
    else:
        end_d = date.today()
        start_d = end_d - timedelta(days=args.days)
        start, end = start_d.isoformat(), end_d.isoformat()

    dimensions = [d.strip() for d in args.dimensions.split(",") if d.strip()]
    metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]

    print(f"GA4 fetch: property={args.property} {start} → {end}", file=sys.stderr)
    try:
        data = fetch(args.property, start, end, dimensions, metrics, args.limit)
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: GA4 API failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"✓ {data.get('rowCount', 0)} rows", file=sys.stderr)
    out = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out)


if __name__ == "__main__":
    main()
