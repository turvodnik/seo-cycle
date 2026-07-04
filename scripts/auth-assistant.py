#!/usr/bin/env python3
"""Provider auth in one place: who is configured, from where, one-command login.

Two credential profiles (see seo_cycle_core/env_profile.py):
  project  — .env in the project root (a client's own accounts win here)
  global   — ~/.seo-cycle/env.global (log in once, works in every project)

Commands:
  python3 scripts/auth-assistant.py list [--format json]
      Status per provider: every env var with its current source
      (process / project / global / missing).

  python3 scripts/auth-assistant.py login <provider> [--global]
      Guided login. `gbp` runs the local OAuth dance (gbp-oauth-helper) and
      saves the refresh token straight into the chosen env file; every other
      provider prints the exact URL + hint and prompts for each variable
      (input hidden, Enter = skip). Nothing is ever printed back.

  python3 scripts/auth-assistant.py set VAR [--global] [--value V]
      Write one variable into the chosen env file (0600).
"""

from __future__ import annotations

import argparse
import getpass
import json
import pathlib
import subprocess
import sys
from typing import Any

from seo_cycle_core.config import find_config, project_root_for
from seo_cycle_core.env_profile import (
    env_chain,
    env_source,
    global_env_path,
    project_env_path,
    upsert_env_var,
)

PROVIDERS: dict[str, dict[str, Any]] = {
    "gbp": {
        "title": "Google Business Profile (OAuth)",
        "env": ["GBP_OAUTH_CLIENT_ID", "GBP_OAUTH_CLIENT_SECRET", "GBP_OAUTH_REFRESH_TOKEN"],
        "optional": ["GOOGLE_BUSINESS_ACCOUNT_ID", "GOOGLE_BUSINESS_LOCATION_ID"],
        "url": "https://console.cloud.google.com/apis/credentials",
        "hint": "OAuth client (Desktop/Web + http://localhost). Refresh token выдаёт login-flow ниже; runbook: docs/gbp-oauth-verification.md",
        "flow": "gbp-oauth",
    },
    "yandex": {
        "title": "Яндекс OAuth (Метрика, Вебмастер, Wordstat)",
        "env": ["YANDEX_OAUTH_TOKEN"],
        "optional": ["YANDEX_METRIKA_COUNTER_ID", "YANDEX_WEBMASTER_HOST_ID", "YANDEX_USER_ID"],
        "url": "https://oauth.yandex.ru/",
        "hint": "Создайте приложение с правами Метрики/Вебмастера → «Получить OAuth-токен вручную» → вставьте токен",
    },
    "yandex-direct": {
        "title": "Яндекс.Директ API",
        "env": ["YANDEX_DIRECT_TOKEN"],
        "optional": ["YANDEX_DIRECT_CLIENT_LOGIN"],
        "url": "https://oauth.yandex.ru/ (приложение с доступом к API Директа)",
        "hint": "Токен уровня рекламодателя/агентства; sandbox настраивается в кабинете API Директа",
    },
    "google-sa": {
        "title": "Google service account (GSC, GA4, NLP, Merchant)",
        "env": ["GOOGLE_APPLICATION_CREDENTIALS"],
        "optional": ["GSC_SITE_URL", "GA4_PROPERTY_ID", "GOOGLE_MERCHANT_ACCOUNT_ID"],
        "url": "https://console.cloud.google.com/iam-admin/serviceaccounts",
        "hint": "Значение — ПУТЬ к JSON-ключу сервис-аккаунта (не сам ключ); докиньте доступы в GSC/GA4",
    },
    "google-ads": {
        "title": "Google Ads API",
        "env": ["GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
                 "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_CUSTOMER_ID"],
        "optional": ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
        "url": "https://developers.google.com/google-ads/api/docs/first-call/overview",
        "hint": "Для region_profile: ru статус region_limited — это норма; основной канал Директ",
    },
    "perplexity": {
        "title": "Perplexity Sonar API",
        "env": ["PERPLEXITY_API_KEY"],
        "optional": [],
        "url": "https://www.perplexity.ai/settings/api",
        "hint": "Нужен только для API-режима (MCP-пресет perplexity); браузерный сбор работает без ключа",
    },
    "xmlriver": {
        "title": "XMLRiver (SERP/Wordstat)",
        "env": ["XMLRIVER_USER_ID", "XMLRIVER_API_KEY"],
        "optional": [],
        "url": "https://xmlriver.com/",
        "hint": "Кабинет → API: числовой user ID и ключ; платный — расход пишется в usage-ledger",
    },
    "keyso": {
        "title": "Keyso API",
        "env": ["KEYSO_API_TOKEN"],
        "optional": [],
        "url": "https://www.keyso.so/",
        "hint": "Тариф с API; токен в кабинете",
    },
    "serpstat": {
        "title": "Serpstat API",
        "env": ["SERPSTAT_API_KEY"],
        "optional": [],
        "url": "https://serpstat.com/users/profile/",
        "hint": "API-ключ в профиле",
    },
    "neuronwriter": {
        "title": "NeuronWriter",
        "env": ["NEURON_API_KEY"],
        "optional": ["NEURON_PROJECT_ID"],
        "url": "https://neuronwriter.com/",
        "hint": "API-ключ в настройках аккаунта; лимиты — nw-cli.sh limits",
    },
    "wordpress": {
        "title": "WordPress (REST publish + mirror)",
        "env": ["WP_API_URL", "WP_API_USERNAME", "WP_API_PASSWORD"],
        "optional": ["WP_BASE_URL"],
        "url": "wp-admin → Пользователи → Application Passwords",
        "hint": "Обычно per-project (у каждого клиента свой сайт) — запускайте без --global",
    },
    "tilda": {
        "title": "Tilda API",
        "env": ["TILDA_PUBLIC_KEY", "TILDA_SECRET_KEY", "TILDA_PROJECT_ID"],
        "optional": [],
        "url": "https://tilda.cc/ → Настройки сайта → Экспорт → API",
        "hint": "Ключи на сайт (бизнес-тариф); лимит 150 запросов/час учитывается автоматически",
    },
    "bitrix": {
        "title": "1С-Битрикс экспорт",
        "env": ["BITRIX_EXPORT_URL"],
        "optional": ["BITRIX_EXPORT_TOKEN"],
        "url": "свой экспорт-скрипт на стороне сайта (см. docs)",
        "hint": "URL JSON-экспорта инфоблоков; токен — если экспорт закрыт bearer'ом",
    },
    "telegram": {
        "title": "Telegram-уведомления",
        "env": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
        "optional": [],
        "url": "https://t.me/BotFather",
        "hint": "Токен бота + chat id (@userinfobot); обычно --global на всё агентство",
    },
    "bing": {
        "title": "Bing Webmaster",
        "env": ["BING_WEBMASTER_API_KEY"],
        "optional": ["BING_SITE_URL"],
        "url": "https://www.bing.com/webmasters/ → Settings → API access",
        "hint": "",
    },
    "indexnow": {
        "title": "IndexNow",
        "env": ["INDEXNOW_KEY"],
        "optional": ["INDEXNOW_KEY_LOCATION"],
        "url": "https://www.indexnow.org/",
        "hint": "Ключ — любая hex-строка, выложенная файлом на сайте",
    },
    "embeddings": {
        "title": "Embeddings для RAG (OpenAI-совместимый endpoint)",
        "env": ["EMBEDDING_API_URL", "EMBEDDING_API_KEY", "EMBEDDING_MODEL"],
        "optional": [],
        "url": "любой OpenAI-совместимый /v1/embeddings",
        "hint": "Опционально: без ключей RAG работает на FTS5/BM25",
    },
}


def resolve_project_root() -> pathlib.Path | None:
    cfg_path = find_config(pathlib.Path.cwd())
    return project_root_for(cfg_path) if cfg_path else None


def target_env_path(project_root: pathlib.Path | None, use_global: bool) -> pathlib.Path:
    if use_global or project_root is None:
        return global_env_path()
    return project_env_path(project_root)


def provider_status(project_root: pathlib.Path | None, spec: dict[str, Any]) -> dict[str, Any]:
    rows = []
    missing_required = 0
    for name in [*spec["env"], *spec.get("optional", [])]:
        source = env_source(project_root, name)
        required = name in spec["env"]
        if required and source is None:
            missing_required += 1
        rows.append({"var": name, "source": source, "required": required})
    state = "ready" if missing_required == 0 else "partial" if missing_required < len(spec["env"]) else "not_configured"
    return {"state": state, "vars": rows}


def cmd_list(args: argparse.Namespace, project_root: pathlib.Path | None) -> int:
    report = {}
    for alias, spec in PROVIDERS.items():
        status = provider_status(project_root, spec)
        report[alias] = {"title": spec["title"], **status}
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print("# Провайдеры: кто настроен и откуда\n")
    print(f"- project .env: {project_env_path(project_root) if project_root else '— (запустите из проекта)'}")
    print(f"- global env:  {global_env_path()}\n")
    icons = {"ready": "✅", "partial": "🟡", "not_configured": "▫️"}
    for alias, data in report.items():
        print(f"{icons[data['state']]} {alias:<14} {data['title']}")
        for row in data["vars"]:
            mark = {"process": "env", "project": "project", "global": "global", None: "—"}[row["source"]]
            req = "" if row["required"] else " (опц.)"
            print(f"    {'[' + mark + ']':<10} {row['var']}{req}")
    print("\nЛогин: python3 scripts/auth-assistant.py login <provider> [--global]")
    return 0


def prompt_and_write(name: str, target: pathlib.Path, *, required: bool) -> bool:
    suffix = "" if required else " (опционально)"
    try:
        value = getpass.getpass(f"  {name}{suffix} [Enter — пропустить]: ")
    except (EOFError, KeyboardInterrupt):
        print("", file=sys.stderr)
        return False
    if not value.strip():
        return False
    upsert_env_var(target, name, value.strip())
    print(f"  ✓ {name} → {target}", file=sys.stderr)
    return True


def cmd_login(args: argparse.Namespace, project_root: pathlib.Path | None) -> int:
    spec = PROVIDERS.get(args.provider)
    if not spec:
        print(f"ERROR: неизвестный провайдер `{args.provider}`. Список: {', '.join(sorted(PROVIDERS))}",
              file=sys.stderr)
        return 2
    target = target_env_path(project_root, args.use_global)
    scope = "global (все проекты)" if target == global_env_path() else f"project ({target})"
    print(f"# {spec['title']} → {scope}", file=sys.stderr)
    if spec.get("url"):
        print(f"Где взять: {spec['url']}", file=sys.stderr)
    if spec.get("hint"):
        print(f"Подсказка: {spec['hint']}", file=sys.stderr)

    if spec.get("flow") == "gbp-oauth":
        chain = env_chain(project_root)
        for name in ("GBP_OAUTH_CLIENT_ID", "GBP_OAUTH_CLIENT_SECRET"):
            if not chain.get(name):
                print(f"\nСначала нужен {name} (Cloud Console → Credentials):", file=sys.stderr)
                if not prompt_and_write(name, target, required=True):
                    print("ERROR: без client id/secret OAuth-flow невозможен.", file=sys.stderr)
                    return 2
        helper = pathlib.Path(__file__).resolve().parent / "gbp-oauth-helper.py"
        proc = subprocess.run(
            [sys.executable, str(helper), "--write-env", str(target)],
            cwd=project_root or pathlib.Path.cwd(),
            env=env_chain(project_root),
            check=False,
        )
        if proc.returncode == 0:
            for name in spec.get("optional", []):
                if not env_chain(project_root).get(name):
                    prompt_and_write(name, target, required=False)
            print("\n✓ GBP авторизован. Проверка: python3 scripts/gbp-health.py", file=sys.stderr)
        return proc.returncode

    print("", file=sys.stderr)
    written = 0
    for name in spec["env"]:
        if prompt_and_write(name, target, required=True):
            written += 1
    for name in spec.get("optional", []):
        if prompt_and_write(name, target, required=False):
            written += 1
    status = provider_status(project_root, spec)["state"]
    print(f"\nИтог: записано {written} перем., статус провайдера: {status}", file=sys.stderr)
    return 0 if status != "not_configured" else 1


def cmd_set(args: argparse.Namespace, project_root: pathlib.Path | None) -> int:
    target = target_env_path(project_root, args.use_global)
    value = args.value
    if value is None:
        try:
            value = getpass.getpass(f"{args.var} = ")
        except (EOFError, KeyboardInterrupt):
            print("", file=sys.stderr)
            return 1
    if not value.strip():
        print("ERROR: пустое значение не записываю.", file=sys.stderr)
        return 2
    upsert_env_var(target, args.var, value.strip())
    print(f"✓ {args.var} → {target} (0600)", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    lst = sub.add_parser("list", help="Provider status: every env var and its source")
    lst.add_argument("--format", choices=("md", "json"), default="md")

    login = sub.add_parser("login", help="Guided login for one provider")
    login.add_argument("provider", help=f"One of: {', '.join(sorted(PROVIDERS))}")
    login.add_argument("--global", dest="use_global", action="store_true",
                       help="Write to ~/.seo-cycle/env.global instead of the project .env")

    setter = sub.add_parser("set", help="Write one variable into an env profile")
    setter.add_argument("var", help="Variable name, e.g. PERPLEXITY_API_KEY")
    setter.add_argument("--value", help="Value (omit to be prompted with hidden input)")
    setter.add_argument("--global", dest="use_global", action="store_true")

    args = parser.parse_args(argv)
    project_root = resolve_project_root()
    if args.command == "list":
        return cmd_list(args, project_root)
    if args.command == "login":
        return cmd_login(args, project_root)
    return cmd_set(args, project_root)


if __name__ == "__main__":
    raise SystemExit(main())
