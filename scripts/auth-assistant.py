#!/usr/bin/env python3
"""Provider auth in one place: who is configured, from where, one-command login.

One canon for secret values (T-108, global policy §5): the macOS Keychain via
the `ai-secret` broker. This script never writes a value into a file.

  scope    — Keychain scope: the project's `project.brand_name_technical`
             from seo-cycle.yaml (e.g. `gsse`), `--global` for keys shared by
             every project, or an explicit `--scope NAME`.

Commands:
  python3 scripts/auth-assistant.py list [--format json]
      Status per provider: every env var with its current source —
      keychain:<scope> / keychain:global (names via `ai-secret list`, values
      never read) / process / legacy .env / legacy env.global / missing.

  python3 scripts/auth-assistant.py login <provider> [--global|--scope S]
      Guided login: prints the exact URL + hint, prompts for each variable
      with hidden input and hands it to `ai-secret set` over stdin. `gbp`
      first stores the OAuth client, then runs the local OAuth dance
      (gbp-oauth-helper) under `ai-secret run`. Nothing is ever printed back.

  python3 scripts/auth-assistant.py set VAR [--global|--scope S]
      Store one variable (hidden prompt; on a non-tty the value is read as
      one line from stdin — never from argv, which would land in `ps` and
      the dispatcher log).

Without `ai-secret` on PATH, `login`/`set` exit 3 with an explicit message —
no quiet fallback to `.env` (policy §5, invariant 7). `list` still works and
reports that secrets are not wired.
"""

from __future__ import annotations

import argparse
import getpass
import json
import pathlib
import subprocess
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for
from seo_cycle_core.env_profile import (
    AI_SECRET_MISSING,
    GLOBAL_SCOPE,
    SCOPE_RE,
    env_chain,
    env_source,
    find_ai_secret,
    global_env_path,
    keychain_names,
    project_env_path,
    secret_scope,
    store_secret,
)

RC_NO_AI_SECRET = 3

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
        "tier": "minimum",
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
        "tier": "minimum",
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
        "title": "WordPress REST (публикация + mirror, Application Password)",
        "env": ["WP_BASE_URL", "WP_USER", "WP_APP_PASSWORD"],
        "optional": [],
        "url": "wp-admin → Пользователи → профиль → Application Passwords",
        "hint": "Основной канал публикации (skills/seo-publishing). WP_BASE_URL — корень сайта без /wp-json; "
                "обычно per-project (у каждого клиента свой сайт) — запускайте без --global",
    },
    "wordpress-mcp": {
        "title": "WordPress MCP (Novomira, только если подключён --with-wordpress-mcp)",
        "env": ["WP_API_URL", "WP_API_USERNAME", "WP_API_PASSWORD"],
        "optional": [],
        "url": "wp-admin → Пользователи → Application Passwords (тот же пароль, что для REST, подойдёт)",
        "hint": "Отдельное семейство имён для MCP-сервера (project-mcp-config.py); публикации через REST не нужно",
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


def resolve_scope(project_root: pathlib.Path | None, use_global: bool, override: str | None) -> str | None:
    """Keychain scope for this invocation; None = cannot decide (caller reports)."""
    if override:
        return override if SCOPE_RE.match(override) else None
    if use_global or project_root is None:
        return GLOBAL_SCOPE
    cfg_path = find_config(project_root)
    return secret_scope(load_yaml(cfg_path)) if cfg_path else None


def scope_error(project_root: pathlib.Path | None, override: str | None) -> str:
    if override:
        return (f"ERROR: недопустимый scope `{override}` — строчные латинские буквы, цифры, `-`, `_`, `.` "
                "(до 64 символов).")
    return ("ERROR: scope Keychain не определён — заполни `project.brand_name_technical` в seo-cycle.yaml "
            f"({find_config(project_root) if project_root else 'конфиг не найден'}) "
            "или укажи явно: --scope <slug> / --global.")


class KeychainIndex:
    """Names registered in the Keychain for the project scope and `global` — read once per run."""

    def __init__(self, binary: str | None, scope: str | None) -> None:
        self.binary = binary
        self.scope = scope
        self.available = binary is not None
        self.error: str | None = None
        self._names: dict[str, set[str]] = {}
        if binary is None:
            return
        for sc in dict.fromkeys([s for s in (scope, GLOBAL_SCOPE) if s]):
            names = keychain_names(binary, sc)
            if names is None:
                self.error = f"ai-secret list {sc} не ответил (связка ключей заблокирована или scope неизвестен)"
                continue
            self._names[sc] = set(names)

    def source_of(self, name: str) -> str | None:
        if self.scope and name in self._names.get(self.scope, ()):
            return f"keychain:{self.scope}"
        if name in self._names.get(GLOBAL_SCOPE, ()):
            return "keychain:global"
        return None


def var_source(project_root: pathlib.Path | None, index: KeychainIndex, name: str) -> str | None:
    """process > keychain:<scope> > keychain:global > legacy project .env > legacy env.global."""
    legacy = env_source(project_root, name)
    if legacy == "process":
        return "process"
    keychain = index.source_of(name)
    if keychain:
        return keychain
    return legacy


def provider_status(project_root: pathlib.Path | None, spec: dict[str, Any], index: KeychainIndex) -> dict[str, Any]:
    rows = []
    missing_required = 0
    for name in [*spec["env"], *spec.get("optional", [])]:
        source = var_source(project_root, index, name)
        required = name in spec["env"]
        if required and source is None:
            missing_required += 1
        rows.append({"var": name, "source": source, "required": required})
    state = "ready" if missing_required == 0 else "partial" if missing_required < len(spec["env"]) else "not_configured"
    return {"state": state, "vars": rows}


def gbp_token_age_warning(project_root: pathlib.Path | None) -> str | None:
    """Testing-mode GBP refresh tokens die after 7 days — warn before they do."""
    minted = env_chain(project_root, base={}).get("GBP_TOKEN_MINTED_AT", "")
    if not minted:
        return None
    import datetime as dt

    try:
        age = (dt.date.today() - dt.date.fromisoformat(minted)).days
    except ValueError:
        return None
    if age >= 6:
        return (f"GBP refresh token выпущен {age} дн. назад — в Testing-режиме он умирает на 7-й день; "
                "пере-минтите: seo-cycle auth login gbp")
    return None


SOURCE_MARKS = {
    "process": "env",
    "project": ".env legacy",
    "global": "env.global legacy",
    None: "—",
}


def source_mark(source: str | None) -> str:
    if source and source.startswith("keychain:"):
        return source
    return SOURCE_MARKS[source]


def cmd_list(args: argparse.Namespace, project_root: pathlib.Path | None) -> int:
    binary = find_ai_secret()
    scope = resolve_scope(project_root, args.use_global, args.scope)
    index = KeychainIndex(binary, scope)
    report = {}
    for alias, spec in PROVIDERS.items():
        status = provider_status(project_root, spec, index)
        report[alias] = {"title": spec["title"], "tier": spec.get("tier", "extra"), **status}
    warning = gbp_token_age_warning(project_root)
    if warning:
        report["gbp"]["warning"] = warning
    if args.format == "json":
        # JSON shape = providers only (the dashboard iterates every key as a
        # provider row); the broker meta goes to stderr as one line.
        print(f"secrets: ai-secret={binary or 'not-found'} scope={scope or '?'}"
              + (f" warning={index.error}" if index.error else ""), file=sys.stderr)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print("# Провайдеры: кто настроен и откуда\n")
    print("Для ежедневного среза достаточно: Яндекс.Вебмастер **или** Google Search Console.\n")
    if binary:
        print(f"- Keychain (ai-secret): scope `{scope or '?'}` + `global` — {binary}")
        if index.error:
            print(f"  ⚠️  {index.error}")
    else:
        print(f"- Keychain: ⚠️  {AI_SECRET_MISSING}")
    print(f"- legacy project .env: {project_env_path(project_root) if project_root else '— (запустите из проекта)'}")
    print(f"- legacy global env:  {global_env_path()}")
    print("  (legacy-файлы только читаются; перенос: `ai-secret import <scope> .env` и удалить файл)\n")
    icons = {"ready": "✅", "partial": "🟡", "not_configured": "▫️"}
    tier_labels = {"minimum": "минимум для pulse", "extra": "дополнительно"}
    for alias, data in report.items():
        tier = tier_labels[PROVIDERS[alias].get("tier", "extra")]
        print(f"{icons[data['state']]} {alias:<14} {data['title']} — {tier}")
        if data.get("warning"):
            print(f"    ⚠️  {data['warning']}")
        for row in data["vars"]:
            mark = source_mark(row["source"])
            req = "" if row["required"] else " (опц.)"
            print(f"    {'[' + mark + ']':<22} {row['var']}{req}")
    print("\nЛогин: python3 scripts/auth-assistant.py login <provider> [--global|--scope S]")
    return 0


def read_hidden(prompt: str) -> str | None:
    """Hidden prompt on a tty; one line from stdin otherwise. None = aborted/empty."""
    try:
        if sys.stdin.isatty():
            value = getpass.getpass(prompt)
        else:
            value = sys.stdin.readline()
    except (EOFError, KeyboardInterrupt):
        print("", file=sys.stderr)
        return None
    value = value.strip()
    return value or None


def prompt_and_store(binary: str, scope: str, name: str, *, required: bool) -> bool:
    suffix = "" if required else " (опционально)"
    value = read_hidden(f"  {name}{suffix} [Enter — пропустить]: ")
    if value is None:
        return False
    rc, message = store_secret(binary, scope, name, value)
    if rc != 0:
        print(f"  ✗ {name}: ai-secret set rc={rc} {message}", file=sys.stderr)
        return False
    print(f"  ✓ {name} → Keychain scope `{scope}`", file=sys.stderr)
    return True


def require_broker(project_root: pathlib.Path | None, args: argparse.Namespace) -> tuple[str, str] | int:
    binary = find_ai_secret()
    if binary is None:
        print(f"ERROR: {AI_SECRET_MISSING}", file=sys.stderr)
        return RC_NO_AI_SECRET
    scope = resolve_scope(project_root, args.use_global, args.scope)
    if scope is None:
        print(scope_error(project_root, args.scope), file=sys.stderr)
        return 2
    return binary, scope


def cmd_login(args: argparse.Namespace, project_root: pathlib.Path | None) -> int:
    spec = PROVIDERS.get(args.provider)
    if not spec:
        print(f"ERROR: неизвестный провайдер `{args.provider}`. Список: {', '.join(sorted(PROVIDERS))}",
              file=sys.stderr)
        return 2
    broker = require_broker(project_root, args)
    if isinstance(broker, int):
        return broker
    binary, scope = broker
    where = "global (все проекты)" if scope == GLOBAL_SCOPE else f"project scope `{scope}`"
    print(f"# {spec['title']} → Keychain, {where}", file=sys.stderr)
    if spec.get("url"):
        print(f"Где взять: {spec['url']}", file=sys.stderr)
    if spec.get("hint"):
        print(f"Подсказка: {spec['hint']}", file=sys.stderr)

    if spec.get("flow") == "gbp-oauth":
        index = KeychainIndex(binary, scope)
        for name in ("GBP_OAUTH_CLIENT_ID", "GBP_OAUTH_CLIENT_SECRET"):
            if var_source(project_root, index, name) is None:
                print(f"\nСначала нужен {name} (Cloud Console → Credentials):", file=sys.stderr)
                if not prompt_and_store(binary, scope, name, required=True):
                    print("ERROR: без client id/secret OAuth-flow невозможен.", file=sys.stderr)
                    return 2
        helper = pathlib.Path(__file__).resolve().parent / "gbp-oauth-helper.py"
        minted_file = global_env_path() if scope == GLOBAL_SCOPE or project_root is None else project_env_path(project_root)
        # The helper needs the client id/secret in ITS environment and stores
        # the refresh token itself via `ai-secret set` — so it runs under
        # `ai-secret run <scope>`; this process never sees the values.
        proc = subprocess.run(
            [binary, "run", scope, "--", sys.executable, str(helper),
             "--store-scope", scope, "--minted-env", str(minted_file)],
            cwd=project_root or pathlib.Path.cwd(),
            check=False,
        )
        if proc.returncode == 0:
            index = KeychainIndex(binary, scope)
            for name in spec.get("optional", []):
                if var_source(project_root, index, name) is None:
                    prompt_and_store(binary, scope, name, required=False)
            print("\n✓ GBP авторизован. Проверка: ai-secret run "
                  f"{scope} -- python3 scripts/gbp-health.py", file=sys.stderr)
        return proc.returncode

    print("", file=sys.stderr)
    written = 0
    for name in spec["env"]:
        if prompt_and_store(binary, scope, name, required=True):
            written += 1
    for name in spec.get("optional", []):
        if prompt_and_store(binary, scope, name, required=False):
            written += 1
    status = provider_status(project_root, spec, KeychainIndex(binary, scope))["state"]
    print(f"\nИтог: записано {written} перем. в Keychain (scope `{scope}`), статус провайдера: {status}",
          file=sys.stderr)
    return 0 if status != "not_configured" else 1


def cmd_set(args: argparse.Namespace, project_root: pathlib.Path | None) -> int:
    broker = require_broker(project_root, args)
    if isinstance(broker, int):
        return broker
    binary, scope = broker
    value = read_hidden(f"{args.var} = ")
    if value is None:
        print("ERROR: пустое значение не записываю.", file=sys.stderr)
        return 2
    rc, message = store_secret(binary, scope, args.var, value)
    if rc != 0:
        print(f"ERROR: ai-secret set rc={rc} {message}", file=sys.stderr)
        return rc or 1
    print(f"✓ {args.var} → Keychain scope `{scope}` ({message or 'stored'})", file=sys.stderr)
    return 0


def add_scope_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--global", dest="use_global", action="store_true",
                        help="Keychain scope `global` (keys shared by every project) instead of the project scope")
    parser.add_argument("--scope", help="Explicit Keychain scope (default: project.brand_name_technical)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    lst = sub.add_parser("list", help="Provider status: every env var and its source")
    lst.add_argument("--format", choices=("md", "json"), default="md")
    add_scope_flags(lst)

    login = sub.add_parser("login", help="Guided login for one provider (values → Keychain via ai-secret)")
    login.add_argument("provider", help=f"One of: {', '.join(sorted(PROVIDERS))}")
    add_scope_flags(login)

    setter = sub.add_parser("set", help="Store one variable in the Keychain (hidden prompt / stdin line)")
    setter.add_argument("var", help="Variable name, e.g. PERPLEXITY_API_KEY")
    add_scope_flags(setter)

    args = parser.parse_args(argv)
    project_root = resolve_project_root()
    if args.command == "list":
        return cmd_list(args, project_root)
    if args.command == "login":
        return cmd_login(args, project_root)
    return cmd_set(args, project_root)


if __name__ == "__main__":
    raise SystemExit(main())
