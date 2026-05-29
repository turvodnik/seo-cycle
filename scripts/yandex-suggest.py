#!/usr/bin/env python3
"""
yandex-suggest.py — собирает Яндекс Suggest (автодополнение) для seed-запроса.

Бесплатно через public endpoint suggest.yandex.ru. Без API ключа, без авторизации.
Глубина 2 — пробегаем по seed + каждому suggest, и собираем подсказки 2-го уровня.

Регион: 213 = Москва, 1 = Московская область, 225 = Россия.

Использование:
    python3 yandex-suggest.py "минеральная вата" --region 213 --depth 2 --output 02a2-yandex-suggest.csv

Что возвращает: список уникальных long-tail запросов с примечанием уровня (1 или 2).
Это сырые данные для семантического ядра — без частот, нужны для расширения long-tail.
Для частот — отправить ключи в Wordstat (через yandex-seo-specialist агент).
"""

from __future__ import annotations
import argparse, json, sys, time, csv, pathlib, re
import urllib.parse, urllib.request


def fetch_suggest(query: str, region: str = "213") -> list[str]:
    """Возвращает suggest для query через public endpoint Яндекса.

    Endpoint suggest-ya.cgi возвращает JSONP вида:
        ["query", ["suggest1", "suggest2", ...], {...meta...}]
    или JSON-array если без callback.
    """
    url = "https://suggest.yandex.ru/suggest-ya.cgi"
    params = {
        "srv": "morda_ru_desktop",
        "part": query,
        "n": "10",
        "v": "4",
        "uil": "ru",
        "lr": region,
    }
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "ru,en;q=0.9",
        "Referer": "https://yandex.ru/",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode("utf-8")
        # Может быть JSONP-обёрткой вида callback(...) или чистым JSON
        m = re.match(r"^\s*[A-Za-z_][\w.]*\((.*)\)\s*;?\s*$", raw, re.DOTALL)
        if m:
            raw = m.group(1)
        data = json.loads(raw)
        # Формат Яндекса: [query, [["highlight", "full text", {meta}], ...], {meta}]
        # Полный текст подсказки лежит в s[1]; s[0] обычно "" или ярлык категории.
        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
            out = []
            for s in data[1]:
                if isinstance(s, str):
                    out.append(s)
                elif isinstance(s, list):
                    # ищем первую непустую строку начиная с index 1, затем 0
                    text = ""
                    for i in (1, 0, 2):
                        if i < len(s) and isinstance(s[i], str) and s[i].strip():
                            text = s[i].strip()
                            break
                    if text:
                        out.append(text)
            return out
        return []
    except Exception as e:
        print(f"  ! error for {query!r}: {e}", file=sys.stderr)
        return []


def expand_with_alphabet(query: str, region: str) -> list[str]:
    """Расширение через 'query <буква>' для богатой подборки."""
    out = set()
    for s in fetch_suggest(query, region):
        out.add(s)
    letters = "абвгдежзиклмнопрстуфхцчшэюя"
    for letter in letters:
        for s in fetch_suggest(f"{query} {letter}", region):
            out.add(s)
        time.sleep(0.15)  # вежливая пауза, Яндекс может рейт-лимитить
    return sorted(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("seed", help="Главный запрос (например, 'минеральная вата')")
    p.add_argument("--region", default="213",
                   help="Код региона Яндекса: 213=Москва, 1=МО, 225=Россия. По умолчанию 213.")
    p.add_argument("--depth", type=int, default=2, choices=[1, 2])
    p.add_argument("--output", type=pathlib.Path, default=None,
                   help="CSV файл для сохранения")
    p.add_argument("--alphabet", action="store_true",
                   help="Расширять через 'seed <буква>' (даёт больше long-tail)")
    args = p.parse_args()

    print(f"== Яндекс Suggest: {args.seed!r} (region={args.region}, depth={args.depth}) ==")

    # Level 1
    if args.alphabet:
        level1 = expand_with_alphabet(args.seed, args.region)
    else:
        level1 = fetch_suggest(args.seed, args.region)

    print(f"\nLevel 1: {len(level1)} suggestions")
    for s in level1[:20]:
        print(f"  {s}")
    if len(level1) > 20:
        print(f"  ... +{len(level1)-20} more")

    # Level 2
    level2 = set()
    if args.depth >= 2:
        print(f"\nLevel 2: expanding each L1 (this may take a minute)...")
        for i, s1 in enumerate(level1, 1):
            for s2 in fetch_suggest(s1, args.region):
                if s2 != s1 and s2 not in level1:
                    level2.add(s2)
            time.sleep(0.15)
            if i % 10 == 0:
                print(f"  ... {i}/{len(level1)} done, collected {len(level2)} L2")

    print(f"\nLevel 2: {len(level2)} new suggestions")

    all_suggestions = [(s, 1) for s in level1] + [(s, 2) for s in sorted(level2)]
    print(f"\n=== Total: {len(all_suggestions)} unique suggestions ===")

    if args.output:
        with args.output.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["keyword", "level", "seed", "region"])
            for s, lvl in all_suggestions:
                w.writerow([s, lvl, args.seed, args.region])
        print(f"✓ Saved to {args.output}")


if __name__ == "__main__":
    main()
