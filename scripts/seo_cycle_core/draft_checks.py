"""Config-driven checks of a copy draft (3.1.0) — the body of the draft gate.

`skills/seo-writing/SKILL.md` always promised that stop-words, the
fact-check log and image alt/captions block publication, and the project
config carried the thresholds (`quality_gates.*`, `images.*`,
`content_rules.*`). Until 3.1.0 nothing read them: a 30-word draft full of
«лучший/уникальный», with an image without alt and no `fact_check_log`,
passed `draft-quality-gate.py` with zero findings.

Rules of engagement:
- a check runs only when its key is EXPLICITLY present and enabled in the
  config — a minimal config (`project` + `governance`) keeps the pre-3.1
  behaviour, the config template enables everything;
- a rule whose value is still an example from the template
  (`placeholders.is_placeholder`) is skipped and reported in
  `skipped_checks` — the demo «Мытищи» must not be required from a Kazan shop;
- findings carry line numbers in `message`: the quality loop keeps only
  `id`/`severity`/`message` (`seo_cycle_core.loop.normalize_findings`).
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from .config import boolish, coerce_int, nested_get
from .frontmatter import Frontmatter
from .page_types import is_article_like, word_count_bucket
from .placeholders import is_placeholder
from .stop_words import extra_rules, find_violations, patterns_for, resolve_lang
from .textmatch import TOKEN_RE, stem_token

MAX_STOP_WORD_FINDINGS = 50

# Image types (markdown title / data-type) that are not inline body images.
NON_INLINE_TYPES = {"hero", "featured", "cover", "og", "icon", "decorative", "logo"}
GENERIC_ALTS = {
    "image", "img", "photo", "picture", "pic", "картинка", "фото", "фотография",
    "изображение", "рисунок", "иллюстрация", "screenshot", "скриншот",
}
DISPUTED_VERDICTS = {"спорно", "недостоверно", "disputed", "false", "incorrect", "unverified"}

MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+[\"']([^\"']*)[\"'])?\s*\)")
HTML_IMAGE_RE = re.compile(r"<img\b[^>]*>", re.I)
ATTR_RE = re.compile(r"""\b([a-z-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
MD_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^\"']*[\"'])?\s*\)")
CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
HTML_TAG_RE = re.compile(r"<[^>]+>")
URL_RE = re.compile(r"https?://\S+")
WORD_RE = re.compile(r"[^\W_]+(?:[-’'][^\W_]+)*", re.U)


@dataclasses.dataclass
class CheckResult:
    findings: list[dict[str, Any]]
    checks_run: list[str]
    skipped: list[dict[str, str]]


@dataclasses.dataclass(frozen=True)
class Image:
    line: int
    alt: str | None
    src: str
    kind: str
    html: bool


def _finding(fid: str, severity: str, message: str, location: str) -> dict[str, Any]:
    return {"id": fid, "severity": severity, "location": location, "message": message}


def _section(cfg: dict[str, Any], dotted: str) -> dict[str, Any] | None:
    value = nested_get(cfg, dotted)
    return value if isinstance(value, dict) else None


def _enabled(cfg: dict[str, Any], dotted: str) -> bool:
    section = _section(cfg, dotted)
    return section is not None and boolish(section.get("enabled"), False)


def _lines(numbers: list[int], limit: int = 8) -> str:
    shown = ", ".join(str(n) for n in numbers[:limit])
    return shown + (f" и ещё {len(numbers) - limit}" if len(numbers) > limit else "")


def strip_markup(text: str) -> str:
    text = CODE_FENCE_RE.sub(" ", text)
    text = INLINE_CODE_RE.sub(" ", text)
    text = MD_IMAGE_RE.sub(" ", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = HTML_TAG_RE.sub(" ", text)
    return URL_RE.sub(" ", text)


def count_words(body: str) -> int:
    return sum(1 for word in WORD_RE.findall(strip_markup(body)) if any(ch.isalnum() for ch in word))


def _attrs(tag: str) -> dict[str, str]:
    return {m.group(1).lower(): next(v for v in m.groups()[1:] if v is not None) for m in ATTR_RE.finditer(tag)}


def find_images(text: str, line_offset: int = 0) -> list[Image]:
    """Markdown and HTML images; `kind` = the md title or data-type/class hint."""
    images: list[Image] = []
    in_code = False
    for index, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        for match in MD_IMAGE_RE.finditer(line):
            images.append(Image(index + line_offset, match.group(1), match.group(2),
                                (match.group(3) or "").strip().lower(), False))
        for match in HTML_IMAGE_RE.finditer(line):
            attrs = _attrs(match.group(0))
            kind = (attrs.get("data-type") or "").strip().lower()
            if not kind and "decorative" in (attrs.get("class") or "").lower():
                kind = "decorative"
            if not kind and attrs.get("role", "").lower() == "presentation":
                kind = "decorative"
            images.append(Image(index + line_offset, attrs.get("alt"), attrs.get("src", ""), kind, True))
    return images


def _caption_follows(lines: list[str], index: int, html: bool) -> bool:
    """Caption = the next non-empty line in italics, or a <figcaption> nearby."""
    window = lines[index: index + 4]
    if any("<figcaption" in line.lower() for line in window):
        return True
    current = lines[index - 1] if 0 < index <= len(lines) else ""
    tail = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", current).strip()
    if tail and re.fullmatch(r"(\*[^*].*\*|_[^_].*_)", tail):
        return True
    for line in lines[index:]:
        stripped = line.strip()
        if not stripped:
            continue
        return bool(re.fullmatch(r"(\*[^*].*\*|_[^_].*_)", stripped))
    return False


def _is_generic_alt(alt: str, src: str) -> bool:
    value = alt.strip().lower().strip(".")
    stem = re.sub(r"\.[a-z0-9]{2,5}$", "", src.rsplit("/", 1)[-1].lower())
    return value in GENERIC_ALTS or (bool(stem) and value == stem) or bool(re.fullmatch(r"(img|dsc|image|photo)[-_]?\d+", value))


def _local_key(token: str) -> str:
    stem = stem_token(token)
    return stem if len(stem) >= 4 else token


def count_local_signals(body: str, examples: list[str]) -> int:
    tokens = [_local_key(token) for token in TOKEN_RE.findall(strip_markup(body).lower().replace("ё", "е"))]
    total = 0
    for example in examples:
        phrase = [_local_key(token) for token in TOKEN_RE.findall(str(example).lower().replace("ё", "е"))]
        if not phrase:
            continue
        size = len(phrase)
        total += sum(1 for i in range(len(tokens) - size + 1) if tokens[i:i + size] == phrase)
    return total


def _domain(cfg: dict[str, Any]) -> str:
    raw = nested_get(cfg, "project.domain")
    if not isinstance(raw, str):
        return ""
    value = re.sub(r"^https?://", "", raw.strip().lower()).split("/", 1)[0]
    return value.removeprefix("www.")


def count_internal_links(body: str, domain: str) -> int:
    targets = set()
    for match in MD_LINK_RE.finditer(body):
        target = match.group(1).strip()
        if target.startswith("/") and not target.startswith("//"):
            targets.add(target.split("#", 1)[0].rstrip("/") or "/")
        elif domain:
            host = re.sub(r"^https?://", "", target.lower()).split("/", 1)[0].removeprefix("www.")
            if target.lower().startswith(("http://", "https://")) and host == domain:
                path = "/" + target.split("/", 3)[3] if target.count("/") >= 3 else "/"
                targets.add(path.split("#", 1)[0].rstrip("/") or "/")
    return len(targets)


def run_config_checks(
    text: str,
    front: Frontmatter,
    cfg: dict[str, Any],
    page_type: str,
    location: str,
) -> CheckResult:
    findings: list[dict[str, Any]] = []
    checks_run: list[str] = []
    skipped: list[dict[str, str]] = []
    body = front.body
    offset = front.body_start_line - 1

    # --- stop-words ------------------------------------------------------
    stop_cfg = _section(cfg, "quality_gates.stop_words_check")
    if stop_cfg is not None and boolish(stop_cfg.get("enabled"), False):
        checks_run.append("stop_words")
        severity = "error" if boolish(stop_cfg.get("fail_on_match"), True) else "warning"
        simple, regexes = extra_rules(cfg)
        patterns = patterns_for(resolve_lang("auto", cfg)) + [("custom-regex", r) for r in regexes]
        by_term: dict[str, list[int]] = {}
        for lineno, _category, match, _context in find_violations(text, patterns, simple):
            by_term.setdefault(match.lower(), []).append(lineno)
        for term, lines in list(by_term.items())[:MAX_STOP_WORD_FINDINGS]:
            findings.append(_finding(
                "stop_words_found", severity,
                f"Стоп-слово «{term}» (строки {_lines(lines)}): замени конкретикой — цифрой, свойством, условием.",
                location,
            ))

    # --- fact-check log ----------------------------------------------------
    if _enabled(cfg, "quality_gates.fact_check_log_present"):
        checks_run.append("fact_check_log")
        log = front.data.get("fact_check_log") if front.data else None
        if not isinstance(log, list) or not log:
            findings.append(_finding(
                "fact_check_log_missing", "error",
                "Нет `fact_check_log` во frontmatter (claim/source/url/verdict/checked): проверь факты реальными источниками и запиши лог.",
                location,
            ))
        else:
            incomplete = [i for i, row in enumerate(log, 1)
                          if not isinstance(row, dict) or not row.get("claim") or not row.get("verdict")
                          or not (row.get("source") or row.get("url"))]
            if incomplete:
                findings.append(_finding(
                    "fact_check_log_incomplete", "warning",
                    f"Записи `fact_check_log` без claim, source/url или verdict: №{_lines(incomplete)}.",
                    location,
                ))
            disputed = [str(row.get("claim"))[:80] for row in log
                        if isinstance(row, dict) and str(row.get("verdict") or "").strip().lower() in DISPUTED_VERDICTS]
            if disputed:
                findings.append(_finding(
                    "fact_check_claim_disputed", "warning",
                    "Утверждения со статусом «спорно/недостоверно» остались в тексте — перепиши формулировку, а не ищи подтверждение: "
                    + "; ".join(disputed[:5]),
                    location,
                ))

    # --- images ------------------------------------------------------------
    images = find_images(body, offset)
    text_lines = text.splitlines()
    alt_cfg = _section(cfg, "images.alt")
    if alt_cfg is not None and boolish(alt_cfg.get("required"), False):
        checks_run.append("image_alt")
        missing = [img.line for img in images if img.kind != "decorative" and not (img.alt or "").strip()]
        featured = front.data.get("featured_image") if front.data else None
        if featured and not any(front.data.get(key) for key in ("featured_image_alt", "featured_alt", "image_alt")):
            findings.append(_finding("image_missing_alt", "error",
                                     "У `featured_image` во frontmatter нет `featured_image_alt`.", location))
        if missing:
            findings.append(_finding(
                "image_missing_alt", "error",
                f"Изображения без alt (строки {_lines(missing)}): опиши, что на картинке и какая сущность; декоративным поставь тип «decorative».",
                location,
            ))
        generic = [img.line for img in images if (img.alt or "").strip() and _is_generic_alt(img.alt or "", img.src)]
        if generic:
            findings.append(_finding("image_generic_alt", "warning",
                                     f"Пустой по смыслу alt (image/фото/имя файла) на строках {_lines(generic)}.", location))
    captions = _section(cfg, "images.captions")
    inline_images = [img for img in images if img.kind not in NON_INLINE_TYPES]
    if captions is not None and boolish(captions.get("inline_required"), False) and str(captions.get("mode") or "") != "none":
        checks_run.append("image_captions")
        no_caption = [img.line for img in inline_images if not _caption_follows(text_lines, img.line, img.html)]
        if no_caption:
            findings.append(_finding(
                "image_missing_caption", "error",
                f"Inline-изображения без подписи (строки {_lines(no_caption)}): следующая строка курсивом `*…*` или <figcaption>.",
                location,
            ))
    inline_min = coerce_int(nested_get(cfg, "images.inline_min_per_post"), 0, name="images.inline_min_per_post")
    if inline_min > 0 and is_article_like(page_type):
        checks_run.append("inline_images_min")
        if len(inline_images) < inline_min:
            findings.append(_finding(
                "inline_images_below_min", "warning",
                f"Inline-изображений {len(inline_images)}, нужно не меньше {inline_min} (images.inline_min_per_post).",
                location,
            ))

    # --- word count --------------------------------------------------------
    words_cfg = _section(cfg, "quality_gates.word_count_min")
    if words_cfg is not None and boolish(words_cfg.get("enabled"), False):
        bucket = word_count_bucket(page_type)
        minimum = coerce_int(words_cfg.get(bucket), 0, name=f"quality_gates.word_count_min.{bucket}")
        if minimum > 0:
            checks_run.append("word_count")
            words = count_words(body)
            if words < minimum:
                findings.append(_finding(
                    "word_count_below_min", "error",
                    f"В тексте {words} слов, для типа «{bucket}» нужно не меньше {minimum} (quality_gates.word_count_min).",
                    location,
                ))

    # --- internal links ----------------------------------------------------
    min_links = coerce_int(nested_get(cfg, "content_rules.internal_linking.min_links_per_article"), 0,
                           name="content_rules.internal_linking.min_links_per_article")
    if min_links > 0 and is_article_like(page_type):
        checks_run.append("internal_links_min")
        links = count_internal_links(body, _domain(cfg))
        if links < min_links:
            findings.append(_finding(
                "internal_links_below_min", "warning",
                f"Внутренних ссылок {links}, нужно не меньше {min_links} (content_rules.internal_linking).",
                location,
            ))

    # --- local signals -----------------------------------------------------
    local = _section(cfg, "content_rules.local_signals")
    if local is not None:
        minimum = coerce_int(local.get("min_per_page"), 0, name="content_rules.local_signals.min_per_page")
        examples = [str(item) for item in local.get("examples") or [] if isinstance(item, (str, int))] \
            if isinstance(local.get("examples"), list) else []
        if minimum > 0 and examples:
            if is_placeholder("content_rules.local_signals.examples", examples):
                skipped.append({"check": "local_signals", "reason": "content_rules.local_signals.examples — пример из шаблона"})
            else:
                checks_run.append("local_signals")
                found = count_local_signals(body, examples)
                if found < minimum:
                    findings.append(_finding(
                        "local_signals_below_min", "warning",
                        f"Локальных сигналов {found}, нужно не меньше {minimum}: {', '.join(examples[:6])}.",
                        location,
                    ))

    return CheckResult(findings, checks_run, skipped)
