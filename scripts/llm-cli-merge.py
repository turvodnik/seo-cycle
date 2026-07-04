#!/usr/bin/env python3
"""
llm-cli-merge.py — мерджит два результата (Antigravity + Codex) в один уникальный список.

Парсит long-tail запросы и сущности из обоих файлов, дедуплицирует через нормализацию
(lowercase + удаление маркеров [И]/[К] + сжатие пробелов), сохраняет источник.

Использование:
    python3 seo/scripts/llm-cli-merge.py \
        seo/research/llm-cli/results/minvata-antigravity-2026-05-22.md \
        seo/research/llm-cli/results/minvata-codex-2026-05-22.md \
        -o seo/research/llm-cli/results/minvata-merged-2026-05-22.md

Выход — единый markdown с двумя секциями:
- ## Long-Tail запросы (уникальные, с пометкой источника agy/codex/both)
- ## Сущности (объединённые, URL-ы из Codex сохраняются)
"""

from __future__ import annotations
import argparse, pathlib, re, sys
from collections import OrderedDict


def normalize(s: str) -> str:
    """Нормализация для дедупа: lowercase, без [И]/[К], без лишних пробелов и символов."""
    s = re.sub(r"\[[ИК]\]", "", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"[\"'«»]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def parse_keywords(text: str) -> list[str]:
    """Извлекает long-tail запросы — строки вида '1. xxx' или '- xxx' внутри секции про ключи."""
    out = []
    # Найти секцию "Long-Tail" / "long-tail" / "запросы"
    in_section = False
    for line in text.splitlines():
        if re.search(r"##\s*(long-tail|long\s*tail|запросы|ключи)", line, re.I):
            in_section = True
            continue
        if line.startswith("## ") and in_section:
            # Другая ## — выход
            if not re.search(r"(long-tail|long\s*tail|запросы|ключи)", line, re.I):
                in_section = False
        if not in_section:
            continue
        # Паттерны: "1. xxx" / "- xxx" / "* xxx"
        m = re.match(r"^\s*(?:\d+[\.\)]|[-*])\s+(.+)$", line)
        if m:
            kw = m.group(1).strip()
            # Удаляем backticks и markdown headers внутри
            kw = re.sub(r"^#+\s*", "", kw)
            if len(kw) > 5 and len(kw) < 200:
                out.append(kw)
    return out


def parse_entities(text: str) -> list[str]:
    """Извлекает сущности из секции '## Связанные сущности' / '## Сущности'."""
    out = []
    in_section = False
    current = []
    for line in text.splitlines():
        if re.search(r"##\s*(связанные\s+)?сущности|entities", line, re.I):
            in_section = True
            continue
        if line.startswith("## ") and in_section:
            if not re.search(r"сущности|entities", line, re.I):
                if current:
                    out.append(" ".join(current).strip())
                    current = []
                in_section = False
        if not in_section:
            continue
        m = re.match(r"^\s*(?:\d+[\.\)]|[-*])\s+(.+)$", line)
        if m:
            if current:
                out.append(" ".join(current).strip())
            current = [m.group(1).strip()]
        elif line.strip() and current:
            current.append(line.strip())
    if current:
        out.append(" ".join(current).strip())
    return [e for e in out if len(e) > 10]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file_a", type=pathlib.Path, help="Первый отчёт (обычно antigravity)")
    p.add_argument("file_b", type=pathlib.Path, help="Второй отчёт (обычно codex)")
    p.add_argument("-o", "--output", type=pathlib.Path, required=True)
    p.add_argument("--label-a", default="agy")
    p.add_argument("--label-b", default="codex")
    args = p.parse_args()

    text_a = args.file_a.read_text(encoding="utf-8")
    text_b = args.file_b.read_text(encoding="utf-8")

    kw_a = parse_keywords(text_a)
    kw_b = parse_keywords(text_b)
    ent_a = parse_entities(text_a)
    ent_b = parse_entities(text_b)

    print(f"== Parsed ==", file=sys.stderr)
    print(f"  {args.label_a}: {len(kw_a)} keywords, {len(ent_a)} entities", file=sys.stderr)
    print(f"  {args.label_b}: {len(kw_b)} keywords, {len(ent_b)} entities", file=sys.stderr)

    # Merge keywords (preserve order, mark source)
    seen: dict[str, list[str]] = OrderedDict()
    for kw in kw_a:
        seen[normalize(kw)] = [kw, args.label_a]
    for kw in kw_b:
        n = normalize(kw)
        if n in seen:
            seen[n][1] = "both"
        else:
            seen[n] = [kw, args.label_b]

    # Merge entities — нормализация по первому слову (название бренда / номер ГОСТа)
    ent_seen: dict[str, list[str]] = OrderedDict()
    for e in ent_a:
        key = normalize(e).split()[0] if normalize(e) else e[:20].lower()
        ent_seen[key] = [e, args.label_a]
    for e in ent_b:
        key = normalize(e).split()[0] if normalize(e) else e[:20].lower()
        if key in ent_seen:
            # Объединяем — берём из codex (с URL) и добавляем agy-версию как комментарий
            ent_seen[key] = [e, "both", ent_seen[key][0]]
        else:
            ent_seen[key] = [e, args.label_b]

    # Write output
    with args.output.open("w", encoding="utf-8") as f:
        f.write(f"---\nmerged_from:\n  - {args.file_a.name}\n  - {args.file_b.name}\n")
        f.write(f"stats:\n  keywords_unique: {len(seen)}\n  entities_unique: {len(ent_seen)}\n---\n\n")
        f.write(f"# Merged LLM CLI отчёт\n\n")
        f.write(f"## Long-Tail запросы (уникальные)\n\n")
        for i, (_n, (kw, src)) in enumerate(seen.items(), 1):
            f.write(f"{i}. `[{src}]` {kw}\n")
        f.write(f"\n## Связанные сущности (объединённые)\n\n")
        for i, item in enumerate(ent_seen.values(), 1):
            entity, src = item[0], item[1]
            f.write(f"{i}. `[{src}]` {entity}\n")
            if len(item) > 2:
                f.write(f"   - alt: {item[2]}\n")

    print(f"\n✓ Merged → {args.output}", file=sys.stderr)
    print(f"  Unique keywords: {len(seen)}", file=sys.stderr)
    print(f"  Unique entities: {len(ent_seen)}", file=sys.stderr)


if __name__ == "__main__":
    main()
