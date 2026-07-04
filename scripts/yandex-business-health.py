#!/usr/bin/env python3
"""Report Yandex Business (Справочник) readiness honestly — the API is partner-only.

Яндекс.Бизнес/Справочник не даёт публичного API для управления карточкой:
доступ партнёрский (агрегаторы). Честный статус — `partner_limited`. Рабочие
пути сегодня: браузерный workflow (prompts/local/yandex-maps.md через Chrome
MCP), ручные выгрузки отзывов, и Метрика/Вебмастер для трафик-сигналов.
То же относится к 2ГИС (партнёрский API справочника).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for
from seo_cycle_core.reports import write_report_bundle

ENV_NAMES = ["YANDEX_MERCHANT_BUSINESS_ID"]
OFFICIAL_DOCS = [
    "https://yandex.ru/support/business/",
    "https://yandex.ru/dev/sprav/",
    "https://dev.2gis.ru/",
]


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "setup"
    return {
        "markdown": base / "yandex-business-health.md",
        "json": base / "yandex-business-health.json",
        "latest_markdown": base / "latest-yandex-business-health.md",
        "latest_json": base / "latest-yandex-business-health.json",
    }


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
        "",
        "## Working paths",
    ]
    lines.extend(f"- {item}" for item in report["working_paths"])
    lines.extend(["", "## Guardrails"])
    lines.extend(f"- {item}" for item in report["guardrails"])
    lines.extend(["", "## Official Docs"])
    lines.extend(f"- {url}" for url in report["official_docs"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write seo/setup/yandex-business-health.* artifacts.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    report = build_report(cfg)
    if args.write:
        write_report_bundle(output_paths(project_root), render_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
