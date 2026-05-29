#!/usr/bin/env python3
"""
research-cache.py — TTL-кэш для дорогих research-прогонов (Wordstat, NeuronWriter,
LLM-CLI, suggest, ATP). Не позволяет повторно жечь токены/время, если свежий
результат по той же теме уже лежит на диске.

Подкоманда `check`: ищет в каталоге файлы вида <slug>-<source>-*.<ext>, берёт
новейший. Если он моложе --ttl дней — печатает его путь в stdout и выходит с
кодом 0 (CACHE HIT). Иначе ничего не печатает, код 1 (MISS → нужно собирать).

Использование в bash-обёртке:
    if HIT=$(python3 research-cache.py check --dir "$OUTDIR" \
                 --slug "$SLUG" --source antigravity --ttl 14); then
        echo "↩ cache hit: $HIT — пропускаем сбор"
    else
        # ... запустить сбор ...
    fi

TTL по проекту берётся из seo-cycle.yaml: research_cache_ttl_days (default 14).
"""

from __future__ import annotations
import argparse, glob, os, sys, time, pathlib


def newest_fresh(directory: str, slug: str, source: str, ttl_days: float,
                 exts: list[str]) -> pathlib.Path | None:
    d = pathlib.Path(directory)
    if not d.is_dir():
        return None
    candidates: list[pathlib.Path] = []
    for ext in exts:
        candidates += [pathlib.Path(p) for p in glob.glob(str(d / f"{slug}-{source}-*.{ext}"))]
        candidates += [pathlib.Path(p) for p in glob.glob(str(d / f"{slug}-{source}.{ext}"))]
    if not candidates:
        return None
    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    age_days = (time.time() - newest.stat().st_mtime) / 86400.0
    return newest if age_days <= ttl_days else None


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="проверить наличие свежего кэша")
    c.add_argument("--dir", required=True, help="каталог результатов")
    c.add_argument("--slug", required=True, help="slug темы")
    c.add_argument("--source", required=True, help="имя источника (antigravity/codex/nw/...)")
    c.add_argument("--ttl", type=float, default=14, help="макс. возраст в днях (default 14)")
    c.add_argument("--ext", default="md,csv,json", help="расширения через запятую")

    args = ap.parse_args()

    if args.cmd == "check":
        exts = [e.strip().lstrip(".") for e in args.ext.split(",") if e.strip()]
        hit = newest_fresh(args.dir, args.slug, args.source, args.ttl, exts)
        if hit:
            print(str(hit))
            return 0
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
