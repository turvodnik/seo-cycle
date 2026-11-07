#!/usr/bin/env python3
"""seo-cycle voice — профиль голоса бренда, методов письма и изображений (3.1.0).

Один файл на проект — `seo/brand/voice.yaml` (`policy_files.brand_voice_profile`):
кто мы и для кого пишем, голос в парах «это / а не это», обращение,
лексика, стиль и типографика, порядок блоков по типам страниц, реальные
авторы, типы изображений с источником, стилем, пропорцией и подписью.
Профиль попадает в бриф копирайтера (page-outline-v3), в context pack задач
на написание и в гейт черновика.

Команды:
  init [--write] [--force]          создать профиль из шаблона; значения
                                    переносятся из seo-cycle.yaml (tone.*,
                                    images.*, project.brand_name_*, locale)
  validate [--format md|json]       структура и типы; что осталось заполнить
  show [--page-type T] [--format]   блок для брифа (как увидит копирайтер)
  check <draft.md> [--page-type T]  проверить черновик по профилю
  extract-prompt --from PATH...     запрос для модели: вывести голос из уже
                                    опубликованных текстов (платных вызовов нет)

Коды выхода: 0 — ок; 1 — профиль с ошибками / черновик с error-находками /
профиля нет (validate); 2 — ошибка вызова или конфига.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any

from seo_cycle_core import brand_voice as bv
from seo_cycle_core.config import find_project_config, load_yaml, project_root_for, write_text
from seo_cycle_core.frontmatter import split_frontmatter
from seo_cycle_core.page_types import PAGE_TYPES

MAX_SAMPLE_CHARS = 12000


def resolve_project(explicit: str | None) -> tuple[pathlib.Path, dict[str, Any]] | None:
    if explicit:
        cfg_path = pathlib.Path(explicit).expanduser().resolve()
        if not cfg_path.exists():
            print(f"ERROR: конфиг не найден: {cfg_path}", file=sys.stderr)
            return None
    else:
        found = find_project_config(pathlib.Path.cwd())
        if found is None:
            print(f"ERROR: seo-cycle.yaml не найден от {pathlib.Path.cwd()} вверх — запусти из проекта или передай --config",
                  file=sys.stderr)
            return None
        cfg_path = found
    return project_root_for(cfg_path), load_yaml(cfg_path)


def require_profile(root: pathlib.Path, cfg: dict[str, Any]) -> tuple[pathlib.Path, dict[str, Any]] | None:
    path = bv.profile_path(cfg, root)
    if not bv.settings(cfg)["enabled"]:
        print("ℹ профиль голоса выключен в seo-cycle.yaml (brand_voice.enabled: false)", file=sys.stderr)
        return None
    if not path.exists():
        print(f"ERROR: профиля нет: {bv.display_path(root, path)} — создай: seo-cycle voice init --write", file=sys.stderr)
        return None
    profile = load_yaml(path)
    return path, profile


def cmd_init(args: argparse.Namespace, root: pathlib.Path, cfg: dict[str, Any]) -> int:
    path = bv.profile_path(cfg, root)
    shown = bv.display_path(root, path)
    if path.exists() and not args.force:
        print(f"ℹ профиль уже есть: {shown} — не трогаю (--force перезапишет)")
        return 0
    text = bv.render_init(cfg)
    if not args.write:
        print(text, end="")
        print(f"\n# dry-run: файл не записан; запись — seo-cycle voice init --write → {shown}", file=sys.stderr)
        return 0
    write_text(path, text)
    profile = load_yaml(path)
    todo = bv.unanswered_fields(profile)
    print(f"✓ профиль голоса создан: {shown}")
    if todo:
        print("Заполни (seo-cycle voice validate покажет снова):")
        for row in todo:
            print(f"  - {row['field']}: {row['question']}")
    return 0


def cmd_validate(args: argparse.Namespace, root: pathlib.Path, cfg: dict[str, Any]) -> int:
    loaded = require_profile(root, cfg)
    if loaded is None:
        return 1
    path, profile = loaded
    errors = bv.validate_profile(profile)
    todo = bv.unanswered_fields(profile) if isinstance(profile, dict) else []
    report = {"profile": bv.display_path(root, path), "errors": errors, "unanswered": todo,
              "status": "invalid" if errors else ("incomplete" if todo else "ok")}
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"# Профиль голоса: {report['profile']} — {report['status']}")
        for error in errors:
            print(f"✗ {error}")
        for row in todo:
            print(f"□ {row['field']}: {row['question']}")
        if not errors and not todo:
            print("✓ структура верна, обязательные поля заполнены")
    return 1 if errors else 0


def cmd_show(args: argparse.Namespace, root: pathlib.Path, cfg: dict[str, Any]) -> int:
    loaded = require_profile(root, cfg)
    if loaded is None:
        return 1
    path, profile = loaded
    errors = bv.validate_profile(profile)
    if errors:
        print("ERROR: профиль с ошибками — seo-cycle voice validate", file=sys.stderr)
        return 1
    block = bv.brief_block(profile, args.page_type, bv.display_path(root, path))
    if args.format == "json":
        print(json.dumps(block, ensure_ascii=False, indent=2))
    else:
        print("\n".join(bv.render_brief_markdown(block)))
    return 0


def cmd_check(args: argparse.Namespace, root: pathlib.Path, cfg: dict[str, Any]) -> int:
    loaded = require_profile(root, cfg)
    if loaded is None:
        return 2
    _path, profile = loaded
    errors = bv.validate_profile(profile)
    if errors:
        print(f"ERROR: профиль с ошибками ({len(errors)}) — seo-cycle voice validate", file=sys.stderr)
        return 2
    draft = pathlib.Path(args.draft).expanduser().resolve()
    try:
        text = draft.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: черновик не прочитан: {draft}: {exc}", file=sys.stderr)
        return 2
    front = split_frontmatter(text)
    page_type = args.page_type or front.data.get("page_type") or "article"
    findings = bv.check_draft(text, profile, page_type=page_type, frontmatter=front.data, cfg=cfg, location=str(draft))
    status = "fail" if any(f["severity"] == "error" for f in findings) else ("warn" if findings else "pass")
    if args.format == "json":
        print(json.dumps({"status": status, "page_type": page_type, "findings": findings}, ensure_ascii=False, indent=2))
    else:
        print(f"# Черновик по профилю голоса: {status}")
        for finding in findings:
            print(f"- {finding['severity'].upper()} `{finding['id']}`: {finding['message']}")
        if not findings:
            print("✓ замечаний нет")
    return 1 if status == "fail" else 0


def _sample_text(path: pathlib.Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in (".html", ".htm"):
        raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
        raw = re.sub(r"<[^>]+>", " ", raw)
    else:
        raw = split_frontmatter(raw).body
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", raw)).strip()


def cmd_extract_prompt(args: argparse.Namespace, root: pathlib.Path, cfg: dict[str, Any]) -> int:
    files: list[pathlib.Path] = []
    for raw in args.sources:
        path = pathlib.Path(raw).expanduser()
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*") if p.suffix.lower() in (".md", ".txt", ".html", ".htm")))
        elif path.is_file():
            files.append(path)
        else:
            print(f"ERROR: нет такого файла или каталога: {path}", file=sys.stderr)
            return 2
    if not files:
        print("ERROR: в источниках нет .md/.txt/.html текстов", file=sys.stderr)
        return 2
    budget = max(1000, args.max_chars)
    samples: list[str] = []
    for path in files:
        if budget <= 0:
            break
        text = _sample_text(path)[:budget]
        if text:
            samples.append(f"### {path.name}\n\n{text}")
            budget -= len(text)
    profile_path = bv.display_path(root, bv.profile_path(cfg, root))
    print("\n".join([
        "# Задача: вывести профиль голоса бренда из опубликованных текстов",
        "",
        f"Ниже — {len(samples)} фрагментов текстов проекта. Заполни YAML-профиль по схеме из шаблона",
        f"(после блока образцов) и верни ТОЛЬКО YAML для файла `{profile_path}`.",
        "",
        "Правила:",
        "- Атрибуты голоса — пары `be` / `not` с примерами из текстов, а не общие слова.",
        "- `voice.address`: vy, если в текстах «вы»; ty — «ты»; impersonal — нет обращения.",
        "- `lexicon.preferred`: варианты терминов, которые текст использует последовательно.",
        "- `methods.page_types.*.structure`: порядок блоков, который реально встречается в образцах.",
        "- Не выдумывай авторов, цифры и факты; чего нет в образцах — оставь пустым.",
        "- Сохрани все ключи шаблона; комментарии можно опустить.",
        "",
        "## Образцы текстов",
        "",
        *samples,
        "",
        "## Схема (шаблон профиля)",
        "",
        "```yaml",
        bv.template_text().rstrip(),
        "```",
    ]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="seo-cycle.yaml (по умолчанию — ближайший вверх от текущего каталога)")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Создать профиль из шаблона и значений seo-cycle.yaml")
    init.add_argument("--write", action="store_true", help="Записать файл (без флага — показать)")
    init.add_argument("--force", action="store_true", help="Перезаписать существующий профиль")
    validate = sub.add_parser("validate", help="Проверить структуру и незаполненные поля")
    validate.add_argument("--format", choices=("md", "json"), default="md")
    show = sub.add_parser("show", help="Показать блок профиля для брифа")
    show.add_argument("--page-type", default=None, help=f"Тип страницы ({', '.join(PAGE_TYPES)} или page_type из outline)")
    show.add_argument("--format", choices=("md", "json"), default="md")
    check = sub.add_parser("check", help="Проверить черновик по профилю")
    check.add_argument("draft")
    check.add_argument("--page-type", default=None)
    check.add_argument("--format", choices=("md", "json"), default="md")
    extract = sub.add_parser("extract-prompt", help="Запрос для модели: вывести профиль из опубликованных текстов")
    extract.add_argument("--from", dest="sources", nargs="+", required=True, help="Файлы или каталоги .md/.txt/.html")
    extract.add_argument("--max-chars", type=int, default=MAX_SAMPLE_CHARS, help="Сколько символов образцов включить")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project = resolve_project(args.config)
    if project is None:
        return 2
    root, cfg = project
    handlers = {
        "init": cmd_init,
        "validate": cmd_validate,
        "show": cmd_show,
        "check": cmd_check,
        "extract-prompt": cmd_extract_prompt,
    }
    return handlers[args.command](args, root, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
