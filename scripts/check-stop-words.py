#!/usr/bin/env python3
"""
check-stop-words.py — детектор стоп-слов с поддержкой морфологических форм.

Универсальный (project-agnostic):
- Базовые regex-паттерны (RU + EN) встроены в скрипт
- Доп. паттерны / простые слова — из seo-cycle.yaml (`tone.stop_words_extra`)
- Игнорирует цитаты («...» / "..." / '...'), code blocks, frontmatter, JSON-LD

Использование:
    python3 check-stop-words.py <file.md> [<file2.md> ...]
    python3 check-stop-words.py --config ./seo-cycle.yaml content.md
    python3 check-stop-words.py --extra-words "лучший,уникальный" file.md
    python3 check-stop-words.py --lang en file.md

Выход:
    0 — ничего не найдено
    1 — найдены стоп-слова (детали в stdout)
    2 — ошибка
"""

from __future__ import annotations
import argparse, pathlib, re, sys

try:
    import yaml
except ImportError:
    yaml = None


# Паттерны учитывают морфологию (русские прилагательные имеют падежи/род/число).
# (?ui) = unicode + case-insensitive.
RU_PATTERNS = [
    # Эпитеты качества — все формы через альтернацию окончаний
    ("эпитет", r"(?ui)\bлучш(ий|ая|ее|ие|их|им|ими|ему|его)\b"),
    ("эпитет", r"(?ui)\bкачественн(ый|ая|ое|ые|ых|ого|ому|ыми)\b"),
    ("эпитет", r"(?ui)\bвысококачественн(ый|ая|ое|ые|ых)\b"),
    ("эпитет", r"(?ui)\bпремиальн(ый|ая|ое|ые)\b"),
    ("эпитет", r"(?ui)\bэксклюзивн(ый|ая|ое|ые)\b"),
    ("эпитет", r"(?ui)\bуникальн(ый|ая|ое|ые|ых|ому)\b"),
    ("эпитет", r"(?ui)\bнепревзойдённ(ый|ая|ое|ые)\b"),
    ("эпитет", r"(?ui)\bбезупречн(ый|ая|ое|ые)\b"),
    ("эпитет", r"(?ui)\bидеальн(ый|ая|ое|ые)\b"),
    ("эпитет", r"(?ui)\bведущ(ий|ая|ее|ие|их|ему)\b"),
    ("эпитет", r"(?ui)\bпередов(ой|ая|ое|ые)\b"),
    ("эпитет", r"(?ui)\bопытн(ый|ая|ое|ые|ых)\b"),
    ("эпитет", r"(?ui)\bмноголетн(ий|яя|ее|ие)\b"),
    ("эпитет", r"(?ui)\bпрофессиональн(ая|ое|ые)\s+(команда|поддержка|обслуживание|подход)\b"),
    ("эпитет", r"(?ui)\bинновационн(ый|ая|ое|ые)\b"),
    # Маркетинговые обещания
    ("обещание", r"(?ui)\bвыгодн(ый|ая|ое|ые|ой|ою|ыми)\b"),
    ("обещание", r"(?ui)\bвыгоднее всех\b"),
    ("обещание", r"(?ui)\bгибкая система скидок\b"),
    ("обещание", r"(?ui)\bиндивидуальн(ый|ая|ое|ые)\s+подход(а|у|ом)?\b"),
    ("обещание", r"(?ui)\bкомплексн(ое|ые)\s+решени(е|я|ями?)?\b"),
    ("обещание", r"(?ui)\bполный спектр\b"),
    ("обещание", r"(?ui)\bширочайш(ий|ая|ее|ие)\b"),
    ("обещание", r"(?ui)\bогромн(ый|ая|ое|ые)\b"),
    ("обещание", r"(?ui)\bкрупнейш(ий|ая|ее|ие)\b"),
    ("обещание", r"(?ui)\bгарантия качества\b"),
    ("обещание", r"(?ui)\b100\s*%\s*качеств"),
    ("обещание", r"(?ui)\bне имеет аналогов\b"),
    ("обещание", r"(?ui)\bне имеет конкурентов\b"),
    ("обещание", r"(?ui)\bширок(ий|ая|ое|ие)\s+ассортимент"),
    # Фейк-цифры (общие — проверять)
    ("цифра", r"(?ui)\bболее\s+10\s+лет\b"),
    ("цифра", r"(?ui)\b1000\+ клиент"),
    ("цифра", r"(?ui)\b№\s*1\b"),
]

EN_PATTERNS = [
    ("epithet", r"(?i)\bthe best\b"),
    ("epithet", r"(?i)\bbest[- ]in[- ]class\b"),
    ("epithet", r"(?i)\bnumber one\b"),
    ("epithet", r"(?i)\bworld[- ]class\b"),
    ("epithet", r"(?i)\bpremium quality\b"),
    ("epithet", r"(?i)\bhigh[- ]quality\b"),
    ("epithet", r"(?i)\bleading provider\b"),
    ("epithet", r"(?i)\bcutting[- ]edge\b"),
    ("epithet", r"(?i)\bstate[- ]of[- ]the[- ]art\b"),
    ("epithet", r"(?i)\bone[- ]of[- ]a[- ]kind\b"),
    ("epithet", r"(?i)\binnovative solution"),
    ("epithet", r"(?i)\bultimate (guide|solution)"),
    ("promise", r"(?i)\b100%\s+(quality|guarantee|satisfaction)\b"),
    ("promise", r"(?i)\bsecond to none\b"),
    ("promise", r"(?i)\bunmatched\b"),
    ("promise", r"(?i)\bunparalleled\b"),
]


IGNORE_PATTERNS = [
    r'"[^"]*"',
    r"'[^']*'",
    r'«[^»]*»',
    r'“[^”]*”',
    r'```.*?```',                 # code fenced (DOTALL)
    r'`[^`]+`',                   # inline code
    r'<!--.*?-->',                # HTML comments
    r'^---\s*$.*?^---\s*$',       # YAML frontmatter
    r'<script[^>]*>.*?</script>', # JSON-LD blocks
]


def load_extra(config_path: pathlib.Path) -> tuple[list[str], list[str]]:
    """Returns (extra_simple_words, extra_regex_patterns)."""
    if not yaml or not config_path.exists():
        return [], []
    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        tone = cfg.get("tone", {})
        simple = tone.get("stop_words_extra", []) or []
        regex = tone.get("stop_words_regex_extra", []) or []
        return simple, regex
    except Exception as e:
        print(f"⚠ failed to read config {config_path}: {e}", file=sys.stderr)
        return [], []


def strip_ignored(text: str) -> str:
    out = text
    out = re.sub(IGNORE_PATTERNS[4], "", out, flags=re.DOTALL)
    out = re.sub(IGNORE_PATTERNS[5], "", out)
    out = re.sub(IGNORE_PATTERNS[6], "", out, flags=re.DOTALL)
    out = re.sub(IGNORE_PATTERNS[7], "", out, flags=re.MULTILINE | re.DOTALL)
    out = re.sub(IGNORE_PATTERNS[8], "", out, flags=re.DOTALL | re.IGNORECASE)
    for pat in IGNORE_PATTERNS[:4]:
        out = re.sub(pat, "", out)
    return out


def find_violations(text: str, patterns: list[tuple[str, str]], simple_words: list[str]):
    clean = strip_ignored(text)
    lines_clean = clean.splitlines()
    lines_orig = text.splitlines()
    violations = []
    for lineno, line in enumerate(lines_clean, 1):
        for category, pat in patterns:
            for m in re.finditer(pat, line):
                orig = lines_orig[lineno - 1] if lineno - 1 < len(lines_orig) else line
                violations.append((lineno, category, m.group(0), orig.strip()[:120]))
        line_lower = line.lower()
        for w in simple_words:
            wlow = w.lower()
            if " " in wlow:
                if wlow in line_lower:
                    orig = lines_orig[lineno - 1] if lineno - 1 < len(lines_orig) else line
                    violations.append((lineno, "extra", w, orig.strip()[:120]))
            else:
                if re.search(rf"(?u)\b{re.escape(wlow)}\b", line_lower):
                    orig = lines_orig[lineno - 1] if lineno - 1 < len(lines_orig) else line
                    violations.append((lineno, "extra", w, orig.strip()[:120]))
    return violations


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--config", default="seo-cycle.yaml",
                    help="Путь к seo-cycle.yaml")
    ap.add_argument("--lang", default="auto",
                    help="auto | ru | en | both (default: auto — определяется по конфигу)")
    ap.add_argument("--extra-words", default="",
                    help="Доп. простые слова через запятую")
    args = ap.parse_args()

    cfg_path = pathlib.Path(args.config)
    extra_simple, extra_regex = load_extra(cfg_path)
    if args.extra_words:
        extra_simple.extend([w.strip() for w in args.extra_words.split(",") if w.strip()])

    # Определяем язык
    lang = args.lang
    if lang == "auto" and cfg_path.exists() and yaml:
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
            cfg_lang = cfg.get("locale", {}).get("language", "ru")
            lang = cfg_lang
        except Exception:
            lang = "ru"
    if lang == "auto":
        lang = "ru"

    patterns = []
    if lang in ("ru", "both"):
        patterns.extend(RU_PATTERNS)
    if lang in ("en", "both"):
        patterns.extend(EN_PATTERNS)
    if not patterns and lang not in ("ru", "en", "both"):
        # Чужой язык — только пользовательские правила
        print(f"⚠ Язык {lang!r} не поддерживается встроенными паттернами — используем только extra-words и regex_extra из конфига", file=sys.stderr)

    # Добавляем extra regex из конфига
    for r in extra_regex:
        patterns.append(("custom-regex", r))

    total = 0
    for f in args.files:
        p = pathlib.Path(f)
        if not p.exists():
            print(f"⚠ {p}: не существует", file=sys.stderr)
            continue
        text = p.read_text(encoding="utf-8")
        v = find_violations(text, patterns, extra_simple)
        if not v:
            print(f"✓ {p}: чисто ({len(patterns)} паттернов, {len(extra_simple)} простых слов)")
        else:
            print(f"❌ {p}: {len(v)} нарушений")
            for lineno, cat, match, ctx in v:
                print(f"  L{lineno} [{cat}] «{match}» → {ctx}")
            total += len(v)

    sys.exit(1 if total > 0 else 0)


if __name__ == "__main__":
    main()
