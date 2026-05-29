#!/usr/bin/env python3
"""
google-suggest.py — собирает Google Suggest (автодополнение) для seed-запроса.

Бесплатно через public endpoint suggestqueries.google.com. Без API ключа.
Глубина 2 — пробегаем по seed + каждому suggest, и собираем подсказки 2-го уровня.

Использование:
    python3 google-suggest.py "минеральная вата" --region RU --depth 2 --output 02e-suggest.csv

Что возвращает: список уникальных long-tail запросов с примечанием уровня (1 или 2).
Это сырые данные для семантического ядра — без частот, нужны для расширения long-tail.
"""

from __future__ import annotations
import argparse, json, sys, time, csv, pathlib
import urllib.parse, urllib.request
import string


def fetch_suggest(query: str, lang: str = "ru", region: str = "RU") -> list[str]:
    """Возвращает suggest для query через public endpoint."""
    url = "https://suggestqueries.google.com/complete/search"
    params = {
        "client": "firefox",
        "q": query,
        "hl": lang,
        "gl": region.lower(),
    }
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={
        "User-Agent": "Mozilla/5.0 (compatible; emwoody-seo-cycle/1.0)"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data[1] if isinstance(data, list) and len(data) > 1 else []
    except Exception as e:
        print(f"  ! error for {query!r}: {e}", file=sys.stderr)
        return []


def expand_with_alphabet(query: str, lang: str, region: str) -> list[str]:
    """Расширение через 'query <буква>' для богатой подборки."""
    out = set()
    # Базовый suggest
    for s in fetch_suggest(query, lang, region):
        out.add(s)
    # Suggest с добавлением буквы (как делают SEO-tools)
    letters = "абвгдежзиклмнопрстуфхцчшэюя" if lang == "ru" else string.ascii_lowercase
    for letter in letters:
        for s in fetch_suggest(f"{query} {letter}", lang, region):
            out.add(s)
        time.sleep(0.1)  # вежливая пауза
    return sorted(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("seed", help="Главный запрос (например, 'минеральная вата')")
    p.add_argument("--region", default="RU")
    p.add_argument("--lang", default="ru")
    p.add_argument("--depth", type=int, default=2, choices=[1, 2])
    p.add_argument("--output", type=pathlib.Path, default=None, help="CSV файл для сохранения")
    p.add_argument("--alphabet", action="store_true", help="Расширять через 'seed <буква>' (даёт больше long-tail)")
    args = p.parse_args()

    print(f"== Google Suggest: {args.seed!r} (region={args.region}, depth={args.depth}) ==")

    # Level 1
    if args.alphabet:
        level1 = expand_with_alphabet(args.seed, args.lang, args.region)
    else:
        level1 = fetch_suggest(args.seed, args.lang, args.region)

    print(f"\nLevel 1: {len(level1)} suggestions")
    for s in level1[:20]: print(f"  {s}")
    if len(level1) > 20: print(f"  ... +{len(level1)-20} more")

    # Level 2: для каждого suggest level1, собираем его suggest
    level2 = set()
    if args.depth >= 2:
        print(f"\nLevel 2: expanding each L1 (this may take a minute)...")
        for i, s1 in enumerate(level1, 1):
            for s2 in fetch_suggest(s1, args.lang, args.region):
                if s2 != s1 and s2 not in level1:
                    level2.add(s2)
            time.sleep(0.1)
            if i % 10 == 0:
                print(f"  ... {i}/{len(level1)} done, collected {len(level2)} L2")

    print(f"\nLevel 2: {len(level2)} new suggestions")

    # Сводим
    all_suggestions = [(s, 1) for s in level1] + [(s, 2) for s in sorted(level2)]
    print(f"\n=== Total: {len(all_suggestions)} unique suggestions ===")

    if args.output:
        with args.output.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["keyword", "level", "seed"])
            for s, lvl in all_suggestions:
                w.writerow([s, lvl, args.seed])
        print(f"✓ Saved to {args.output}")


if __name__ == "__main__":
    main()
