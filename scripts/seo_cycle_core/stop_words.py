"""Stop-word detection shared by `check-stop-words.py` and the draft gate (3.1.0).

Built-in RU/EN patterns account for Russian inflection. Extra simple words
and regexes come from `seo-cycle.yaml` (`tone.stop_words_extra`,
`tone.stop_words_regex_extra`). Quotes, code, HTML comments, `<script>`
blocks and the frontmatter are ignored.

3.1.0 fixes over the pre-3.1 script:
- ignored spans are blanked IN PLACE (every character but the newline
  becomes a space), so line numbers and the context line point at the real
  line of the file — before, a 4-line frontmatter moved every hit 4 lines up;
- the frontmatter is recognised only at the start of the file — two `---`
  horizontal rules in the body no longer swallow the text between them;
- quotes are single-line, and `'` counts as a quote only outside a word —
  apostrophes («It's … Don't») no longer swallow text across lines;
- hits are de-duplicated by (line, span): «лучший» matched by both the
  built-in pattern and `tone.stop_words_extra` is one hit, not two.
"""

from __future__ import annotations

import re
from typing import Any

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

# (pattern, flags) — blanked before matching; positions are preserved.
IGNORE_PATTERNS: tuple[tuple[str, int], ...] = (
    (r"\A---[ \t]*\r?\n.*?\r?\n---[ \t]*(?=\r?\n|\Z)", re.S),  # YAML frontmatter (start of file only)
    (r"```.*?```", re.S),                     # fenced code
    (r"<!--.*?-->", re.S),                    # HTML comments
    (r"<script[^>]*>.*?</script>", re.S | re.I),  # JSON-LD blocks
    (r"`[^`\n]+`", 0),                        # inline code
    (r'"[^"\n]*"', 0),
    (r"(?<!\w)'[^'\n]*'(?!\w)", 0),         # 'quote', not an apostrophe
    (r"«[^»\n]*»", 0),
    (r"“[^”\n]*”", 0),
)


def _blank(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def strip_ignored(text: str) -> str:
    """Blank ignored spans; the result has the same length and line breaks."""
    out = text
    for pattern, flags in IGNORE_PATTERNS:
        out = re.sub(pattern, _blank, out, flags=flags)
    return out


def patterns_for(lang: str) -> list[tuple[str, str]]:
    patterns: list[tuple[str, str]] = []
    if lang in ("ru", "both"):
        patterns.extend(RU_PATTERNS)
    if lang in ("en", "both"):
        patterns.extend(EN_PATTERNS)
    return patterns


def resolve_lang(lang: str, cfg: Any) -> str:
    """`auto` → `locale.language` of the config (default ru)."""
    if lang != "auto":
        return lang
    locale = cfg.get("locale") if isinstance(cfg, dict) else None
    value = locale.get("language") if isinstance(locale, dict) else None
    return str(value).strip().lower() if isinstance(value, str) and value.strip() else "ru"


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, (str, int, float)) and str(item).strip()]
    return []


def extra_rules(cfg: Any) -> tuple[list[str], list[str]]:
    """(extra simple words, extra regexes) from `tone.*` — tolerant of bad shapes."""
    tone = cfg.get("tone") if isinstance(cfg, dict) else None
    if not isinstance(tone, dict):
        return [], []
    return _string_list(tone.get("stop_words_extra")), _string_list(tone.get("stop_words_regex_extra"))


def find_violations(
    text: str,
    patterns: list[tuple[str, str]],
    simple_words: list[str],
) -> list[tuple[int, str, str, str]]:
    """`(line, category, match, context)` for every distinct hit, in text order."""
    clean = strip_ignored(text)
    lines_clean = clean.splitlines()
    lines_orig = text.splitlines()
    hits: dict[tuple[int, int, int], tuple[int, str, str, str]] = {}
    compiled = []
    for category, pattern in patterns:
        try:
            compiled.append((category, re.compile(pattern)))
        except re.error:
            continue
    words = []
    for word in simple_words:
        word = word.strip()
        if not word:
            continue
        if " " in word:
            words.append(re.compile(re.escape(word), re.I))
        else:
            words.append(re.compile(rf"(?u)\b{re.escape(word)}\b", re.I))
    for lineno, line in enumerate(lines_clean, 1):
        context = (lines_orig[lineno - 1] if lineno - 1 < len(lines_orig) else line).strip()[:120]
        for category, regex in compiled:
            for match in regex.finditer(line):
                hits.setdefault((lineno, match.start(), match.end()), (lineno, category, match.group(0), context))
        for regex in words:
            for match in regex.finditer(line):
                hits.setdefault((lineno, match.start(), match.end()), (lineno, "extra", match.group(0), context))
    return [hits[key] for key in sorted(hits)]
