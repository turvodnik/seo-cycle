"""Detect example values left over from `config/project.template.yaml` (3.1.0).

The wizard (`init-project.sh`) copies the template and rewrites only the
identity/locale fields it asks about. Everything else — the demo
`business_profile` (address, phone, logo), the demo `industry`, the demo
local signals «Москва / Мытищи» — survives into the project config and
quietly feeds real artifacts: `schema-org-build` injects the demo NAP into
JSON-LD, the draft gate would demand Moscow place names from a Kazan shop.

Placeholders are found by comparing a curated list of paths against the
template's own values (the literals are not duplicated here), plus the
wizard's non-interactive defaults. Lists count as placeholders when they
still share any element with the template list (a user who kept one demo
category out of three is still flagged). Empty template values are never
placeholders.
"""

from __future__ import annotations

import functools
import pathlib
from typing import Any

from .config import load_yaml, nested_get, skill_root

TEMPLATE_PATH = skill_root() / "config" / "project.template.yaml"

# (dotted path, question for the setup questionnaire)
PLACEHOLDER_FIELDS: tuple[tuple[str, str], ...] = (
    ("project.name", "Как называется проект (имя для людей)?"),
    ("project.domain", "Какой домен у сайта?"),
    ("project.brand_name_user_facing", "Как бренд пишется в текстах для читателя?"),
    ("project.brand_name_technical", "Техническое имя бренда (латиница, для slug/кода)?"),
    ("project.description", "Кто аудитория, что продаём, какая ниша (1–3 предложения)?"),
    ("industry.name", "Какая отрасль/ниша у проекта?"),
    ("industry.primary_categories", "Какие товарные группы/услуги главные?"),
    ("industry.homepage_h1", "Какой утверждённый H1 главной (или оставить пустым)?"),
    ("business_profile.legal_name", "Юридическое/публичное имя бизнеса для schema.org?"),
    ("business_profile.url", "Публичный URL сайта для schema.org?"),
    ("business_profile.logo", "URL логотипа?"),
    ("business_profile.telephone", "Реальный телефон бизнеса (или удалить поле)?"),
    ("business_profile.address.street", "Реальный адрес: улица и дом (или удалить address для онлайн-бизнеса)?"),
    ("business_profile.address.locality", "Реальный адрес: город?"),
    ("business_profile.address.region", "Реальный адрес: регион?"),
    ("business_profile.knows_about", "Экспертные темы бизнеса (E-E-A-T, knowsAbout)?"),
    ("content_rules.local_signals.examples", "Какие локальные сигналы (города/районы) упоминать в текстах?"),
    ("tone.description", "Как вы пишете — описание тона (или профиль голоса `seo-cycle voice init`)?"),
)

# Values the wizard writes when the operator just presses Enter.
WIZARD_DEFAULTS: dict[str, frozenset[str]] = {
    "project.name": frozenset({"MyProject"}),
    "project.domain": frozenset({"example.com"}),
    "project.brand_name_user_facing": frozenset({"MyProject"}),
    "project.brand_name_technical": frozenset({"example"}),
}

# Reserved documentation domains (RFC 2606) are never a real site.
EXAMPLE_DOMAINS = ("example.com", "example.org", "example.net")
_DOMAIN_PATHS = {"project.domain", "business_profile.url", "business_profile.logo"}


@functools.lru_cache(maxsize=4)
def _template(path: str) -> dict[str, Any]:
    return load_yaml(pathlib.Path(path))


def template_value(dotted: str, template_path: pathlib.Path | None = None) -> Any:
    return nested_get(_template(str(template_path or TEMPLATE_PATH)), dotted)


def _norm(value: Any) -> str:
    return " ".join(str(value).split()).casefold()


def is_placeholder(dotted: str, value: Any, template_path: pathlib.Path | None = None) -> bool:
    """True when `value` at `dotted` is still the template's (or wizard's) example."""
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        if text in WIZARD_DEFAULTS.get(dotted, frozenset()):
            return True
        if dotted in _DOMAIN_PATHS and any(domain in text.lower() for domain in EXAMPLE_DOMAINS):
            return True
    sample = template_value(dotted, template_path)
    if sample in (None, "", [], {}):
        return False
    if isinstance(value, list) and isinstance(sample, list):
        ours = {_norm(item) for item in value if not isinstance(item, (dict, list)) and str(item).strip()}
        theirs = {_norm(item) for item in sample if not isinstance(item, (dict, list)) and str(item).strip()}
        return bool(ours & theirs)
    if isinstance(value, (dict, list)) or isinstance(sample, (dict, list)):
        return False
    return _norm(value) == _norm(sample)


def find_placeholders(cfg: dict[str, Any], template_path: pathlib.Path | None = None) -> list[dict[str, Any]]:
    """Every curated path whose value is still an example from the template."""
    found: list[dict[str, Any]] = []
    if not isinstance(cfg, dict):
        return found
    for dotted, question in PLACEHOLDER_FIELDS:
        value = nested_get(cfg, dotted)
        if is_placeholder(dotted, value, template_path):
            found.append({"path": dotted, "value": value, "question": question})
    return found


def checked_paths(cfg: dict[str, Any]) -> list[str]:
    """Curated paths that are present in this config (the category's denominator)."""
    if not isinstance(cfg, dict):
        return []
    return [dotted for dotted, _question in PLACEHOLDER_FIELDS if nested_get(cfg, dotted) not in (None, "", [], {})]
