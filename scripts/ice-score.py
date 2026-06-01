#!/usr/bin/env python3
"""
ice-score.py — приоритизация находок (конкурентный анализ, аудит, гэпы) по методу
ICE: Impact × Confidence × Ease. Каждый фактор — 1..10. Выше скор → раньше делать.

Зачем: сводит разрозненные находки (Serpstat keyword gap, SpyFu, Keys.so, local-pack,
GSC striking-distance) в один отсортированный список «что делать первым».

Вход — CSV с колонками: finding,impact,confidence,ease[,source,note]
  impact      — потенциальный эффект (трафик/деньги), 1..10
  confidence  — уверенность, что сработает, 1..10
  ease        — лёгкость внедрения (10 = очень легко), 1..10

Выход — таблица, отсортированная по ICE (desc), с рангом и зоной (🔥/✅/⏳).

Использование:
  python3 ice-score.py findings.csv
  python3 ice-score.py findings.csv --md          # markdown-таблица (для отчёта)
  python3 ice-score.py findings.csv --top 10
Формат ICE-скор: I×C×E (1..1000). Зоны: ≥336 🔥 быстрая победа · ≥120 ✅ · иначе ⏳.
"""

from __future__ import annotations
import argparse, csv, sys


def clamp(v, lo=1, hi=10):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, v))


def zone(score: float) -> str:
    if score >= 336:   # ~7*7*7
        return "🔥 quick-win"
    if score >= 120:   # ~5*5*5
        return "✅ do"
    return "⏳ later"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="CSV: finding,impact,confidence,ease[,source,note]")
    ap.add_argument("--md", action="store_true", help="markdown-таблица")
    ap.add_argument("--top", type=int, help="показать только top N")
    args = ap.parse_args()

    rows = []
    with open(args.csv, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            i, c, e = clamp(r.get("impact")), clamp(r.get("confidence")), clamp(r.get("ease"))
            score = round(i * c * e)
            rows.append({
                "finding": (r.get("finding") or "").strip(),
                "i": i, "c": c, "e": e, "ice": score,
                "source": (r.get("source") or "").strip(),
                "note": (r.get("note") or "").strip(),
            })
    if not rows:
        print("Пусто: нет находок в CSV (нужны колонки finding,impact,confidence,ease)")
        return 0

    rows.sort(key=lambda x: x["ice"], reverse=True)
    if args.top:
        rows = rows[:args.top]

    if args.md:
        print("| # | Находка | I | C | E | ICE | Зона | Источник |")
        print("|---|---|---|---|---|---|---|---|")
        for n, r in enumerate(rows, 1):
            print(f"| {n} | {r['finding']} | {r['i']:.0f} | {r['c']:.0f} | {r['e']:.0f} | "
                  f"{r['ice']} | {zone(r['ice'])} | {r['source']} |")
    else:
        print(f"{'#':>2} {'ICE':>4}  {'зона':<12} находка")
        print("-" * 70)
        for n, r in enumerate(rows, 1):
            print(f"{n:>2} {r['ice']:>4}  {zone(r['ice']):<12} {r['finding']}"
                  + (f"  [{r['source']}]" if r['source'] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
