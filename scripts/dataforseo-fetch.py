#!/usr/bin/env python3
"""
dataforseo-fetch.py — клиент DataForSEO API для headless-конвейеров seo-cycle.

Зачем отдельный скрипт, если есть MCP-сервер: MCP хорош в диалоге с агентом
(разведка, разовые вопросы), но требует живой сессии и грузит десятки схем
инструментов в контекст. Для повторяемых прогонов (cron, батчи, отчёты) дешевле
и предсказуемее прямой HTTP-вызов: тот же аккаунт, тот же ключ, кэш на диск и
честный учёт расходов по полю `cost` из ответа API.

Auth: Authorization: Basic <base64("login:password")>.
  DATAFORSEO_API_KEY_BASE64  — готовый base64 (основной путь, Keychain через
                               `ai-secret run global -- ...`);
  DATAFORSEO_LOGIN + DATAFORSEO_PASSWORD — альтернатива, base64 собирается сам.

Подкоманды (все — live, ответ сразу):
  balance                      остаток на счёте и лимиты (бесплатный вызов)
  serp        KEYWORD          органическая выдача Google (top-N, типы блоков)
  volume      KW [KW ...]      частотность Google Ads (объём, CPC, конкуренция)
  ideas       KEYWORD          идеи ключей (DataForSEO Labs)
  related     KEYWORD          связанные ключи (Labs)
  ranked      DOMAIN           ключи, по которым домен ранжируется (Labs)
  competitors DOMAIN           домены-конкуренты по органике (Labs)
  backlinks   DOMAIN           сводка по ссылочному профилю
  onpage      URL              мгновенный технический разбор страницы

Экономия и защита от неожиданных трат:
  • кэш на диск (--ttl дней, по умолчанию 30) — повтор той же выборки = 0 расходов;
  • месячный счётчик реальных трат `_usage.json` из поля `cost` ответов; битый/
    нечитаемый файл учёта — это отказ, а не «потрачено 0» (--force снимает осознанно);
  • стоп при исчерпании месячного лимита — минимум из --budget (по умолчанию 5 USD)
    и governance.subscriptions.dataforseo.monthly_usd_cap проекта, если конфиг
    найден; --force снимает стоп.

Примеры:
  ai-secret run global -- python3 dataforseo-fetch.py balance
  ai-secret run global -- python3 dataforseo-fetch.py volume "минеральная вата" --location 2840 --md
  ai-secret run global -- python3 dataforseo-fetch.py serp "kuchyne na miru" --location 2203 --language cs --md
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

from seo_cycle_core.config import find_config, load_yaml, nested_get
from seo_cycle_core.usage_ledger import (
    UsageLedgerError,
    budget_arg,
    effective_budget as _shared_effective_budget,
    finite_nonneg as _finite_nonneg,
    load_usage as _shared_load_usage,
    save_usage,
    usage_file as _shared_usage_file,
    usage_lock,
)

API_BASE = "https://api.dataforseo.com/v3"
DEFAULT_OUT = "seo/research/dataforseo"
DEFAULT_TTL_DAYS = 30
DEFAULT_BUDGET_USD = 5.0


# ---------- авторизация ----------

def load_auth(env: dict | None = None) -> str:
    """base64 для заголовка Basic. Значение нигде не печатается."""
    env = dict(os.environ if env is None else env)
    for rel in (".env", "seo/.env"):
        p = pathlib.Path.cwd() / rel
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    b64 = (env.get("DATAFORSEO_API_KEY_BASE64") or "").strip()
    if b64:
        return b64
    login, password = env.get("DATAFORSEO_LOGIN"), env.get("DATAFORSEO_PASSWORD")
    if login and password:
        return base64.b64encode(f"{login}:{password}".encode()).decode()
    sys.exit("ERROR: нет ключа DataForSEO. Запусти через "
             "`ai-secret run global -- python3 dataforseo-fetch.py ...` "
             "(ключ DATAFORSEO_API_KEY_BASE64 лежит в Keychain).")


# ---------- учёт расходов (общий модуль seo_cycle_core.usage_ledger, T-066) ----------
#
# Класс «денежный стоп» третий раз оказался шире, чем чинился поштучно (T-046,
# T-059, независимый прогон 2026-09-06 F-11/F-12/F-13). Примитивы (проверка
# значения, атомарная запись, блокировка, валидатор --budget) теперь живут в
# seo_cycle_core/usage_ledger.py одной копией на всех платных клиентов; здесь —
# только тонкие обёртки под интерфейс, которого ждут существующие вызовы/тесты.

USAGE_FIELDS = ("spent_usd", "calls")


def usage_file(out_dir: pathlib.Path) -> pathlib.Path:
    return _shared_usage_file(out_dir)


def load_usage(out_dir: pathlib.Path) -> dict:
    """Месячный учёт трат. Нечитаемый/повреждённый файл (включая NaN/Infinity/
    отрицательный spent_usd, нечисловой calls, испорченный month) поднимает
    UsageLedgerError, а не тихо возвращает «потрачено 0» — вызывающая сторона
    (fetch()) решает, что делать: по умолчанию отказ, --force осознанно считает
    месяц заново."""
    return _shared_load_usage(out_dir, USAGE_FIELDS)


def effective_budget(args) -> float:
    """--budget, ограниченный сверху governance.subscriptions.dataforseo.monthly_usd_cap
    проекта, если конфиг найден и поле задано пригодным для арифметики числом
    (T-059). Конфиг без секции/файла — поведение как раньше (только --budget).
    Битый YAML — честный отказ (sys.exit), а не молчаливый откат на --budget:
    иначе опечатка в конфиге тихо снимает лимит, который человек специально
    понижал (ревью T-059, красный №1/№2 — «тип прошёл проверку, значение
    непригодно для денег»)."""
    cfg_path = find_config(pathlib.Path.cwd())
    if cfg_path is None:
        return args.budget
    try:
        cfg = load_yaml(cfg_path)
    except Exception as e:
        sys.exit(f"ERROR: {cfg_path} не парсится как YAML ({e}). Почини конфиг или "
                 f"убери секцию governance.subscriptions.dataforseo, чтобы работать "
                 f"только по --budget.")
    cap = nested_get(cfg, "governance.subscriptions.dataforseo.monthly_usd_cap")
    try:
        return _shared_effective_budget(args.budget, cap, cap_label=(
            f"governance.subscriptions.dataforseo.monthly_usd_cap в {cfg_path}"))
    except ValueError as e:
        sys.exit(f"ERROR: {e}. Почини значение или убери ключ, чтобы работать "
                 f"только по --budget.")


# ---------- транспорт ----------

def call(b64: str, path: str, payload: dict | None) -> dict:
    """POST (live-методы) либо GET (без payload). Ошибки API, сети и битого JSON
    поднимаются как управляемый sys.exit с понятным сообщением, а не голый
    traceback (T-059)."""
    data = None
    if payload is not None:
        data = json.dumps([payload]).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/{path}",
        data=data,
        headers={"Authorization": f"Basic {b64}", "Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        sys.exit(f"ERROR DataForSEO HTTP {e.code}: {body}")
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit(f"ERROR DataForSEO: сеть недоступна ({e}).")
    try:
        return json.loads(raw)
    except ValueError as e:
        sys.exit(f"ERROR DataForSEO: битый ответ, не JSON ({e}).")


def response_cost(resp: dict) -> float:
    """Реальная стоимость вызова из ответа API (в USD). Отсутствие поля — 0
    (бесплатные методы вроде balance его не возвращают). Присутствие с
    непригодным для арифметики значением (не число, NaN, Infinity, отрицательное)
    — sys.exit, а не тихий 0: заниженный/испорченный учёт из ответа API — тот же
    риск, что «потрачено 0» при битом файле учёта (T-059, второй круг после
    гейта — response_cost() не был затронут первым проходом)."""
    raw = resp.get("cost")
    if raw is None:
        return 0.0
    try:
        cost = float(raw)
    except (TypeError, ValueError):
        sys.exit(f"ERROR DataForSEO: поле cost в ответе непригодно для денежной "
                 f"арифметики ({raw!r}).")
    if not _finite_nonneg(cost):
        sys.exit(f"ERROR DataForSEO: поле cost в ответе непригодно для денежной "
                 f"арифметики ({raw!r}).")
    return cost


def first_result(resp: dict) -> list:
    tasks = resp.get("tasks") or []
    if not tasks:
        return []
    t = tasks[0]
    if t.get("status_code") not in (20000, None):
        sys.exit(f"ERROR DataForSEO: {t.get('status_code')} {t.get('status_message')}")
    return t.get("result") or []


def _task_status_ok(resp: dict) -> bool:
    """Task-level статус (в отличие от общего resp["status_code"], который fetch()
    уже проверил выше) — нужен только для решения «кэшировать ответ или нет»
    (T-059). Сам exit на ошибке задачи по-прежнему делает first_result()."""
    tasks = resp.get("tasks") or []
    if not tasks:
        return True
    return tasks[0].get("status_code") in (20000, None)


# ---------- кэш ----------

def cache_path(out_dir: pathlib.Path, path: str, payload: dict | None) -> pathlib.Path:
    key = hashlib.md5((path + json.dumps(payload or {}, sort_keys=True)).encode()).hexdigest()[:12]
    return out_dir / f"dfs-{path.strip('/').replace('/', '-')}-{key}.json"


def fetch(b64: str, path: str, payload: dict | None, args) -> dict:
    """Кэш → бюджет-гард → вызов → учёт расхода. Возвращает распарсенный ответ.
    Проверка бюджета, платный вызов и запись расхода идут под одной файловой
    блокировкой (usage_lock, T-059) — иначе параллельные fetch теряют чужой
    расход. Ответ с task-level ошибкой в кэш не пишется."""
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cpath = cache_path(out_dir, path, payload)

    if cpath.exists() and (time.time() - cpath.stat().st_mtime) / 86400.0 <= args.ttl:
        print(f"↩ кэш (<{args.ttl}д): {cpath} — без расходов", file=sys.stderr)
        return json.loads(cpath.read_text(encoding="utf-8"))

    with usage_lock(out_dir):
        try:
            u = load_usage(out_dir)
        except UsageLedgerError as e:
            if not args.force:
                sys.exit(f"ERROR: файл учёта трат повреждён ({e}). Это отказ, а не "
                         f"«потрачено 0» — иначе бюджетный стоп пропустит платный "
                         f"вызов вслепую. Почини или удали {usage_file(out_dir)}, "
                         f"либо --force, чтобы посчитать месяц заново (старый файл "
                         f"будет переписан).")
            print(f"⚠ файл учёта трат повреждён, --force: считаю месяц с нуля ({e})",
                  file=sys.stderr)
            u = {"month": datetime.date.today().strftime("%Y-%m"), "spent_usd": 0.0, "calls": 0}

        budget = effective_budget(args)
        if u["spent_usd"] >= budget and not args.force:
            sys.exit(f"ERROR: месячный лимит DataForSEO исчерпан "
                     f"(${u['spent_usd']:.4f}/${budget}, месяц {u['month']}). "
                     f"--force чтобы продолжить или подними --budget.")

        # F-13 (независимый прогон 2026-09-06): деньги списываются самим фактом
        # платного вызова, а не фактом «ответ хороший». Раньше и плохой
        # status_code, и непригодное поле cost (response_cost) уходили в
        # sys.exit ДО save_usage() — вызов был реальный, платный, а учёт про
        # него не знал ничего. Поэтому: вызов сначала, запись под тем же
        # usage_lock — ВСЕГДА, любой из выходов ниже происходит только после неё.
        resp = call(b64, path, payload)
        u["calls"] = u.get("calls", 0) + 1
        try:
            cost = response_cost(resp)
        except SystemExit as e:
            cost = None
            cost_error = str(e.code)
        else:
            cost_error = None
        if cost is not None:
            u["spent_usd"] = round(u.get("spent_usd", 0.0) + cost, 6)
        else:
            # Сумма неизвестна — списать нечего, но сам факт платного вызова
            # обязан остаться в учёте (F-13): непригодность отражена отдельным
            # счётчиком, а не потерей вызова из истории.
            u["cost_unknown_calls"] = u.get("cost_unknown_calls", 0) + 1
        save_usage(out_dir, u)

        if resp.get("status_code") not in (20000, None):
            print(f"↑ запрос {path}: вызов #{u['calls']} зафиксирован в учёте, "
                  f"ответ вернул ошибку конверта", file=sys.stderr)
            sys.exit(f"ERROR DataForSEO: {resp.get('status_code')} {resp.get('status_message')}")
        if cost_error is not None:
            print(f"↑ запрос {path}: вызов #{u['calls']} зафиксирован в учёте "
                  f"без суммы (cost непригоден)", file=sys.stderr)
            sys.exit(f"ERROR DataForSEO: {cost_error} Расход по вызову #{u['calls']} "
                     f"учтён без суммы — сверь {usage_file(out_dir)} вручную.")

        print(f"↑ запрос {path}: ${cost:.4f} · за месяц ${u['spent_usd']:.4f} "
              f"({u['calls']} вызовов)", file=sys.stderr)

        task_ok = _task_status_ok(resp)

    if task_ok:
        cpath.write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        msg = (resp.get("tasks") or [{}])[0].get("status_message")
        print(f"⚠ задача вернула ошибку ({msg}) — ответ не кэшируется", file=sys.stderr)
    return resp


# ---------- вывод ----------

def md_table(headers: list, rows: list) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in r) + " |")
    return "\n".join(out)


def show(rows: list, headers: list, args) -> None:
    if args.md:
        print(md_table(headers, rows))
    else:
        print(json.dumps([dict(zip(headers, r, strict=True)) for r in rows], ensure_ascii=False, indent=2))


# ---------- подкоманды ----------

def cmd_balance(b64, args):
    resp = call(b64, "appendix/user_data", None)
    res = (first_result(resp) or [{}])[0]
    money = res.get("money") or {}
    print(json.dumps({"balance_usd": money.get("balance"),
                      "total_spent_usd": money.get("total"),
                      "rates_minute_total": ((res.get("rates") or {}).get("limits") or {}).get("total")},
                     ensure_ascii=False, indent=2))


def cmd_serp(b64, args):
    payload = {"keyword": args.keyword, "location_code": args.location,
               "language_code": args.language, "depth": args.depth}
    resp = fetch(b64, "serp/google/organic/live/advanced", payload, args)
    items = ((first_result(resp) or [{}])[0].get("items") or [])
    rows = [(i.get("rank_absolute"), i.get("type"), i.get("domain"),
             (i.get("title") or "")[:70]) for i in items if i.get("type") == "organic"]
    show(rows[:args.depth], ["#", "тип", "домен", "заголовок"], args)


def cmd_volume(b64, args):
    payload = {"keywords": args.keywords, "location_code": args.location,
               "language_code": args.language}
    resp = fetch(b64, "keywords_data/google_ads/search_volume/live", payload, args)
    res = first_result(resp)
    rows = [(r.get("keyword"), r.get("search_volume"), r.get("competition"),
             r.get("cpc")) for r in res]
    rows.sort(key=lambda r: (r[1] is None, -(r[1] or 0)))
    show(rows, ["ключ", "частотность", "конкуренция", "CPC"], args)


def _labs_keywords(b64, args, path, key_field="keyword", *, seed_as_list=False):
    """seed_as_list=True шлёт seed-ключ как `keywords: [...]` — так требует
    контракт dataforseo_labs/google/keyword_ideas/live (T-059); related_keywords
    ждёт одиночный `keyword`, поведение по умолчанию не меняется."""
    seed_key = "keywords" if seed_as_list else "keyword"
    seed_val = [args.keyword] if seed_as_list else args.keyword
    payload = {seed_key: seed_val, "location_code": args.location,
               "language_code": args.language, "limit": args.limit}
    resp = fetch(b64, path, payload, args)
    items = ((first_result(resp) or [{}])[0].get("items") or [])
    rows = []
    for i in items:
        kd = i.get("keyword_data") or i
        info = (kd.get("keyword_info") or {})
        rows.append((kd.get(key_field), info.get("search_volume"), info.get("cpc"),
                     info.get("competition_level")))
    show(rows, ["ключ", "частотность", "CPC", "конкуренция"], args)


def cmd_ideas(b64, args):
    _labs_keywords(b64, args, "dataforseo_labs/google/keyword_ideas/live", seed_as_list=True)


def cmd_related(b64, args):
    _labs_keywords(b64, args, "dataforseo_labs/google/related_keywords/live")


def cmd_ranked(b64, args):
    payload = {"target": args.domain, "location_code": args.location,
               "language_code": args.language, "limit": args.limit}
    resp = fetch(b64, "dataforseo_labs/google/ranked_keywords/live", payload, args)
    items = ((first_result(resp) or [{}])[0].get("items") or [])
    rows = []
    for i in items:
        kd = i.get("keyword_data") or {}
        serp = ((i.get("ranked_serp_element") or {}).get("serp_item") or {})
        rows.append((kd.get("keyword"), serp.get("rank_absolute"),
                     (kd.get("keyword_info") or {}).get("search_volume"),
                     (serp.get("url") or "")[:70]))
    rows.sort(key=lambda r: (r[1] is None, r[1] or 0))
    show(rows, ["ключ", "позиция", "частотность", "URL"], args)


def cmd_competitors(b64, args):
    payload = {"target": args.domain, "location_code": args.location,
               "language_code": args.language, "limit": args.limit}
    resp = fetch(b64, "dataforseo_labs/google/competitors_domain/live", payload, args)
    items = ((first_result(resp) or [{}])[0].get("items") or [])
    rows = []
    for i in items:
        m = ((i.get("metrics") or {}).get("organic") or {})
        rows.append((i.get("domain"), i.get("avg_position"), m.get("count"), m.get("etv")))
    show(rows, ["домен", "средняя позиция", "ключей", "трафик (ETV)"], args)


def cmd_backlinks(b64, args):
    payload = {"target": args.domain, "internal_list_limit": 10}
    resp = fetch(b64, "backlinks/summary/live", payload, args)
    r = (first_result(resp) or [{}])[0]
    rows = [(r.get("target"), r.get("rank"), r.get("backlinks"), r.get("referring_domains"),
             r.get("broken_backlinks"))]
    show(rows, ["цель", "rank", "ссылок", "доменов-доноров", "битых"], args)


def cmd_onpage(b64, args):
    payload = {"url": args.url, "enable_javascript": False}
    resp = fetch(b64, "on_page/instant_pages", payload, args)
    items = ((first_result(resp) or [{}])[0].get("items") or [])
    rows = []
    for i in items:
        meta = i.get("meta") or {}
        rows.append((i.get("url"), i.get("status_code"), (meta.get("title") or "")[:60],
                     meta.get("internal_links_count"), (i.get("onpage_score"))))
    show(rows, ["URL", "код", "title", "внутр. ссылок", "onpage score"], args)


# ---------- CLI ----------

def add_common(p: argparse.ArgumentParser, sub: bool) -> None:
    """Общие опции. У подкоманд default=SUPPRESS, иначе они затирают значения,
    заданные до подкоманды (`--md volume X` и `volume X --md` работают одинаково)."""
    d = (lambda v: argparse.SUPPRESS) if sub else (lambda v: v)
    p.add_argument("--out", default=d(DEFAULT_OUT), help=f"папка кэша и учёта (умолч. {DEFAULT_OUT})")
    p.add_argument("--ttl", type=float, default=d(DEFAULT_TTL_DAYS), help="возраст кэша в днях")
    p.add_argument("--budget", type=budget_arg, default=d(DEFAULT_BUDGET_USD),
                   help="месячный лимит трат, USD (итог — минимум с "
                        "governance.subscriptions.dataforseo.monthly_usd_cap проекта, если задан)")
    p.add_argument("--force", action="store_true", default=d(False),
                   help="игнорировать исчерпанный лимит")
    p.add_argument("--md", action="store_true", default=d(False),
                   help="markdown-таблица вместо JSON")
    p.add_argument("--location", type=int, default=d(2840), help="location_code (2840 = США)")
    p.add_argument("--language", default=d("en"), help="language_code (ru, cs, en ...)")
    p.add_argument("--limit", type=int, default=d(50), help="строк в ответе Labs-методов")
    p.add_argument("--depth", type=int, default=d(20), help="глубина выдачи для serp")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Клиент DataForSEO API для seo-cycle")
    add_common(p, sub=False)
    common = argparse.ArgumentParser(add_help=False)
    add_common(common, sub=True)

    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("balance", parents=[common])
    for name in ("serp", "ideas", "related"):
        sp = sub.add_parser(name, parents=[common])
        sp.add_argument("keyword")
    sp = sub.add_parser("volume", parents=[common])
    sp.add_argument("keywords", nargs="+")
    for name in ("ranked", "competitors", "backlinks"):
        sp = sub.add_parser(name, parents=[common])
        sp.add_argument("domain")
    sp = sub.add_parser("onpage", parents=[common])
    sp.add_argument("url")
    return p


HANDLERS = {
    "balance": cmd_balance, "serp": cmd_serp, "volume": cmd_volume,
    "ideas": cmd_ideas, "related": cmd_related, "ranked": cmd_ranked,
    "competitors": cmd_competitors, "backlinks": cmd_backlinks, "onpage": cmd_onpage,
}


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    HANDLERS[args.cmd](load_auth(), args)


if __name__ == "__main__":
    main()
