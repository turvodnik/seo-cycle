"""Движки поиска из конфига проекта, устойчиво к формату записи.

Канонический формат — список `{name, priority}`; исторические конфиги (схема v1.1)
пишут словарь-флаги `{google: true, yandex: false}`. Обе формы читаются одинаково,
чтобы решения «какой источник опрашивать» не зависели от возраста конфига.
"""
from __future__ import annotations

from typing import Any


def engine_names(cfg: dict[str, Any]) -> list[str]:
    raw = cfg.get("engines") or []
    if isinstance(raw, dict):
        return [str(name) for name, enabled in raw.items() if enabled]
    names: list[str] = []
    for item in raw:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
        elif isinstance(item, str):
            names.append(item)
    return names
