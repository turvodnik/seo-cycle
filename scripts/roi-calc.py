#!/usr/bin/env python3
"""
roi-calc.py — воронка и экономика по каналам: связывает трафик с деньгами и отвечает
на вопрос «какой канал окупается и нужна ли реклама». Это «конечный результат»
маркетинга — то, чего не видно из позиций/трафика.

Вход — CSV по каналам:
  channel,spend,visits,leads,orders,revenue
  Органика SEO,0,4200,180,52,624000
  Яндекс.Директ,90000,3100,140,38,456000
  VK Реклама,40000,1500,40,9,108000
  Локалка/Карты,0,900,70,25,300000
(spend — расход за период, ₽; revenue — выручка с канала, ₽)

Метрики на канал:
  CR1 visit→lead, CR2 lead→order, CPL (цена лида), CAC (цена клиента),
  AOV (средний чек), ROI% = (revenue−spend)/spend, ДРР% = spend/revenue (РФ-метрика),
  прибыльность (revenue−spend).

Использование:
  python3 roi-calc.py funnel.csv [--md] [--margin 0.3]
  --margin — доля маржи в выручке (для ROI по прибыли, а не обороту; default 1.0 = по обороту)

Выводит таблицу + вердикт: какие каналы окупаются, нужна ли платная реклама
(сравнение ROI платных каналов с органикой), где резать/масштабировать.
"""

from __future__ import annotations
import argparse, csv, sys


def num(v):
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--margin", type=float, default=1.0, help="доля маржи в выручке (0..1), default 1.0")
    args = ap.parse_args()

    rows = []
    with open(args.csv, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ch = (r.get("channel") or "").strip()
            if not ch:
                continue
            spend, visits = num(r.get("spend")), num(r.get("visits"))
            leads, orders, rev = num(r.get("leads")), num(r.get("orders")), num(r.get("revenue"))
            profit = rev * args.margin - spend
            rows.append({
                "ch": ch, "spend": spend, "visits": visits, "leads": leads,
                "orders": orders, "rev": rev,
                "cr1": (leads / visits * 100) if visits else 0,
                "cr2": (orders / leads * 100) if leads else 0,
                "cpl": (spend / leads) if leads else 0,
                "cac": (spend / orders) if orders else 0,
                "aov": (rev / orders) if orders else 0,
                "roi": ((rev * args.margin - spend) / spend * 100) if spend else None,
                "drr": (spend / rev * 100) if rev else 0,
                "profit": profit,
                "paid": spend > 0,
            })
    if not rows:
        print("Пусто: нужен CSV channel,spend,visits,leads,orders,revenue")
        return 0

    if args.md:
        print("| Канал | Расход | Выручка | CR1% | CR2% | CPL | CAC | AOV | ДРР% | ROI% | Прибыль |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            roi = "∞" if r["roi"] is None else f"{r['roi']:+.0f}"
            print(f"| {r['ch']} | {r['spend']:.0f} | {r['rev']:.0f} | {r['cr1']:.1f} | {r['cr2']:.1f} | "
                  f"{r['cpl']:.0f} | {r['cac']:.0f} | {r['aov']:.0f} | {r['drr']:.0f} | {roi} | {r['profit']:+.0f} |")
    else:
        print(f"== Воронка и ROI по каналам (маржа {args.margin:g}) ==\n")
        for r in rows:
            roi = "органика (без расхода)" if r["roi"] is None else f"ROI {r['roi']:+.0f}%, ДРР {r['drr']:.0f}%"
            print(f"  {r['ch']}: выручка {r['rev']:.0f}₽, прибыль {r['profit']:+.0f}₽ | {roi}")
            print(f"     визиты {r['visits']:.0f} → лиды {r['leads']:.0f} ({r['cr1']:.1f}%) → заказы {r['orders']:.0f} ({r['cr2']:.1f}%) | CAC {r['cac']:.0f}₽, чек {r['aov']:.0f}₽")

    # Вердикт
    paid = [r for r in rows if r["paid"] and r["roi"] is not None]
    profitable = [r for r in paid if r["roi"] > 0]
    losing = [r for r in paid if r["roi"] <= 0]
    organic = [r for r in rows if not r["paid"]]
    print("\n== Вердикт ==")
    if not paid:
        print("  Платных каналов нет. Если органика+локалка закрывают цели по объёму — реклама не обязательна.")
    else:
        if profitable:
            best = max(profitable, key=lambda r: r["roi"])
            print(f"  ✓ Окупаются: {', '.join(r['ch'] for r in profitable)}. Лучший — {best['ch']} (ROI {best['roi']:+.0f}%) → масштабировать.")
        if losing:
            losing_str = ", ".join(f"{r['ch']} ({r['roi']:+.0f}%)" for r in losing)
            print(f"  ✗ Не окупаются: {losing_str} → пересмотреть оффер/таргет или резать.")
    if organic:
        print(f"  Органика/локалка: {', '.join(r['ch'] for r in organic)} — почти бесплатный объём; растить в первую очередь.")
    print("  «Нужна ли реклама?» — да, если органика не закрывает план по заказам И есть платный канал с ROI>0; иначе вкладываться в органику+локалку.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
