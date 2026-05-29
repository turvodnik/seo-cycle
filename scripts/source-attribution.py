#!/usr/bin/env python3
"""
source-attribution.py — замыкает цикл обратной связи: какой источник семантики
(Wordstat / GSC / NeuronWriter / LLM-CLI / ATP / suggest / Perplexity) дал ключи,
которые реально вышли в топ. Позволяет отключать малоэффективные источники —
это и качество стратегии, и экономия токенов/времени на бесполезный сбор.

Вход:
  1. source-attribution.csv — лог «ключ → источник» (keyword,source,date_added,
     cluster,target_url). Заполняется в Phase 2: помечай, откуда пришёл ключ.
  2. snapshot JSON (Phase 9, формат snapshot-build.py): queries[] с position,
     clicks, impressions.

Выход: таблица по источникам (сколько ключей, в топ-10/топ-3, клики, ср. позиция)
+ рекомендации, какие источники кандидаты на отключение.

Использование:
    python3 source-attribution.py --csv seo/source-attribution.csv \
            --snapshot seo/monitoring/<date>-snapshot.json [--min-sample 5]
"""

from __future__ import annotations
import argparse, csv, json, pathlib, re, sys
from collections import defaultdict


def norm(q: str) -> str:
    q = (q or "").strip().lower().replace("ё", "е")
    return re.sub(r"\s+", " ", q)


def load_attribution(path: pathlib.Path) -> dict[str, set[str]]:
    """norm(keyword) → множество источников."""
    kw_sources: dict[str, set[str]] = defaultdict(set)
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            kw = norm(row.get("keyword", ""))
            src = (row.get("source") or "").strip()
            if kw and src:
                kw_sources[kw].add(src)
    return kw_sources


def load_snapshot(path: pathlib.Path) -> dict[str, dict]:
    """norm(query) → {position, clicks, impressions} (лучшая позиция при дублях)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    # snapshot может быть {engine:..., queries:[...]} или {merged: {queries:[...]}}
    queries = data.get("queries") or data.get("merged", {}).get("queries") or []
    out: dict[str, dict] = {}
    for q in queries:
        k = norm(q.get("query", ""))
        if not k:
            continue
        pos = float(q.get("position", 0) or 0)
        rec = out.get(k)
        if rec is None or (pos and pos < rec["position"]):
            out[k] = {"position": pos,
                      "clicks": int(q.get("clicks", 0) or 0),
                      "impressions": int(q.get("impressions", 0) or 0)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--min-sample", type=int, default=5,
                    help="мин. ключей от источника, чтобы судить об эффективности")
    args = ap.parse_args()

    csv_path, snap_path = pathlib.Path(args.csv), pathlib.Path(args.snapshot)
    for p in (csv_path, snap_path):
        if not p.exists():
            print(f"ERROR: нет файла {p}", file=sys.stderr)
            return 2

    kw_sources = load_attribution(csv_path)
    snap = load_snapshot(snap_path)
    if not kw_sources:
        print("source-attribution.csv пуст — нечего анализировать. Заполняй лог в Phase 2.")
        return 0

    # Агрегация по источнику
    agg: dict[str, dict] = defaultdict(lambda: {"kw": 0, "ranked": 0, "top10": 0,
                                                "top3": 0, "clicks": 0, "impr": 0,
                                                "pos_sum": 0.0})
    for kw, sources in kw_sources.items():
        snr = snap.get(kw)
        for src in sources:
            a = agg[src]
            a["kw"] += 1
            if snr and snr["position"] > 0:
                a["ranked"] += 1
                a["pos_sum"] += snr["position"]
                a["clicks"] += snr["clicks"]
                a["impr"] += snr["impressions"]
                if snr["position"] <= 10:
                    a["top10"] += 1
                if snr["position"] <= 3:
                    a["top3"] += 1

    # Отчёт
    print("== Source attribution: эффективность источников семантики ==\n")
    hdr = f"{'источник':<18}{'ключей':>7}{'в топ-10':>9}{'в топ-3':>8}{'клики':>7}{'ср.поз':>8}"
    print(hdr); print("-" * len(hdr))
    rows = sorted(agg.items(), key=lambda kv: kv[1]["top10"], reverse=True)
    for src, a in rows:
        avg = a["pos_sum"] / a["ranked"] if a["ranked"] else 0
        print(f"{src:<18}{a['kw']:>7}{a['top10']:>9}{a['top3']:>8}{a['clicks']:>7}{avg:>8.1f}")

    # Рекомендации
    print("\n== Рекомендации ==")
    any_rec = False
    for src, a in rows:
        if a["kw"] >= args.min_sample and a["top10"] == 0:
            print(f"  ⚠ {src}: {a['kw']} ключей, ни один не в топ-10 → кандидат на снижение приоритета/отключение")
            any_rec = True
        elif a["kw"] >= args.min_sample and a["top10"] / a["kw"] >= 0.4:
            print(f"  ✓ {src}: высокая отдача ({a['top10']}/{a['kw']} в топ-10) → держать в приоритете")
            any_rec = True
    if not any_rec:
        print("  Недостаточно данных для выводов (мало пересечений ключей со snapshot или мал sample).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
