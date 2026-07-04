#!/usr/bin/env python3
"""
competitor-benchmark.py — медианный бенчмарк по конкурентам. Для каждой метрики
считает медиану топ-N конкурентов и сравнивает с твоим значением: ты выше/на уровне/
ниже медианы и на сколько %. Отвечает на вопрос «медиана по конкурентам — что у них
есть, чего у нас нет».

Вход — CSV (wide): первая колонка `metric`, затем `my`, затем колонки конкурентов.
  metric,my,comp1,comp2,comp3
  organic_keywords,1200,3400,2800,5100
  referring_domains,45,120,90,210
  reviews,38,156,90,120
  photos,20,60,45,80
  posts_per_month,2,6,4,8
(значения — числа; пустые ячейки игнорируются)

Использование:
  python3 competitor-benchmark.py benchmark.csv [--md]

Выход — по каждой метрике: my | медиана конкурентов | разрыв % | статус
(🔴 ниже / 🟡 на уровне / 🟢 выше). Метрики, где сильнее всего отстаём — кандидаты в roadmap.
"""

from __future__ import annotations
import argparse, csv, statistics, sys


def to_num(v):
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def status(my, med):
    if med == 0:
        return "—"
    ratio = my / med
    if ratio < 0.8:
        return "🔴 ниже"
    if ratio > 1.2:
        return "🟢 выше"
    return "🟡 на уровне"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="CSV: metric,my,comp1,comp2,...")
    ap.add_argument("--md", action="store_true")
    args = ap.parse_args()

    rows = []
    with open(args.csv, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, [])  # skip header
        for r in reader:
            if not r or not r[0].strip():
                continue
            metric = r[0].strip()
            my = to_num(r[1]) if len(r) > 1 else None
            comps = [to_num(x) for x in r[2:] if to_num(x) is not None]
            if my is None or not comps:
                continue
            med = statistics.median(comps)
            gap = ((my - med) / med * 100) if med else 0
            rows.append((metric, my, med, gap, status(my, med), len(comps)))

    if not rows:
        print("Пусто: нужен CSV вида metric,my,comp1,comp2,... с числами.")
        return 0

    # сортируем: сильнее всего отстаём — наверх
    rows.sort(key=lambda x: x[3])

    if args.md:
        print("| Метрика | Моё | Медиана конк. | Разрыв | Статус |")
        print("|---|---|---|---|---|")
        for m, my, med, gap, st, n in rows:
            print(f"| {m} | {my:g} | {med:g} | {gap:+.0f}% | {st} |")
    else:
        print(f"{'метрика':<22}{'моё':>8}{'медиана':>10}{'разрыв':>9}  статус")
        print("-" * 60)
        for m, my, med, gap, st, n in rows:
            print(f"{m:<22}{my:>8g}{med:>10g}{gap:>+8.0f}%  {st}")
    behind = [m for m, *_ , st, n in rows if st == "🔴 ниже"]
    if behind:
        print(f"\n  Сильнее всего отстаём (в roadmap/ICE): {', '.join(behind[:5])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
