#!/usr/bin/env python3
"""Report Yandex Business (Справочник) readiness honestly — the API is partner-only.

Яндекс.Бизнес/Справочник не даёт публичного API для управления карточкой:
доступ партнёрский (агрегаторы). Честный статус — `partner_limited`. Рабочие
пути сегодня: браузерный workflow (prompts/local/yandex-maps.md через Chrome
MCP), ручные выгрузки отзывов, и Метрика/Вебмастер для трафик-сигналов.
То же относится к 2ГИС (партнёрский API справочника).
"""

from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any

from seo_cycle_core.health import HealthSpec, render_sections, run_health

ENV_NAMES = ["YANDEX_MERCHANT_BUSINESS_ID"]
OFFICIAL_DOCS = [
    "https://yandex.ru/support/business/",
    "https://yandex.ru/dev/sprav/",
    "https://dev.2gis.ru/",
]


def build_report(cfg: dict[str, Any]) -> dict[str, Any]:
    business = cfg.get("business_profile") if isinstance(cfg.get("business_profile"), dict) else {}
    return {
        "provider": "yandex_business",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": cfg.get("project", {}),
        "status": "partner_limited",
        "status_note": (
            "Публичного API управления карточкой Яндекс.Бизнес нет (Справочник — партнёрский). "
            "Это ожидаемое состояние, не ошибка конфигурации."
        ),
        "env_names": ENV_NAMES,
        "business_id_present": bool(os.environ.get("YANDEX_MERCHANT_BUSINESS_ID")),
        "profile_links": {
            "yandex_business": business.get("yandex_business_url") or business.get("yandex_maps_url") or "",
            "gbp": business.get("gbp_url") or "",
        },
        "working_paths": [
            "Браузерный workflow: prompts/local/yandex-maps.md (Chrome MCP) — карточка, рубрики, фото, посты, ответы на отзывы с human review.",
            "Отзывы: ручная выгрузка/копия из кабинета → анализ в review-velocity.py.",
            "Товары/цены на картах: фид Яндекс.Товаров — валидируй yml-feed-audit.py.",
            "Трафик-сигналы: metrika-fetch.py / metrika-logs-fetch.py (переходы с Карт видны как источник).",
            "2ГИС: партнёрский API — та же браузерная механика, отдельного скрипта нет намеренно.",
        ],
        "guardrails": [
            "Никаких live-вызовов в health check.",
            "Любые изменения карточки — только вручную/браузером с явным подтверждением человека.",
            "Не хранить пароли; браузерный профиль живёт вне репозитория проекта.",
        ],
        "official_docs": OFFICIAL_DOCS,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Yandex Business Health",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}` — {report['status_note']}",
        f"- Business ID env present: {report['business_id_present']} ({', '.join(report['env_names'])})",
        f"- Card links: {json.dumps(report['profile_links'], ensure_ascii=False)}",
    ]
    lines.extend(render_sections([
        ("Working paths", report["working_paths"]),
        ("Guardrails", report["guardrails"]),
        ("Official Docs", report["official_docs"]),
    ]))
    return "\n".join(lines) + "\n"


SPEC = HealthSpec(
    slug="yandex-business",
    style="simple",
    description=__doc__,
    write_help="Write seo/setup/yandex-business-health.* artifacts.",
    build_report=build_report,
    render_markdown=render_markdown,
)

if __name__ == "__main__":
    raise SystemExit(run_health(SPEC))
