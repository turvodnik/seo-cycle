#!/usr/bin/env python3
"""
keyso-clustering-export.py — готовит файл ключей для загрузки в clustering-инструмент
Keys.so (или любой внешний кластеризатор). Детерминированная подготовка: собирает
ключи из источников, чистит, дедуплицирует, пишет .txt (по ключу на строку).

Загрузка файла в Keys.so делается через браузер (см. prompts/keyso-clustering-upload.md) —
API этого не позволяет. Этот скрипт — дешёвая надёжная часть (без токенов/браузера).

Источники ключей (можно несколько):
  --from-keyso-cache DOMAIN   — ключи домена из кэша keyso-fetch (seo/research/keyso)
  --from-csv FILE COL         — колонка из CSV (напр. собственное ядро)
  --from-md FILE              — строки вида `... ключ ...` из markdown-таблицы (1-я ячейка)
  --keywords "a","b"          — явный список

Опции: --min-ws N (мин. частота, если есть) | --out FILE (default keywords-for-keyso.txt)
       --limit N (макс. ключей — у Keys.so clustering есть лимит на загрузку)

Пример:
  python3 keyso-clustering-export.py --from-keyso-cache emwoody.ru --out seo/cycles/.../keys.txt
"""

from __future__ import annotations
import argparse, csv, hashlib, json, pathlib, re, sys

CACHE = pathlib.Path("seo/research/keyso")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def from_keyso_cache(domain: str, min_ws: int):
    params = {"domain": domain, "base": "msk", "per_page": 100}
    key = hashlib.md5(("keywords" + json.dumps(params, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:12]
    p = CACHE / f"keyso-keywords-{key}.json"
    if not p.exists():
        print(f"  ! нет кэша для {domain} (сначала: keyso-fetch.py keywords {domain})", file=sys.stderr)
        return []
    out = []
    for k in json.loads(p.read_text(encoding="utf-8")).get("data", []):
        if k.get("ws", 0) >= min_ws:
            out.append(norm(k.get("word", "")))
    return out


def from_md(path: str):
    out = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("|") and "|" in line[1:]:
            cell = line.strip("|").split("|")[0].strip().strip("`")
            if cell and cell.lower() not in ("ключ", "keyword", "---", "метрика"):
                out.append(norm(cell))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-keyso-cache", action="append", default=[], metavar="DOMAIN")
    ap.add_argument("--from-csv", nargs=2, action="append", default=[], metavar=("FILE", "COL"))
    ap.add_argument("--from-md", action="append", default=[], metavar="FILE")
    ap.add_argument("--keywords", help="ключи через запятую")
    ap.add_argument("--min-ws", type=int, default=0)
    ap.add_argument("--limit", type=int, default=10000)
    ap.add_argument("--out", default="keywords-for-keyso.txt")
    args = ap.parse_args()

    kws = []
    for d in args.from_keyso_cache:
        kws += from_keyso_cache(d, args.min_ws)
    for f, col in args.from_csv:
        with open(f, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get(col):
                    kws.append(norm(r[col]))
    for f in args.from_md:
        kws += from_md(f)
    if args.keywords:
        kws += [norm(k) for k in args.keywords.split(",")]

    # дедуп (без учёта регистра), сохранить порядок
    seen, uniq = set(), []
    for k in kws:
        lk = k.lower()
        if k and lk not in seen:
            seen.add(lk); uniq.append(k)
    uniq = uniq[:args.limit]

    if not uniq:
        print("Пусто: не собрано ключей. Проверь источники (--from-keyso-cache требует кэш).")
        return 1

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(uniq) + "\n", encoding="utf-8")
    print(f"✓ {len(uniq)} уникальных ключей → {out}")
    print(f"  Загрузить в Keys.so clustering — см. prompts/keyso-clustering-upload.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
