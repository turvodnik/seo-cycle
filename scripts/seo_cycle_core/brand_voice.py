"""Per-project brand voice, writing methods and image types (3.1.0).

One file per project — `seo/brand/voice.yaml` (`policy_files.brand_voice_profile`)
— says how the brand writes: who we are and for whom, voice attributes as
«be / not» pairs, formality, address (на «вы»/«ты»), lexicon (preferred and
forbidden terms), style limits and typography, the block structure per page
type, real authors (E-E-A-T), and the image types with their source, style,
ratio and caption rules. Before 3.1.0 only `tone.stop_words_extra` of the
config was read by any script; the copywriter brief carried hard-coded
English «Tone Rules» identical for every project.

The profile is ACTIVE only when the file exists and `brand_voice.enabled` is
not `false`. There is no implicit fallback from `tone.*` at runtime — the
legacy section only pre-fills `seo-cycle voice init`. That keeps every
output of a project without a profile exactly as before.

Consumers:
- `scripts/brand-voice.py` (`seo-cycle voice init|validate|show|check|extract-prompt`);
- `page-outline-v3.py` — `brand_voice` block in the outline and a section in
  the copywriter-ready brief;
- `draft-quality-gate.py` — `check_draft()` findings;
- `context-pack.py` / `task-router.py` — the profile is read first for
  writing tasks; `setup-gap-audit.py` — unanswered fields (advisory).
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

from .config import (
    config_section,
    load_yaml,
    load_yaml_safe,
    nested_get,
    policy_path,
    rel_display,
    skill_root,
)
from .draft_checks import find_images
from .page_types import PAGE_TYPES, normalize_page_type
from .stop_words import find_violations

PROFILE_KEY = "brand_voice_profile"
DEFAULT_PROFILE = "seo/brand/voice.yaml"
TEMPLATE_PATH = skill_root() / "templates" / "project-policies" / "brand-voice.template.yaml"

ADDRESS_VALUES = ("vy", "ty", "you", "impersonal")
PERSON_VALUES = ("we", "brand", "impersonal")
HUMOR_VALUES = ("none", "light")
COMPETITOR_VALUES = ("dont_name", "neutral", "compare_fairly")
QUOTES_VALUES = ("«»", '""', "any")
DASH_VALUES = ("—", "any")
YO_VALUES = ("preserve", "any")
NUMBERS_VALUES = ("digits", "words", "any")
SOURCE_VALUES = ("photo", "stock", "generated", "screenshot", "catalog", "html_table", "diagram", "illustration")
CAPTION_VALUES = ("required", "optional", "none")
ENFORCE_VALUES = ("warn", "error")

# Fields `voice validate` / setup-gap-audit ask the owner to fill.
REQUIRED_FIELDS: tuple[tuple[str, str], ...] = (
    ("identity.who_we_are", "Кто вы: чем занимаетесь и чем отличаетесь (1–2 предложения)?"),
    ("identity.audiences", "Для кого пишете: аудитории с задачей и болями?"),
    ("voice.summary", "Как звучит бренд (1–3 предложения)?"),
    ("voice.attributes", "Какой у бренда голос в парах «это / а не это»?"),
    ("voice.address", "Обращаемся к читателю на «вы», на «ты» или без обращения?"),
    ("methods.default", "Какой метод письма по умолчанию (article, category, …)?"),
)

RU_TY = re.compile(r"(?<!\w)(ты|тебя|тебе|тобой|твой|твоя|твоё|твое|твои|твоих|твоим|твоими|твоей|твою)(?!\w)", re.I)
RU_VY = re.compile(r"(?<!\w)(вы|вас|вам|вами|ваш|ваша|ваше|ваши|вашего|вашей|вашим|вашими|ваших|вашу)(?!\w)", re.I)
EN_YOU = re.compile(r"(?<!\w)(you|your|yours|yourself)(?!\w)", re.I)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[«\"(A-ZА-ЯЁ0-9])")


class ProfileError(Exception):
    """A broken profile file (strict consumers turn it into exit 2)."""


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def profile_path(cfg: dict[str, Any], project_root: pathlib.Path) -> pathlib.Path:
    return policy_path(cfg, project_root, PROFILE_KEY, DEFAULT_PROFILE)


def settings(cfg: dict[str, Any]) -> dict[str, Any]:
    section = config_section(cfg, "brand_voice") if isinstance(cfg, dict) else {}
    enforce = str(section.get("enforce") or "warn").strip().lower()
    return {
        "enabled": section.get("enabled") is not False,
        "enforce": enforce if enforce in ENFORCE_VALUES else "warn",
        "require_review": section.get("require_review") is True,
    }


def load_profile(
    cfg: dict[str, Any],
    project_root: pathlib.Path,
    *,
    strict: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    """`(profile, None)` when active; `(None, None)` when absent/disabled;
    `(None, error)` when broken and `strict=False`. With `strict=True` a
    broken file exits 2 through `load_yaml` (one `ERROR:` line)."""
    if not settings(cfg)["enabled"]:
        return None, None
    path = profile_path(cfg, project_root)
    if not path.exists():
        return None, None
    if strict:
        strict_data = load_yaml(path)
        return (strict_data or None), None
    data, error = load_yaml_safe(path)
    if error:
        return None, error
    return (data or None), None


def template_text() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def _type_error(errors: list[str], dotted: str, value: Any, expected: type | tuple[type, ...], label: str) -> None:
    if value is not None and not isinstance(value, expected):
        errors.append(f"{dotted}: ожидался {label}, получено {type(value).__name__}")


def _enum_error(errors: list[str], dotted: str, value: Any, allowed: tuple[str, ...]) -> None:
    if value is not None and value not in allowed:
        errors.append(f"{dotted}: «{value}» — допустимо {', '.join(allowed)}")


def validate_profile(profile: Any) -> list[str]:
    """Structural and type errors only — empty fields are `unanswered_fields`."""
    if not isinstance(profile, dict):
        return [f"профиль должен быть словарём, получено {type(profile).__name__}"]
    errors: list[str] = []
    for key in ("identity", "voice", "lexicon", "style", "methods", "visuals", "examples"):
        _type_error(errors, key, profile.get(key), dict, "словарь")
    _type_error(errors, "authors", profile.get("authors"), list, "список")
    _type_error(errors, "disclaimers", profile.get("disclaimers"), list, "список")
    _type_error(errors, "first_person_allowed", profile.get("first_person_allowed"), bool, "true/false")
    get = lambda dotted: nested_get(profile, dotted)  # noqa: E731
    _type_error(errors, "identity.audiences", get("identity.audiences"), list, "список")
    _type_error(errors, "voice.attributes", get("voice.attributes"), list, "список")
    formality = get("voice.formality")
    if formality is not None and (isinstance(formality, bool) or not isinstance(formality, int) or not 1 <= formality <= 5):
        errors.append(f"voice.formality: нужно целое 1–5, получено {formality!r}")
    _enum_error(errors, "voice.address", get("voice.address"), ADDRESS_VALUES)
    _enum_error(errors, "voice.person", get("voice.person"), PERSON_VALUES)
    _enum_error(errors, "voice.humor", get("voice.humor"), HUMOR_VALUES)
    _type_error(errors, "lexicon.preferred", get("lexicon.preferred"), dict, "словарь «как не пишем → как пишем»")
    _type_error(errors, "lexicon.forbidden", get("lexicon.forbidden"), list, "список")
    _type_error(errors, "lexicon.forbidden_regex", get("lexicon.forbidden_regex"), list, "список")
    for index, pattern in enumerate(get("lexicon.forbidden_regex") or [] if isinstance(get("lexicon.forbidden_regex"), list) else []):
        try:
            re.compile(str(pattern))
        except re.error as exc:
            errors.append(f"lexicon.forbidden_regex[{index}]: регулярка не компилируется: {exc}")
    _enum_error(errors, "lexicon.competitors", get("lexicon.competitors"), COMPETITOR_VALUES)
    for dotted in ("style.sentence_max_words", "style.paragraph_max_sentences", "lexicon.brand_mentions.max_per_1000_words",
                   "methods.cta.max_per_page"):
        value = get(dotted)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            errors.append(f"{dotted}: нужно целое ≥ 0, получено {value!r}")
    _enum_error(errors, "style.typography.quotes", get("style.typography.quotes"), QUOTES_VALUES)
    _enum_error(errors, "style.typography.dash", get("style.typography.dash"), DASH_VALUES)
    _enum_error(errors, "style.typography.yo", get("style.typography.yo"), YO_VALUES)
    _enum_error(errors, "style.numbers", get("style.numbers"), NUMBERS_VALUES)
    default = get("methods.default")
    if default is not None and default not in PAGE_TYPES:
        errors.append(f"methods.default: «{default}» — допустимо {', '.join(PAGE_TYPES)}")
    _type_error(errors, "methods.page_types", get("methods.page_types"), dict, "словарь")
    types = get("visuals.types")
    _type_error(errors, "visuals.types", types, dict, "словарь")
    if isinstance(types, dict):
        for name, spec in types.items():
            if not isinstance(spec, dict):
                errors.append(f"visuals.types.{name}: ожидался словарь")
                continue
            _enum_error(errors, f"visuals.types.{name}.source", spec.get("source"), SOURCE_VALUES)
            _enum_error(errors, f"visuals.types.{name}.caption", spec.get("caption"), CAPTION_VALUES)
            _type_error(errors, f"visuals.types.{name}.text_on_image", spec.get("text_on_image"), bool, "true/false")
            minimum = spec.get("min_per_page")
            if minimum is not None and (isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0):
                errors.append(f"visuals.types.{name}.min_per_page: нужно целое ≥ 0")
    per_page = get("visuals.per_page_type")
    _type_error(errors, "visuals.per_page_type", per_page, dict, "словарь")
    if isinstance(per_page, dict) and isinstance(types, dict):
        for page_type, names in per_page.items():
            if not isinstance(names, list):
                errors.append(f"visuals.per_page_type.{page_type}: ожидался список типов")
                continue
            for name in names:
                if name not in types:
                    errors.append(f"visuals.per_page_type.{page_type}: тип «{name}» не описан в visuals.types")
    for index, author in enumerate(_as_list(profile.get("authors"))):
        if not isinstance(author, dict) or not author.get("name"):
            errors.append(f"authors[{index}]: нужен словарь с name (и proof_url)")
    return errors


def _filled(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_filled(item) if not isinstance(item, dict) else any(_filled(v) for v in item.values()) for item in value)
    if isinstance(value, dict):
        return any(_filled(item) for item in value.values())
    return value is not None


def unanswered_fields(profile: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"field": dotted, "question": question}
        for dotted, question in REQUIRED_FIELDS
        if not _filled(nested_get(profile, dotted))
    ]


# --------------------------------------------------------------------------
# brief
# --------------------------------------------------------------------------

def _method_key(profile: dict[str, Any], page_type: Any) -> str:
    aliases = nested_get(profile, "methods.aliases")
    raw = str(page_type or "")
    if isinstance(aliases, dict):
        for alias, target in aliases.items():
            if str(alias).strip().lower() == raw.strip().lower():
                return normalize_page_type(target)
    return normalize_page_type(page_type) if raw.strip() else str(nested_get(profile, "methods.default") or "article")


def method_for(profile: dict[str, Any], page_type: Any) -> dict[str, Any]:
    key = _method_key(profile, page_type)
    methods = nested_get(profile, "methods.page_types")
    spec = methods.get(key) if isinstance(methods, dict) else None
    if not isinstance(spec, dict):
        default = str(nested_get(profile, "methods.default") or "article")
        spec = methods.get(default) if isinstance(methods, dict) else None
        key = default if isinstance(spec, dict) else key
    spec = spec if isinstance(spec, dict) else {}
    structure = _as_list(spec.get("structure"))
    return {"page_type": key, "structure": [str(item) for item in structure], "notes": str(spec.get("notes") or "")}


def visuals_for(profile: dict[str, Any], page_type: Any) -> list[dict[str, Any]]:
    key = _method_key(profile, page_type)
    types = nested_get(profile, "visuals.types")
    per_page = nested_get(profile, "visuals.per_page_type")
    names = per_page.get(key) if isinstance(per_page, dict) else None
    if not isinstance(types, dict) or not isinstance(names, list):
        return []
    slots = []
    for name in names:
        spec = types.get(name)
        if not isinstance(spec, dict):
            continue
        slots.append({
            "type": str(name),
            "source": spec.get("source"),
            "style": spec.get("style") or nested_get(profile, "visuals.style") or "",
            "ratio": spec.get("ratio"),
            "text_on_image": spec.get("text_on_image"),
            "caption": spec.get("caption"),
            "min_per_page": spec.get("min_per_page"),
        })
    return slots


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, (str, int, float)) and str(item).strip()] if isinstance(value, list) else []


def has_real_author(profile: dict[str, Any] | None) -> bool:
    if not profile or profile.get("first_person_allowed") is not True:
        return False
    authors = profile.get("authors")
    return isinstance(authors, list) and any(
        isinstance(author, dict) and author.get("name") and author.get("proof_url") for author in authors
    )


def brief_block(profile: dict[str, Any], page_type: Any, profile_display: str = DEFAULT_PROFILE) -> dict[str, Any]:
    attributes = []
    for item in _as_list(nested_get(profile, "voice.attributes")):
        if isinstance(item, dict) and (item.get("be") or item.get("not")):
            attributes.append({"be": str(item.get("be") or ""), "not": str(item.get("not") or "")})
        elif isinstance(item, str) and item.strip():
            attributes.append({"be": item.strip(), "not": ""})
    audiences = []
    for item in _as_list(nested_get(profile, "identity.audiences")):
        if isinstance(item, dict) and item.get("name"):
            audiences.append({"name": str(item.get("name")), "task": str(item.get("task") or ""), "pains": _strings(item.get("pains"))})
    preferred = nested_get(profile, "lexicon.preferred")
    authors = _as_list(profile.get("authors"))
    return {
        "profile": profile_display,
        "language": str(profile.get("language") or "ru"),
        "brand_name": str(nested_get(profile, "identity.brand_name") or ""),
        "who_we_are": str(nested_get(profile, "identity.who_we_are") or ""),
        "audiences": audiences,
        "summary": str(nested_get(profile, "voice.summary") or ""),
        "attributes": attributes,
        "formality": nested_get(profile, "voice.formality"),
        "address": nested_get(profile, "voice.address") or "",
        "person": nested_get(profile, "voice.person") or "",
        "lexicon": {
            "preferred": {str(k): str(v) for k, v in preferred.items()} if isinstance(preferred, dict) else {},
            "forbidden": _strings(nested_get(profile, "lexicon.forbidden")),
            "competitors": nested_get(profile, "lexicon.competitors") or "",
        },
        "style": {
            "sentence_max_words": nested_get(profile, "style.sentence_max_words"),
            "paragraph_max_sentences": nested_get(profile, "style.paragraph_max_sentences"),
            "quotes": nested_get(profile, "style.typography.quotes"),
            "dash": nested_get(profile, "style.typography.dash"),
            "numbers": nested_get(profile, "style.numbers"),
        },
        "method": method_for(profile, page_type),
        "cta": nested_get(profile, "methods.cta") if isinstance(nested_get(profile, "methods.cta"), dict) else {},
        "visual_slots": visuals_for(profile, page_type),
        "first_person_allowed": has_real_author(profile),
        "authors": [str(a.get("name")) for a in authors if isinstance(a, dict) and a.get("name")],
        "examples": {"good": _strings(nested_get(profile, "examples.good")), "bad": _strings(nested_get(profile, "examples.bad"))},
        "disclaimers": _strings(profile.get("disclaimers")),
    }


_LABELS = {
    "ru": {
        "title": "Голос бренда и метод", "profile": "Профиль", "who": "Кто мы", "aud": "Для кого",
        "summary": "Как звучим", "be": "Да", "not": "Нет", "formality": "Формальность (1–5)",
        "address": "Обращение", "person": "От чьего лица", "method": "Метод для типа страницы",
        "structure": "Порядок блоков", "notes": "Заметки", "pref": "Пишем так", "forbidden": "Не пишем",
        "style": "Стиль", "visuals": "Изображения по профилю", "fp": "Первое лицо эксперта",
        "fp_yes": "разрешено (реальный автор: {names})", "fp_no": "запрещено — нейтральный экспертный тон",
        "examples": "Примеры", "disclaimers": "Обязательные оговорки", "cta": "CTA",
    },
    "en": {
        "title": "Brand voice and method", "profile": "Profile", "who": "Who we are", "aud": "Audience",
        "summary": "How we sound", "be": "Be", "not": "Not", "formality": "Formality (1–5)",
        "address": "Address", "person": "Voice of", "method": "Method for page type",
        "structure": "Block order", "notes": "Notes", "pref": "Write it as", "forbidden": "Never write",
        "style": "Style", "visuals": "Images from the profile", "fp": "Expert first person",
        "fp_yes": "allowed (real author: {names})", "fp_no": "not allowed — neutral expert voice",
        "examples": "Examples", "disclaimers": "Required disclaimers", "cta": "CTA",
    },
}
_ADDRESS = {"ru": {"vy": "на «вы»", "ty": "на «ты»", "you": "you", "impersonal": "без прямого обращения"},
            "en": {"vy": "formal you", "ty": "informal you", "you": "you", "impersonal": "impersonal"}}


def render_brief_markdown(block: dict[str, Any], heading_level: int = 2) -> list[str]:
    lang = "ru" if str(block.get("language", "ru")).lower().startswith("ru") else "en"
    labels = _LABELS[lang]
    h = "#" * heading_level
    lines = [f"{h} {labels['title']}", "", f"- {labels['profile']}: `{block.get('profile')}`"]
    if block.get("who_we_are"):
        lines.append(f"- {labels['who']}: {block['who_we_are']}")
    for audience in block.get("audiences", []):
        extra = f" — {audience['task']}" if audience.get("task") else ""
        pains = f" ({'; '.join(audience['pains'])})" if audience.get("pains") else ""
        lines.append(f"- {labels['aud']}: {audience['name']}{extra}{pains}")
    if block.get("summary"):
        lines.append(f"- {labels['summary']}: {block['summary']}")
    for item in block.get("attributes", []):
        lines.append(f"- {labels['be']}: {item['be']}" + (f" · {labels['not']}: {item['not']}" if item.get("not") else ""))
    if block.get("formality") is not None:
        lines.append(f"- {labels['formality']}: {block['formality']}")
    if block.get("address"):
        lines.append(f"- {labels['address']}: {_ADDRESS[lang].get(block['address'], block['address'])}")
    if block.get("person"):
        lines.append(f"- {labels['person']}: {block['person']}")
    names = ", ".join(block.get("authors") or [])
    lines.append(f"- {labels['fp']}: " + (labels["fp_yes"].format(names=names) if block.get("first_person_allowed") else labels["fp_no"]))
    method = block.get("method") or {}
    lines.extend(["", f"{h}# {labels['method']} `{method.get('page_type')}`", ""])
    if method.get("structure"):
        lines.append(f"- {labels['structure']}: " + " → ".join(f"`{step}`" for step in method["structure"]))
    if method.get("notes"):
        lines.append(f"- {labels['notes']}: {method['notes']}")
    cta = block.get("cta") or {}
    if cta:
        lines.append(f"- {labels['cta']}: {cta.get('style', '')}, max {cta.get('max_per_page', '')}")
    lexicon = block.get("lexicon") or {}
    for wrong, right in (lexicon.get("preferred") or {}).items():
        lines.append(f"- {labels['pref']}: «{right}» (не «{wrong}»)")
    if lexicon.get("forbidden"):
        lines.append(f"- {labels['forbidden']}: " + ", ".join(f"«{word}»" for word in lexicon["forbidden"]))
    style = block.get("style") or {}
    style_bits = [f"{key}={value}" for key, value in style.items() if value not in (None, "")]
    if style_bits:
        lines.append(f"- {labels['style']}: " + ", ".join(style_bits))
    if block.get("visual_slots"):
        lines.extend(["", f"{h}# {labels['visuals']}", ""])
        for slot in block["visual_slots"]:
            bits = [f"source={slot.get('source')}"]
            for key in ("ratio", "caption", "text_on_image", "min_per_page"):
                if slot.get(key) not in (None, ""):
                    bits.append(f"{key}={slot.get(key)}")
            style_text = f" — {slot['style']}" if slot.get("style") else ""
            lines.append(f"- `{slot['type']}`: {', '.join(bits)}{style_text}")
    examples = block.get("examples") or {}
    if examples.get("good") or examples.get("bad"):
        lines.extend(["", f"{h}# {labels['examples']}", ""])
        lines.extend(f"- ✓ `{path}`" for path in examples.get("good", []))
        lines.extend(f"- ✗ `{path}`" for path in examples.get("bad", []))
    if block.get("disclaimers"):
        lines.extend(["", f"{h}# {labels['disclaimers']}", ""])
        lines.extend(f"- {text}" for text in block["disclaimers"])
    return lines


# --------------------------------------------------------------------------
# draft checks
# --------------------------------------------------------------------------

def _finding(fid: str, severity: str, message: str, location: str) -> dict[str, Any]:
    return {"id": fid, "severity": severity, "location": location, "message": message}


def _lines(numbers: list[int], limit: int = 8) -> str:
    shown = ", ".join(str(n) for n in numbers[:limit])
    return shown + (f" и ещё {len(numbers) - limit}" if len(numbers) > limit else "")


def _prose_lines(text: str) -> list[tuple[int, str]]:
    """(line number, prose text) — no code, frontmatter, headings, tables,
    images, link targets/titles, HTML attributes or list markers."""
    out: list[tuple[int, str]] = []
    lines = text.splitlines()
    in_code = False
    start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() in ("---", "..."):
                start = index + 1
                break
    for index in range(start, len(lines)):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not stripped or stripped.startswith(("#", "|", ">")):
            continue
        clean = re.sub(r"`[^`\n]+`", " ", stripped)
        clean = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", clean)
        clean = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", clean)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", clean)
        if clean.strip():
            out.append((index + 1, clean))
    return out


def _paragraphs(prose: list[tuple[int, str]]) -> list[tuple[int, str]]:
    paragraphs: list[tuple[int, str]] = []
    current: list[str] = []
    first = 0
    last = -2
    for lineno, text in prose:
        if lineno != last + 1 and current:
            paragraphs.append((first, " ".join(current)))
            current = []
        if not current:
            first = lineno
        current.append(text)
        last = lineno
    if current:
        paragraphs.append((first, " ".join(current)))
    return paragraphs


def _sentences(text: str) -> list[str]:
    return [part for part in SENTENCE_SPLIT.split(text.strip()) if part.strip()]


def _word_count(text: str) -> int:
    return len(re.findall(r"[^\W_]+(?:[-’'][^\W_]+)*", text))


def check_draft(
    text: str,
    profile: dict[str, Any],
    *,
    page_type: Any,
    frontmatter: dict[str, Any],
    cfg: dict[str, Any],
    location: str,
    already_checked: set[str] | frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Measurable parts of the profile, checked on the draft text."""
    opts = settings(cfg)
    soft = "error" if opts["enforce"] == "error" else "warning"
    findings: list[dict[str, Any]] = []
    lang = "ru" if str(profile.get("language") or "ru").lower().startswith("ru") else "en"
    prose = _prose_lines(text)

    # forbidden terms (always error)
    forbidden = _strings(nested_get(profile, "lexicon.forbidden"))
    regexes = [("forbidden-regex", str(r)) for r in nested_get(profile, "lexicon.forbidden_regex") or []] \
        if isinstance(nested_get(profile, "lexicon.forbidden_regex"), list) else []
    if forbidden or regexes:
        by_term: dict[str, list[int]] = {}
        for lineno, _category, match, _context in find_violations(text, regexes, forbidden):
            by_term.setdefault(match.lower(), []).append(lineno)
        for term, lines in by_term.items():
            findings.append(_finding("voice_forbidden_term", "error",
                                     f"Слово «{term}» запрещено профилем голоса (строки {_lines(lines)}).", location))

    # preferred terms
    preferred = nested_get(profile, "lexicon.preferred")
    if isinstance(preferred, dict):
        for wrong, right in preferred.items():
            pattern = re.compile(rf"(?<!\w){re.escape(str(wrong))}(?!\w)", re.I)
            lines = [lineno for lineno, line in prose if pattern.search(line)]
            if lines:
                findings.append(_finding("voice_preferred_term", soft,
                                         f"Пиши «{right}», а не «{wrong}» (строки {_lines(lines)}).", location))

    # address
    address = nested_get(profile, "voice.address")
    if lang == "ru" and address in ("vy", "ty", "impersonal"):
        ty = [lineno for lineno, line in prose if RU_TY.search(line)]
        vy = [lineno for lineno, line in prose if RU_VY.search(line)]
        if address == "vy" and ty:
            findings.append(_finding("voice_address_mismatch", soft,
                                     f"Профиль: обращение на «вы», а в тексте «ты» (строки {_lines(ty)}).", location))
        elif address == "ty" and vy:
            findings.append(_finding("voice_address_mismatch", soft,
                                     f"Профиль: обращение на «ты», а в тексте «вы» (строки {_lines(vy)}).", location))
        elif address == "impersonal" and len(ty) + len(vy) > 3:
            findings.append(_finding("voice_address_mismatch", soft,
                                     f"Профиль: без прямого обращения, а в тексте «вы/ты» (строки {_lines(sorted(ty + vy))}).", location))
    elif lang == "en" and address == "impersonal":
        you = [lineno for lineno, line in prose if EN_YOU.search(line)]
        if len(you) > 3:
            findings.append(_finding("voice_address_mismatch", soft,
                                     f"Profile: impersonal voice, but the text addresses «you» (lines {_lines(you)}).", location))

    # sentence and paragraph length
    max_words = nested_get(profile, "style.sentence_max_words")
    share = nested_get(profile, "style.long_sentence_share")
    share = share if isinstance(share, (int, float)) and not isinstance(share, bool) and 0 <= share <= 1 else 0.2
    paragraphs = _paragraphs(prose)
    if isinstance(max_words, int) and not isinstance(max_words, bool) and max_words > 0:
        total = 0
        long_lines: list[int] = []
        for lineno, paragraph in paragraphs:
            for sentence in _sentences(paragraph):
                total += 1
                if _word_count(sentence) > max_words:
                    long_lines.append(lineno)
        if total and len(long_lines) >= 3 and len(long_lines) / total > share:
            findings.append(_finding(
                "voice_long_sentences", soft,
                f"{len(long_lines)} из {total} предложений длиннее {max_words} слов (абзацы со строк {_lines(sorted(set(long_lines)))}).",
                location,
            ))
    max_sentences = nested_get(profile, "style.paragraph_max_sentences")
    if isinstance(max_sentences, int) and not isinstance(max_sentences, bool) and max_sentences > 0:
        long_paragraphs = [lineno for lineno, paragraph in paragraphs if len(_sentences(paragraph)) > max_sentences]
        if long_paragraphs:
            findings.append(_finding("voice_long_paragraphs", soft,
                                     f"Абзацы длиннее {max_sentences} предложений (строки {_lines(long_paragraphs)}).", location))

    # typography
    if nested_get(profile, "style.typography.quotes") == "«»":
        straight = [lineno for lineno, line in prose if re.search(r'"[^"\n]+"', line)]
        if straight:
            findings.append(_finding("voice_typography_quotes", soft,
                                     f"Кавычки «ёлочки», а не \"прямые\" (строки {_lines(straight)}).", location))
    if nested_get(profile, "style.typography.dash") == "—":
        hyphens = [lineno for lineno, line in prose if re.search(r"\s-\s", line)]
        if hyphens:
            findings.append(_finding("voice_typography_dash", soft,
                                     f"Между словами длинное тире «—», а не дефис « - » (строки {_lines(hyphens)}).", location))

    # brand mentions
    brand = str(nested_get(profile, "identity.brand_name") or "").strip()
    limit = nested_get(profile, "lexicon.brand_mentions.max_per_1000_words")
    if brand and isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
        body_text = " ".join(line for _lineno, line in prose)
        words = max(1, _word_count(body_text))
        mentions = len(re.findall(rf"(?<!\w){re.escape(brand)}(?!\w)", body_text, re.I))
        allowed = max(1, round(limit * words / 1000))
        if mentions > allowed:
            findings.append(_finding("voice_brand_mentions_excess", soft,
                                     f"Бренд «{brand}» упомянут {mentions} раз на {words} слов (профиль: не больше {limit} на 1000).",
                                     location))

    # required visuals
    images = find_images(text)
    kinds = {image.kind for image in images}
    inline_count = sum(1 for image in images if image.kind not in {"hero", "featured", "cover", "og", "icon", "decorative", "logo"})
    for slot in visuals_for(profile, page_type):
        name = slot["type"]
        if name == "inline_photo":
            minimum = slot.get("min_per_page")
            if "inline_images_min" not in already_checked and isinstance(minimum, int) and minimum > inline_count:
                findings.append(_finding("inline_images_below_min", soft,
                                         f"Inline-изображений {inline_count}, профиль требует не меньше {minimum}.", location))
            continue
        if name == "comparison_table":
            if not re.search(r"^\s*\|.*\|\s*$", text, re.M) and "<table" not in text.lower():
                findings.append(_finding("visual_required_missing", soft,
                                         "Профиль требует для этого типа страницы таблицу сравнения.", location))
            continue
        present = name in kinds or (name in ("hero", "featured") and bool(frontmatter.get("featured_image")))
        if not present:
            findings.append(_finding(
                "visual_required_missing", soft,
                f"Нет изображения типа «{name}» (в черновике: ![alt](файл \"{name}\")) — профиль требует его для этого типа страницы.",
                location,
            ))

    # model self-review against the profile (opt-in)
    if opts["require_review"]:
        review = frontmatter.get("voice_review")
        verdict = str(review.get("verdict") or "").strip().lower() if isinstance(review, dict) else ""
        if not verdict:
            findings.append(_finding("voice_review_missing", soft,
                                     "Нет `voice_review` во frontmatter: сверь текст с профилем голоса и запиши verdict pass/needs_work.",
                                     location))
        elif verdict != "pass":
            findings.append(_finding("voice_review_needs_work", soft,
                                     f"Самопроверка по профилю голоса: {verdict} — доработай текст.", location))
    return findings


# --------------------------------------------------------------------------
# init (template + legacy config values)
# --------------------------------------------------------------------------

def _json(value: Any) -> str:
    # ensure_ascii=False: with the default escaping PyYAML turns an emoji
    # («\\ud83d\\ude00») into lone surrogates that cannot be written as UTF-8.
    return json.dumps(value, ensure_ascii=False)


def init_values(cfg: dict[str, Any]) -> dict[str, Any]:
    from .placeholders import is_placeholder, template_value

    tone = config_section(cfg, "tone")
    images = config_section(cfg, "images")
    project = config_section(cfg, "project")
    locale = config_section(cfg, "locale")
    language = str(locale.get("language") or "ru").strip().lower() or "ru"
    description = tone.get("description")
    summary = "" if not isinstance(description, str) or is_placeholder("tone.description", description) else " ".join(description.split())
    keywords = _as_list(tone.get("style_keywords"))
    attributes = [{"be": str(item), "not": ""} for item in keywords if isinstance(item, (str, int)) and str(item).strip()]
    formality = tone.get("formal_level")
    formality = formality if isinstance(formality, int) and not isinstance(formality, bool) and 1 <= formality <= 5 else 3
    audiences_raw = _as_list(cfg.get("target_audiences"))
    audiences = [] if audiences_raw == template_value("target_audiences") else [
        {"name": str(item), "task": "", "pains": []} for item in audiences_raw if isinstance(item, (str, int))
    ]
    brand = project.get("brand_name_user_facing") or project.get("name") or ""
    if is_placeholder("project.brand_name_user_facing", brand) or is_placeholder("project.name", brand):
        brand = ""
    palette = _as_dict(images.get("brand_palette"))
    ratios = _as_dict(images.get("aspect_ratios"))
    captions = _as_dict(images.get("captions"))
    inline_min = images.get("inline_min_per_post")
    return {
        "__LANGUAGE__": language,
        "__BRAND_NAME__": str(brand),
        "__AUDIENCES__": audiences,
        "__VOICE_SUMMARY__": summary,
        "__STYLE_ATTRIBUTES__": attributes,
        "__FORMALITY__": formality,
        "__ADDRESS__": "vy" if language == "ru" else "you",
        "__VISUAL_STYLE__": str(images.get("visual_style") or ""),
        "__PALETTE_PRIMARY__": str(palette.get("primary") or ""),
        "__PALETTE_SECONDARY__": str(palette.get("secondary") or ""),
        "__PALETTE_ACCENT__": str(palette.get("accent") or ""),
        "__PALETTE_AVOID__": _strings(palette.get("avoid")),
        "__HERO_RATIO__": str(ratios.get("hero") or ratios.get("featured") or "16:9"),
        "__INLINE_RATIO__": str(ratios.get("article_inline") or "16:9"),
        "__OG_RATIO__": str(ratios.get("og") or "1.91:1"),
        "__ICON_RATIO__": str(ratios.get("icon") or "1:1"),
        "__TEXT_ON_IMAGE__": images.get("allow_visible_text") is True,
        "__INLINE_CAPTION__": "required" if captions.get("inline_required") is True else "optional",
        "__INLINE_MIN__": inline_min if isinstance(inline_min, int) and not isinstance(inline_min, bool) and inline_min >= 0 else 2,
    }


def render_init(cfg: dict[str, Any]) -> str:
    text = template_text()
    for token, value in init_values(cfg).items():
        text = text.replace(token, _json(value))
    return text


def display_path(project_root: pathlib.Path, path: pathlib.Path) -> str:
    return rel_display(project_root, path)
