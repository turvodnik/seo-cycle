#!/usr/bin/env python3
"""
review-velocity.py — расчёт плана догона конкурента по отзывам (Google или Яндекс/2ГИС).
Детерминированная математика для тактики #3 локального SEO: «сколько отзывов в месяц
нужно генерировать, чтобы догнать лидера, и за какой срок».

Вход (числа снимаются вручную/браузером с карточек):
  --my-total       текущее число моих отзывов
  --leader-total   число отзывов лидера
  --leader-30d     прирост лидера за последние 30 дней (его темп/мес)
  --my-target-30d  сколько отзывов/мес я планирую генерировать (опц.)
  --platform       google | yandex | 2gis (для метки)
  --catch-up-months  за сколько месяцев хочу догнать (опц., считает нужный темп)

Выход: разрыв, реалистичность догона, срок при заданном темпе и/или нужный темп
для заданного срока.

Примеры:
  python3 review-velocity.py --my-total 12 --leader-total 80 --leader-30d 6 --my-target-30d 12
  python3 review-velocity.py --my-total 12 --leader-total 80 --leader-30d 6 --catch-up-months 6
"""

from __future__ import annotations
import argparse, math, sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--my-total", type=int, required=True)
    ap.add_argument("--leader-total", type=int, required=True)
    ap.add_argument("--leader-30d", type=int, default=0, help="прирост лидера за 30 дней (темп/мес)")
    ap.add_argument("--my-target-30d", type=int, help="мой планируемый темп отзывов/мес")
    ap.add_argument("--catch-up-months", type=float, help="за сколько мес хочу догнать")
    ap.add_argument("--platform", default="google", choices=["google", "yandex", "2gis"])
    args = ap.parse_args()

    gap = args.leader_total - args.my_total
    print(f"== Review velocity ({args.platform}) ==")
    print(f"  Мои отзывы: {args.my_total} | Лидер: {args.leader_total} | Разрыв: {gap}")
    print(f"  Темп лидера: ~{args.leader_30d}/мес")

    if gap <= 0:
        print("  ✓ Вы уже на уровне лидера или впереди. Держите темп ≥ лидера, чтобы не откатиться.")
        return 0

    # Сценарий A: задан мой темп → когда догоню
    if args.my_target_30d is not None:
        net = args.my_target_30d - args.leader_30d
        print(f"\n  При моём темпе {args.my_target_30d}/мес (чистый прирост к разрыву: {net}/мес):")
        if net <= 0:
            need = args.leader_30d + 1
            print(f"    ✗ Не догнать: лидер растёт так же/быстрее. Нужен темп > {args.leader_30d}/мес (хотя бы {need}).")
        else:
            months = math.ceil(gap / net)
            print(f"    → догон за ~{months} мес ({months // 12}г {months % 12}мес).")

    # Сценарий B: задан срок → какой темп нужен
    if args.catch_up_months is not None:
        # gap + leader_30d*T = my_rate*T  →  my_rate = gap/T + leader_30d
        rate = math.ceil(gap / args.catch_up_months + args.leader_30d)
        print(f"\n  Чтобы догнать за {args.catch_up_months:g} мес — нужен темп ~{rate} отзывов/мес")
        print(f"    (≈ {math.ceil(rate / 30 * 7)} /нед, ≈ {rate / 30:.1f} /день).")

    if args.my_target_30d is None and args.catch_up_months is None:
        # дефолт: темпы для 6 и 12 мес
        for T in (6, 12):
            rate = math.ceil(gap / T + args.leader_30d)
            print(f"\n  Догон за {T} мес → нужен темп ~{rate}/мес (≈ {rate/30:.1f}/день).")

    print("\n  ⚠ Только реальные отзывы (Яндекс/Google фильтруют накрутку). "
          "Стимулировать: QR на точке, follow-up после заказа/доставки.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
