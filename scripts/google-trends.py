#!/usr/bin/env python3
"""
google-trends.py — Google Trends data через pytrends (free, без OAuth).

Опциональная зависимость: pip3 install pytrends. Скрипт ловит ImportError
и подсказывает установить. Выход — JSON для подстановки в Phase 2 цикла.

Использование:
    python3 google-trends.py "минеральная вата" --geo RU
    python3 google-trends.py "minwool" --geo US --period 12-m
    python3 google-trends.py "плиточный клей" --geo RU --related --output 02c-trends.json

Опции:
    seed              Главная фраза (или несколько через запятую)
    --geo CODE        Регион (RU, US, GB, DE, ...). По умолчанию RU
    --period P        Период: 1-h, 4-h, 1-d, 7-d, 1-m, 3-m, 12-m, 5-y, all. Default 12-m
    --related         Также собрать related_queries (top + rising)
    --output PATH     Сохранить JSON в файл (иначе stdout)

Что возвращает:
    {
      "seed": "...",
      "geo": "RU",
      "period": "12-m",
      "interest_over_time": [{"date": "2025-06-01", "value": 80}, ...],
      "seasonality_peak_month": 9,   # месяц с пиком (1-12)
      "related_top": ["...", ...],   # если --related
      "related_rising": ["...", ...]
    }
"""

from __future__ import annotations
import argparse, json, sys, pathlib, statistics
from datetime import datetime


def try_import_pytrends():
    try:
        from pytrends.request import TrendReq
        return TrendReq
    except ImportError:
        print("ERROR: pytrends не установлен.", file=sys.stderr)
        print("  Установи: pip3 install pytrends", file=sys.stderr)
        sys.exit(2)


def fetch_trends(seeds: list[str], geo: str, period: str, want_related: bool) -> dict:
    TrendReq = try_import_pytrends()
    pytrends = TrendReq(hl="ru-RU" if geo == "RU" else "en-US", tz=180)

    result = {"seeds": seeds, "geo": geo, "period": period}

    pytrends.build_payload(seeds, cat=0, timeframe=period, geo=geo, gprop="")

    iot = pytrends.interest_over_time()
    if iot is not None and not iot.empty:
        rows = []
        seed = seeds[0]
        for idx, row in iot.iterrows():
            val = int(row.get(seed, 0))
            rows.append({"date": idx.strftime("%Y-%m-%d"), "value": val})
        result["interest_over_time"] = rows

        # Сезонность: месяц с самым высоким средним значением
        by_month: dict[int, list[int]] = {}
        for r in rows:
            m = datetime.strptime(r["date"], "%Y-%m-%d").month
            by_month.setdefault(m, []).append(r["value"])
        if by_month:
            avg_by_month = {m: statistics.mean(vs) for m, vs in by_month.items()}
            peak = max(avg_by_month.items(), key=lambda x: x[1])
            result["seasonality_peak_month"] = peak[0]
            result["seasonality_peak_value"] = round(peak[1], 1)

    if want_related:
        try:
            rel = pytrends.related_queries()
            seed = seeds[0]
            top_df = rel.get(seed, {}).get("top")
            rising_df = rel.get(seed, {}).get("rising")
            if top_df is not None:
                result["related_top"] = top_df["query"].tolist()[:25]
            if rising_df is not None:
                result["related_rising"] = rising_df["query"].tolist()[:25]
        except Exception as e:
            print(f"⚠ related_queries failed: {e}", file=sys.stderr)

    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seed", help="Главная фраза (или через запятую для multi)")
    ap.add_argument("--geo", default="RU", help="Регион (default: RU)")
    ap.add_argument("--period", default="12-m",
                    choices=["1-h","4-h","1-d","7-d","1-m","3-m","12-m","5-y","all"],
                    help="Период (default: 12-m)")
    ap.add_argument("--related", action="store_true", help="Собрать related_queries")
    ap.add_argument("--output", type=pathlib.Path, help="JSON в файл (иначе stdout)")
    args = ap.parse_args()

    seeds = [s.strip() for s in args.seed.split(",") if s.strip()][:5]
    if not seeds:
        ap.error("empty seed")

    data = fetch_trends(seeds, args.geo, args.period, args.related)
    out = json.dumps(data, ensure_ascii=False, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out, encoding="utf-8")
        print(f"✓ Saved → {args.output}", file=sys.stderr)
    else:
        print(out)


if __name__ == "__main__":
    main()
