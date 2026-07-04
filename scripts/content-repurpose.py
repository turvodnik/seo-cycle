#!/usr/bin/env python3
"""Repurpose a finished draft into multi-format skeletons (offline extraction).

From one approved article the agency usually needs: a Telegram post, a VK
post, a video script outline, and an email digest. This tool extracts the
draft's structure (H2/H3, lead, FAQ, facts with numbers) and builds
ready-to-edit skeletons with clearly marked [TODO] slots — the agent or
copywriter fills the voice, никаких выдуманных фактов не добавляется.

Usage:
  python3 scripts/content-repurpose.py seo/research-package/drafts/<slug>.md --write
Output: seo/research-package/repurpose/<slug>.md
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

from seo_cycle_core.config import package_project_root, write_text
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("content-repurpose")


def parse_draft(text: str) -> dict:
    lines = text.splitlines()
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), "")
    h2 = [l[3:].strip() for l in lines if l.startswith("## ")]
    h3 = [l[4:].strip() for l in lines if l.startswith("### ")]
    paragraphs = [l.strip() for l in lines if l.strip() and not l.startswith(("#", "|", "-", ">", "!"))]
    lead = paragraphs[0] if paragraphs else ""
    facts = [p for p in paragraphs[1:] if re.search(r"\d", p) and 25 <= len(p) <= 220][:8]
    faq: list[tuple[str, str]] = []
    for index, line in enumerate(lines):
        heading = line.lstrip("#").strip()
        if line.startswith("#") and heading.endswith("?"):
            answer = next((l.strip() for l in lines[index + 1:] if l.strip() and not l.startswith("#")), "")
            faq.append((heading, answer))
    return {"title": title, "h2": h2, "h3": h3, "lead": lead, "facts": facts, "faq": faq[:5]}


def build_skeletons(parsed: dict, url_hint: str) -> str:
    title, lead = parsed["title"], parsed["lead"]
    top_facts = parsed["facts"][:3]
    facts_block = "\n".join(f"• {fact}" for fact in top_facts) or "• [TODO: 2–3 главных факта из статьи]"
    sections = parsed["h2"][:6]
    faq = parsed["faq"]

    tg = [f"**{title}**", "", (lead[:280] + "…") if len(lead) > 280 else lead, "", facts_block, "",
          f"Полный разбор: {url_hint}", "", "[TODO: 1 строка «зачем читать» голосом бренда + эмодзи по вкусу]"]
    vk = [f"{title}", "", lead[:400], "", facts_block, "",
          f"Читать целиком: {url_hint}", "#" + " #".join(re.findall(r"[а-яёa-z]{4,}", title.lower())[:4])]
    video = [f"# Видео-скрипт: {title}", "",
             "0:00 Хук — [TODO: вопрос/боль зрителя одной фразой]",
             f"0:15 О чём выпуск — {lead[:160]}"]
    stamp = 30
    for section in sections:
        video.append(f"{stamp // 60}:{stamp % 60:02d} {section} — [TODO: тезис 1–2 предложения]")
        stamp += 45
    video += [f"{stamp // 60}:{stamp % 60:02d} Вывод + CTA — [TODO: что сделать зрителю]",
              "", "Факты для титров:", facts_block]
    email = [f"Тема письма: {title} [TODO: A/B-вариант темы]", "", f"Привет! {lead[:200]}", "",
             "В новом материале:"]
    email += [f"- {section}" for section in sections[:4]]
    email += ["", facts_block, "", f"→ Читать: {url_hint}"]

    out = [f"# Repurpose-пакет: {title}", "",
           "_Каркасы из фактов статьи; [TODO]-слоты заполняет человек/агент. "
           "Новые факты не выдумывать — только из исходника._", "",
           "## Telegram-пост", "", *tg, "", "## VK-пост", "", *vk, "",
           "## Видео-скрипт", "", *video, "", "## Email-дайджест", "", *email]
    if faq:
        out += ["", "## Готовые Q&A (для Stories/Shorts/рассылки)", ""]
        out += [f"**{q}**\n{a}\n" for q, a in faq]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("draft", help="Path to the draft markdown")
    parser.add_argument("--url", default="[TODO: URL после публикации]", help="Published URL for CTAs")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    draft = pathlib.Path(args.draft).expanduser().resolve()
    if not draft.exists():
        print(f"ERROR: {draft} not found", file=sys.stderr)
        return 2
    parsed = parse_draft(draft.read_text(encoding="utf-8"))
    if not parsed["title"]:
        print("ERROR: в драфте нет H1 (# заголовок)", file=sys.stderr)
        return 2
    skeletons = build_skeletons(parsed, args.url)

    if args.format == "json":
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    if args.write:
        base = package_project_root(draft.parent)
        out = base / "seo" / "research-package" / "repurpose" / f"{draft.stem}.md"
        write_text(out, skeletons)
        print(f"✓ {out}", file=sys.stderr)
    if args.format == "md":
        print(skeletons, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
