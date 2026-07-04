#!/usr/bin/env python3
"""
snapshot-build.py — нормализатор аналитики в единый snapshot.json для Phase 9.

Принимает JSON от делегата (claude-seo:seo-google, yandex-seo-specialist, psi)
через stdin или --input, и преобразует в единую schema:

{
  "snapshot_date": "YYYY-MM-DD",
  "period": {"start": "...", "end": "..."},
  "engine": "google|yandex",
  "source": "gsc|ga4|metrika|webmaster|psi",
  "queries": [{"query", "impressions", "clicks", "ctr", "position", "url"}],
  "pages": [{"url", "impressions", "clicks", "behavior": {"bounce", "time_on_page"}}],
  "cwv": {"lcp_p75", "inp_p75", "cls_p75", "status"},
  "behavior": {"sessions", "bounce_rate", "conversions"}
}

Объединение нескольких источников: запусти раз на источник в один snapshot,
скрипт мерджит queries[], pages[], cwv{}, behavior{} по URL/query.

Использование:
    # Из файла
    python3 snapshot-build.py --source gsc --input gsc-export.json --output snapshot.json

    # Из stdin
    cat gsc-export.json | python3 snapshot-build.py --source gsc --output snapshot.json

    # Мердж: запускай по очереди, скрипт читает существующий output и расширяет
    python3 snapshot-build.py --source gsc --input gsc.json --output snapshot.json
    python3 snapshot-build.py --source ga4 --input ga4.json --output snapshot.json --merge
    python3 snapshot-build.py --source psi --input psi.json --output snapshot.json --merge

Опции:
    --source NAME        gsc | ga4 | metrika | webmaster | psi (required)
    --input PATH         JSON файл (иначе stdin)
    --output PATH        snapshot.json (по умолчанию 09-monitoring/YYYY-MM-DD-snapshot.json)
    --merge              Слить с существующим output вместо перезаписи
    --period START END   Период YYYY-MM-DD YYYY-MM-DD (для метаданных)
"""

from __future__ import annotations
import argparse, json, pathlib, sys
from datetime import date


def _load_input(args) -> dict:
    if args.input:
        return json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
    return json.load(sys.stdin)


def _empty_snapshot(args) -> dict:
    today = date.today().isoformat()
    return {
        "snapshot_date": today,
        "period": {
            "start": args.period[0] if args.period else None,
            "end": args.period[1] if args.period else today,
        },
        "sources": [],
        "queries": [],
        "pages": [],
        "cwv": {},
        "behavior": {},
    }


# ----- Нормализаторы по источникам ---------------------------------------

def from_gsc(raw: dict) -> dict:
    """GSC выгрузка: rows c keys [query, page], clicks, impressions, ctr, position"""
    out = {"engine": "google", "source": "gsc", "queries": [], "pages": []}
    rows = raw.get("rows") or raw.get("data") or []
    seen_pages: dict[str, dict] = {}
    for r in rows:
        keys = r.get("keys", [])
        query = keys[0] if keys else r.get("query", "")
        page = keys[1] if len(keys) > 1 else r.get("page", "")
        rec = {
            "query": query,
            "impressions": int(r.get("impressions", 0)),
            "clicks": int(r.get("clicks", 0)),
            "ctr": float(r.get("ctr", 0.0)),
            "position": float(r.get("position", 0.0)),
            "url": page,
        }
        out["queries"].append(rec)
        if page:
            p = seen_pages.setdefault(page, {"url": page, "impressions": 0, "clicks": 0})
            p["impressions"] += rec["impressions"]
            p["clicks"] += rec["clicks"]
    out["pages"] = list(seen_pages.values())
    return out


def from_ga4(raw: dict) -> dict:
    """GA4: rows c pagePath, sessions, bounceRate, averageEngagementTime, conversions"""
    out = {"engine": "google", "source": "ga4", "pages": [], "behavior": {}}
    rows = raw.get("rows", [])
    total_sessions = 0
    total_conversions = 0
    bounce_rates = []
    for r in rows:
        dims = r.get("dimensionValues", []) or [{"value": r.get("pagePath", "")}]
        metrics = r.get("metricValues", [])
        url = dims[0].get("value", "") if dims else ""
        # metrics index по порядку запроса в API; для гибкости — пытаемся по namedDimensions
        sessions = int(float(metrics[0].get("value", 0))) if metrics else int(r.get("sessions", 0))
        bounce = float(metrics[1].get("value", 0.0)) if len(metrics) > 1 else float(r.get("bounceRate", 0))
        engage = float(metrics[2].get("value", 0.0)) if len(metrics) > 2 else float(r.get("averageEngagementTime", 0))
        conv = int(float(metrics[3].get("value", 0))) if len(metrics) > 3 else int(r.get("conversions", 0))
        out["pages"].append({
            "url": url,
            "sessions": sessions,
            "behavior": {"bounce": bounce, "time_on_page": engage, "conversions": conv},
        })
        total_sessions += sessions
        total_conversions += conv
        bounce_rates.append(bounce)
    if bounce_rates:
        out["behavior"] = {
            "sessions": total_sessions,
            "bounce_rate": round(sum(bounce_rates) / len(bounce_rates), 4),
            "conversions": total_conversions,
        }
    return out


def from_metrika(raw: dict) -> dict:
    """Я.Метрика: visits, bounceRate, avgVisitDurationSeconds, goals"""
    out = {"engine": "yandex", "source": "metrika", "pages": [], "behavior": {}}
    rows = raw.get("data", raw.get("rows", []))
    total_visits = 0
    bounces = []
    for r in rows:
        dims = r.get("dimensions", [])
        metrics = r.get("metrics", [])
        url = dims[0].get("name", "") if dims else r.get("url", "")
        visits = int(metrics[0]) if metrics else int(r.get("visits", 0))
        bounce = float(metrics[1]) if len(metrics) > 1 else float(r.get("bounceRate", 0))
        avg_dur = int(metrics[2]) if len(metrics) > 2 else int(r.get("avgVisitDurationSeconds", 0))
        out["pages"].append({
            "url": url,
            "sessions": visits,
            "behavior": {"bounce": bounce, "time_on_page": avg_dur},
        })
        total_visits += visits
        bounces.append(bounce)
    if bounces:
        out["behavior"] = {
            "sessions": total_visits,
            "bounce_rate": round(sum(bounces) / len(bounces), 4),
        }
    return out


def from_webmaster(raw: dict) -> dict:
    """Я.Вебмастер «История запросов»: плоский экспорт ИЛИ сырой API v4
    (webmaster-fetch.py: query_text + indicators.TOTAL_SHOWS/TOTAL_CLICKS/AVG_SHOW_POSITION)."""
    out = {"engine": "yandex", "source": "webmaster", "queries": []}
    rows = raw.get("queries", raw.get("rows", []))
    for r in rows:
        indicators = r.get("indicators") or {}
        query = r.get("query") or r.get("query_text") or r.get("name", "")
        if not query:
            continue
        out["queries"].append({
            "query": query,
            "impressions": int(r.get("shows", r.get("impressions", indicators.get("TOTAL_SHOWS", 0)))),
            "clicks": int(r.get("clicks", indicators.get("TOTAL_CLICKS", 0))),
            "ctr": float(r.get("ctr", 0.0)),
            "position": float(r.get("position",
                                    r.get("avgPosition", indicators.get("AVG_SHOW_POSITION", 0.0)))),
            "url": r.get("url", ""),
        })
    return out


def from_psi(raw: dict) -> dict:
    """PageSpeed Insights: lighthouseResult + loadingExperience с CWV"""
    out = {"engine": "google", "source": "psi", "cwv": {}}
    le = raw.get("loadingExperience", {})
    metrics = le.get("metrics", {})

    def _get(key, p="percentile", default=0):
        return metrics.get(key, {}).get(p, default)

    lcp = _get("LARGEST_CONTENTFUL_PAINT_MS", default=None)
    inp = _get("INTERACTION_TO_NEXT_PAINT", default=None)
    cls_raw = _get("CUMULATIVE_LAYOUT_SHIFT_SCORE", default=None)
    cls = round(cls_raw / 100, 3) if cls_raw is not None else None

    if lcp is not None:
        out["cwv"]["lcp_p75"] = lcp
    if inp is not None:
        out["cwv"]["inp_p75"] = inp
    if cls is not None:
        out["cwv"]["cls_p75"] = cls

    # Статус: good если все три в зелёной зоне
    def _status():
        good = []
        if lcp is not None: good.append(lcp <= 2500)
        if inp is not None: good.append(inp <= 200)
        if cls is not None: good.append(cls <= 0.1)
        if not good: return "unknown"
        if all(good): return "good"
        return "poor" if not any(good) else "needs_improvement"
    out["cwv"]["status"] = _status()

    if "id" in raw:
        out["cwv"]["url"] = raw["id"]
    return out


NORMALIZERS = {
    "gsc": from_gsc,
    "ga4": from_ga4,
    "metrika": from_metrika,
    "webmaster": from_webmaster,
    "psi": from_psi,
}


def _merge_snapshot(base: dict, addition: dict) -> dict:
    """Объединяем queries/pages по (query+url) / url, cwv/behavior подменяем целиком."""
    base.setdefault("sources", [])
    src_meta = {"source": addition.get("source"), "engine": addition.get("engine")}
    if src_meta not in base["sources"]:
        base["sources"].append(src_meta)

    # queries
    if addition.get("queries"):
        idx = {(q["query"], q.get("url", "")): q for q in base.get("queries", [])}
        for q in addition["queries"]:
            key = (q["query"], q.get("url", ""))
            if key in idx:
                idx[key].update(q)
            else:
                idx[key] = q
        base["queries"] = list(idx.values())

    # pages
    if addition.get("pages"):
        idx = {p["url"]: p for p in base.get("pages", [])}
        for p in addition["pages"]:
            url = p.get("url", "")
            if url in idx:
                # глубокий merge поведения
                idx[url].update({k: v for k, v in p.items() if k != "behavior"})
                if "behavior" in p:
                    idx[url].setdefault("behavior", {}).update(p["behavior"])
            else:
                idx[url] = p
        base["pages"] = list(idx.values())

    # cwv: per-URL если в addition есть url, иначе перезаписываем общий
    if addition.get("cwv"):
        url = addition["cwv"].get("url")
        if url:
            base.setdefault("cwv_per_url", {})[url] = addition["cwv"]
        else:
            base["cwv"] = addition["cwv"]

    if addition.get("behavior"):
        base["behavior"] = addition["behavior"]

    return base


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, choices=list(NORMALIZERS.keys()))
    ap.add_argument("--input", type=pathlib.Path, help="JSON файл (default: stdin)")
    ap.add_argument("--output", type=pathlib.Path, help="snapshot.json")
    ap.add_argument("--merge", action="store_true", help="Merge с существующим output")
    ap.add_argument("--period", nargs=2, metavar=("START","END"))
    args = ap.parse_args()

    if not args.output:
        args.output = pathlib.Path(f"09-monitoring/{date.today().isoformat()}-snapshot.json")

    raw = _load_input(args)
    normalized = NORMALIZERS[args.source](raw)

    if args.merge and args.output.exists():
        snapshot = json.loads(args.output.read_text(encoding="utf-8"))
    else:
        snapshot = _empty_snapshot(args)

    _merge_snapshot(snapshot, normalized)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ {args.source} → {args.output}", file=sys.stderr)
    print(f"  queries: {len(snapshot.get('queries', []))}, pages: {len(snapshot.get('pages', []))}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
