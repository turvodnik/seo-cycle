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
    # T-067 (F-36 sibling, engines written as a scalar/mapping-that-isn't-a-dict
    # instead of a list — `engines: 7` used to reach the `for item in raw` loop
    # below and raise `TypeError: 'int' object is not iterable` in the one
    # command whose whole job is to diagnose exactly this kind of mistake).
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
        elif isinstance(item, str):
            names.append(item)
    return names
