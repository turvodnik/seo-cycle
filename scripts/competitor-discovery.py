#!/usr/bin/env python3
"""
competitor-discovery.py — находит максимально похожих конкурентов через топ выдачи
Яндекса по коммерческим ключам ядра (Keys.so). Лучше, чем `concurents` по домену,
когда сайт ранжируется не той семантикой, что отражает бизнес (напр. блогом).

Метод: для каждого seed-ключа берём top[] выдачи (Keys.so keyword_dashboard),
агрегируем домены → сколько ключей в топе + видимость → ранжируем. Гиганты
(маркетплейсы/DIY-сети) помечаются, чтобы выделить «похожих» конкурентов.

Endpoint Keys.so, auth X-Keyso-TOKEN (env KEYSO_API_TOKEN), лимит 10/10сек.

Использование:
  python3 competitor-discovery.py "минвата" "осп плита" "пароизоляция" [--base msk] [--top 20] [--md]
  python3 competitor-discovery.py --file seeds.txt --md
  (--file — по ключу на строку)

Опции: --base msk | --top N (глубина топа на ключ, default 20) | --ttl 60 | --md
        --exclude-giants (скрыть известные маркетплейсы/сети из вывода)
Расход: кэш TTL 60д — повторный прогон тех же ключей не тратит лимит Keys.so.
"""

from __future__ import annotations
import argparse, hashlib, json, os, pathlib, sys, time, urllib.parse, urllib.request, urllib.error
from collections import defaultdict

BASE_URL = "https://api.keys.so"
CACHE_DIR = pathlib.Path("./seo/research/keyso")
_LAST = [0.0]
RATE_DELAY = 1.1

GIANTS = {  # маркетплейсы и федеральные DIY-сети — «другая лига», не похожие
    "lemanapro.ru", "vseinstrumenti.ru", "wildberries.ru", "ozon.ru", "market.yandex.ru",
    "m.avito.ru", "avito.ru", "moscow.petrovich.ru", "petrovich.ru", "maxidom.ru",
    "aliexpress.ru", "sbermegamarket.ru", "castorama.ru", "obi.ru",
}


def load_token() -> str:
    tok = os.environ.get("KEYSO_API_TOKEN")
    if tok:
        return tok.strip()
    for rel in (".env", "seo/.env"):
        p = pathlib.Path.cwd() / rel
        if p.exists():
            for line in p.read_text().splitlines():
                if line.strip().startswith("KEYSO_API_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("ERROR: KEYSO_API_TOKEN не найден")


def fetch_top(token, keyword, base, ttl):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(f"kd:{keyword}:{base}".encode()).hexdigest()[:12]
    cpath = CACHE_DIR / f"keyso-disc-{key}.json"
    if cpath.exists() and (time.time() - cpath.stat().st_mtime) / 86400.0 <= ttl:
        return json.loads(cpath.read_text(encoding="utf-8"))
    wait = RATE_DELAY - (time.time() - _LAST[0])
    if wait > 0:
        time.sleep(wait)
    qs = urllib.parse.urlencode({"keyword": keyword, "base": base})
    req = urllib.request.Request(f"{BASE_URL}/report/simple/keyword_dashboard?{qs}",
                                 headers={"X-Keyso-TOKEN": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            _LAST[0] = time.time()
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        _LAST[0] = time.time()
        if e.code == 429:
            time.sleep(int(e.headers.get("Retry-After", 10)) + 1)
            return fetch_top(token, keyword, base, ttl)
        sys.exit(f"ERROR Keys.so HTTP {e.code}")
    cpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("seeds", nargs="*", help="коммерческие seed-ключи")
    ap.add_argument("--file", help="файл с ключами (по одному на строку)")
    ap.add_argument("--base", default="msk")
    ap.add_argument("--top", type=int, default=20, help="глубина топа на ключ")
    ap.add_argument("--ttl", type=float, default=60)
    ap.add_argument("--exclude-giants", action="store_true")
    ap.add_argument("--md", action="store_true")
    args = ap.parse_args()

    seeds = list(args.seeds)
    if args.file:
        seeds += [l.strip() for l in pathlib.Path(args.file).read_text(encoding="utf-8").splitlines() if l.strip()]
    if not seeds:
        sys.exit("ERROR: нужны seed-ключи (аргументы или --file)")

    token = load_token()
    dom = defaultdict(lambda: {"hits": 0, "vis": 0, "pos": [], "kws": set()})
    for kw in seeds:
        data = fetch_top(token, kw, args.base, args.ttl)
        for t in data.get("top", [])[:args.top]:
            nm = t.get("domain", "")
            if not nm:
                continue
            dom[nm]["hits"] += 1
            dom[nm]["vis"] = max(dom[nm]["vis"], t.get("vis", 0))
            dom[nm]["pos"].append(t.get("pos", 0))
            dom[nm]["kws"].add(kw)

    rows = sorted(dom.items(), key=lambda x: (x[1]["hits"], x[1]["vis"]), reverse=True)
    if args.exclude_giants:
        rows = [(n, v) for n, v in rows if n not in GIANTS]

    hdr = f"найдено конкурентов: {len(rows)} по {len(seeds)} ключам (база {args.base})"
    if args.md:
        print(f"<!-- {hdr} -->")
        print("| домен | ключей в топе | видимость | лига | ключи |")
        print("|---|---|---|---|---|")
        for n, v in rows[:30]:
            league = "гигант" if n in GIANTS else "похожий"
            print(f"| {n} | {v['hits']} | {v['vis']} | {league} | {', '.join(sorted(v['kws']))[:50]} |")
    else:
        print(f"== {hdr} ==\n")
        print(f"{'домен':<30}{'ключей':>8}{'видимость':>14}  лига")
        print("-" * 70)
        for n, v in rows[:30]:
            league = "гигант" if n in GIANTS else "похожий ⭐"
            print(f"{n:<30}{v['hits']:>8}{v['vis']:>14}  {league}")
        similar = [n for n, v in rows if n not in GIANTS][:5]
        print(f"\n  Топ похожих (ориентиры): {', '.join(similar)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
