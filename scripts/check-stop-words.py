#!/usr/bin/env python3
"""
check-stop-words.py — детектор стоп-слов с поддержкой морфологических форм.

Универсальный (project-agnostic):
- Базовые regex-паттерны (RU + EN) — в seo_cycle_core/stop_words.py
  (тот же модуль использует draft-quality-gate.py)
- Доп. паттерны / простые слова — из seo-cycle.yaml (`tone.stop_words_extra`,
  `tone.stop_words_regex_extra`)
- Игнорирует цитаты («...» / "..." / '...'), code blocks, frontmatter, JSON-LD
- Номер строки и контекст указывают на строку исходного файла

Использование:
    python3 check-stop-words.py <file.md> [<file2.md> ...]
    python3 check-stop-words.py --config ./seo-cycle.yaml content.md
    python3 check-stop-words.py --extra-words "лучший,уникальный" file.md
    python3 check-stop-words.py --lang en file.md

Выход:
    0 — ничего не найдено
    1 — найдены стоп-слова (детали в stdout)
    2 — ошибка: файл не найден/не читается, конфиг не разобран
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from seo_cycle_core.config import load_yaml_safe
from seo_cycle_core.stop_words import (  # noqa: F401 (re-exported for callers of the old script)
    EN_PATTERNS,
    RU_PATTERNS,
    extra_rules,
    find_violations,
    patterns_for,
    resolve_lang,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Детектор стоп-слов (RU/EN + правила проекта из seo-cycle.yaml).")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--config", default="seo-cycle.yaml",
                    help="Путь к seo-cycle.yaml")
    ap.add_argument("--lang", default="auto",
                    help="auto | ru | en | both (default: auto — определяется по конфигу)")
    ap.add_argument("--extra-words", default="",
                    help="Доп. простые слова через запятую")
    args = ap.parse_args()

    cfg_path = pathlib.Path(args.config)
    cfg, error = load_yaml_safe(cfg_path)
    if error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    cfg = cfg or {}
    extra_simple, extra_regex = extra_rules(cfg)
    if args.extra_words:
        extra_simple.extend([w.strip() for w in args.extra_words.split(",") if w.strip()])

    lang = resolve_lang(args.lang, cfg)
    patterns = patterns_for(lang)
    if not patterns and lang not in ("ru", "en", "both"):
        # Чужой язык — только пользовательские правила
        print(f"⚠ Язык {lang!r} не поддерживается встроенными паттернами — используем только extra-words и regex_extra из конфига", file=sys.stderr)
    for r in extra_regex:
        patterns.append(("custom-regex", r))

    total = 0
    unreadable = 0
    for f in args.files:
        p = pathlib.Path(f)
        try:
            text = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"ERROR: {p}: не существует", file=sys.stderr)
            unreadable += 1
            continue
        except (OSError, UnicodeDecodeError) as exc:
            print(f"ERROR: {p}: не прочитан: {exc}", file=sys.stderr)
            unreadable += 1
            continue
        v = find_violations(text, patterns, extra_simple)
        if not v:
            print(f"✓ {p}: чисто ({len(patterns)} паттернов, {len(extra_simple)} простых слов)")
        else:
            print(f"❌ {p}: {len(v)} нарушений")
            for lineno, cat, match, ctx in v:
                print(f"  L{lineno} [{cat}] «{match}» → {ctx}")
            total += len(v)

    if unreadable:
        return 2
    return 1 if total > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
