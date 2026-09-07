#!/usr/bin/env python3
"""
spyfu-fetch.py — клиент SpyFu API для competitor/PPC/SEO-аналитики.

⚠ ОБЛАСТЬ ПРИМЕНЕНИЯ: SpyFu покрывает Google US/UK и ряд западных стран
(countryCode: US, GB, CA, DE, FR, AU, ...). **РФ/Яндекс НЕ покрывает** (RU
отвергается API). Поэтому источник включён в профили us/eu/global, НЕ ru.
Для РФ-проектов полезен только для анализа международных конкурентов.

💳 БИЛЛИНГ: pay-as-you-go по строкам. Pro = $40 кредита/мес. CPM по эндпоинту:
  domain-stats $0.50 · competitors/keyword-info $0.20 · ad-history/ppc $2-3 ·
  top-pages $5.00 (формула: rows/1000 * CPM). Клиент ведёт локальный
  usage-трекер (seo/research/spyfu/_usage.json) с месячным сбросом и блокирует
  при достижении --budget (default $40) либо governance.subscriptions.spyfu.
  monthly_usd_cap проекта, если конфиг найден, кроме --force. SpyFu не отдаёт
  остаток через API — точную сверку смотри на spyfu.com/account/api.
  Учёт (валидация значений, атомарная запись, блокировка, --budget) — общий
  модуль scripts/seo_cycle_core/usage_ledger.py, тот же, что у dataforseo-fetch.py
  (T-066: независимый прогон нашёл в этом файле точную копию денежного стопа
  без единого из фиксов T-046/T-059).

Auth: Basic base64(API_SpyFu_ID:API_SpyFu_secret_key) — собирается из .env,
либо берётся готовый *_SpyFu_base-64_key.

Подкоманды:
  usage                              — показать локальный трекер расходов
  domain-stats DOMAIN [--all] [--cc US]
                                     — latest (1 строка, дёшево) или вся история (--all)
  raw PATH [--param k=v ...] [--cpm N]
                                     — произвольный эндпоинт SpyFu API v2

Опции: --cc US | --budget 40 | --ttl 30 | --force | --out ./seo/research/spyfu

Пример:
  python3 spyfu-fetch.py domain-stats competitor.com --cc US
  python3 spyfu-fetch.py usage
"""

from __future__ import annotations
import argparse, base64, hashlib, json, os, pathlib, sys, time, urllib.error, urllib.parse, urllib.request

from seo_cycle_core.config import find_config, load_yaml, nested_get
from seo_cycle_core.usage_ledger import (
    ApiCallError,
    UsageLedgerError,
    budget_arg,
    current_month,
    effective_budget as _shared_effective_budget,
    load_usage as _shared_load_usage,
    nonneg_finite_arg,
    save_usage,
    usage_file as _shared_usage_file,
    usage_lock,
)

# R-3/R-4 (гейт круга 2): `--cpm` голым `type=float` пишет «не число» в
# _usage.json через cost=rows/1000*cpm (F-13-класс наоборот — модуль,
# созданный чтобы прекратить порчу файла, сам его травит); `--ttl` — тот же
# «вечный промах кэша», что F-11 называл прямо.
cpm_arg = nonneg_finite_arg("--cpm")
ttl_arg = nonneg_finite_arg("--ttl")

API_BASE = "https://api.spyfu.com/apis"
# R4-1 (независимый гейт, круг 4→5): этот список больше не решает, какие
# поля защищены — `usage_ledger.load_usage()` проверяет каждое числовое
# поле файла по типу значения, а не по имени. Список только заполняет нули
# для пустого файла (см. dataforseo-fetch.py для полного объяснения).
USAGE_FIELDS = ("spent_usd", "rows")
RATE_DELAY = 0.5

ENDPOINTS = {
    "domain-stats-latest": ("domain_stats_api/v2/getLatestDomainStats", 0.50),
    "domain-stats-all":    ("domain_stats_api/v2/getAllDomainStats", 0.50),
}


def load_auth() -> str:
    """Вернёт base64 для Authorization: Basic. Собирает из ID:secret, либо готовый ключ."""
    env = dict(os.environ)
    for rel in (".env", "seo/.env"):
        p = pathlib.Path.cwd() / rel
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    app_id = env.get("API_SpyFu_ID")
    secret = env.get("API_SpyFu_secret_key")
    if app_id and secret:
        return base64.b64encode(f"{app_id}:{secret}".encode()).decode()
    # fallback: готовый base64 (имя может варьироваться из-за опечатки)
    for k, v in env.items():
        if "spyfu" in k.lower() and "base-64" in k.lower():
            return v
    sys.exit("ERROR: нет SpyFu ключей в .env (API_SpyFu_ID + API_SpyFu_secret_key)")


# ---- usage-трекер ($-бюджет, месячный сброс) ----
#
# T-066: этот блок был точной копией денежного стопа dataforseo-fetch.py без
# единого из фиксов T-046/T-059 (F-12, независимый прогон 2026-09-06) — голое
# чтение без проверки значения, сравнение и сложение, которые NaN/Infinity/
# отрицательное значение делают бессмысленными или необратимо портящими файл,
# запись без atomic replace, без блокировки. Теперь — общий модуль.

def usage_file(out_dir: pathlib.Path) -> pathlib.Path:
    return _shared_usage_file(out_dir)


def load_usage(out_dir: pathlib.Path) -> dict:
    """Месячный учёт трат. Нечитаемый/повреждённый файл, ЛЮБОЕ числовое
    поле (не только spent_usd/rows — по типу значения, R4-1) с
    NaN/Infinity/отрицательным значением, испорченный month — поднимает
    UsageLedgerError вместо тихого «потрачено 0» (F-12)."""
    return _shared_load_usage(out_dir, USAGE_FIELDS)


def effective_budget(args) -> float:
    """--budget, ограниченный сверху governance.subscriptions.spyfu.monthly_usd_cap
    проекта, если конфиг найден (F-12: раньше этот путь у SpyFu не читался
    вообще — только dataforseo-fetch.py уважал лимит из конфига)."""
    cfg_path = find_config(pathlib.Path.cwd())
    if cfg_path is None:
        return args.budget
    try:
        cfg = load_yaml(cfg_path)
    except Exception as e:
        sys.exit(f"ERROR: {cfg_path} не парсится как YAML ({e}). Почини конфиг или "
                 f"убери секцию governance.subscriptions.spyfu, чтобы работать "
                 f"только по --budget.")
    cap = nested_get(cfg, "governance.subscriptions.spyfu.monthly_usd_cap")
    try:
        return _shared_effective_budget(args.budget, cap, cap_label=(
            f"governance.subscriptions.spyfu.monthly_usd_cap в {cfg_path}"))
    except ValueError as e:
        sys.exit(f"ERROR: {e}. Почини значение или убери ключ, чтобы работать "
                 f"только по --budget.")


def call(b64: str, path: str, params: dict) -> dict:
    """Любая ошибка после отправки запроса (HTTP, сеть, битый JSON) поднимает
    ApiCallError вместо голого traceback/sys.exit — run() решает, что писать
    в учёт, ДО того как решит, выходить ли (F-13, круг 2 независимого гейта:
    раньше эти исключения улетали из-под usage_lock необработанными, и запись
    расхода не происходила вовсе)."""
    time.sleep(RATE_DELAY)
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(f"{API_BASE}/{path}?{qs}",
                                 headers={"Authorization": f"Basic {b64}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise ApiCallError(f"HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise ApiCallError(f"сеть недоступна ({e})") from e
    except ApiCallError:
        raise
    except Exception as e:
        # R2-2 (независимый гейт, круг 3): перечень типов (URLError/TimeoutError)
        # не покрывает обрыв тела уже отправленного запроса (IncompleteRead,
        # ConnectionResetError, ssl.SSLError, MemoryError...). Инверсия: любое
        # исключение после отправки запроса становится ApiCallError.
        raise ApiCallError(f"ошибка после отправки запроса ({type(e).__name__}: {e})") from e
    try:
        return json.loads(raw)
    except ValueError as e:
        raise ApiCallError(f"битый ответ, не JSON ({e})") from e


def cache_path(out_dir, path, params):
    key = hashlib.md5((path + json.dumps(params, sort_keys=True)).encode()).hexdigest()[:12]
    return out_dir / f"spyfu-{path.split('/')[-1]}-{key}.json"


def run(b64, path, cpm, params, args, distill):
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cpath = cache_path(out_dir, path, params)

    if cpath.exists() and (time.time() - cpath.stat().st_mtime) / 86400.0 <= args.ttl:
        print(f"↩ cache hit (<{args.ttl}д): {cpath} — без расходов", file=sys.stderr)
        distill(json.loads(cpath.read_text(encoding="utf-8")))
        return

    # F-12: проверка бюджета, платный вызов и запись расхода — под одной
    # файловой блокировкой (usage_lock), иначе параллельные run() читают один
    # и тот же старый _usage.json и последняя запись побеждает, теряя чужой
    # расход (та же дыра, что T-059 закрыл в dataforseo-fetch.py).
    with usage_lock(out_dir):
        try:
            u = load_usage(out_dir)
        except UsageLedgerError as e:
            if not args.force:
                sys.exit(f"ERROR: файл учёта трат SpyFu повреждён ({e}). Это отказ, "
                         f"а не «потрачено 0» — иначе бюджетный стоп пропустит "
                         f"платный вызов вслепую. Почини или удали {usage_file(out_dir)}, "
                         f"либо --force, чтобы посчитать месяц заново.")
            print(f"⚠ файл учёта трат SpyFu повреждён, --force: считаю месяц с нуля ({e})",
                  file=sys.stderr)
            u = {"month": current_month(), "spent_usd": 0.0, "rows": 0}

        budget = effective_budget(args)
        if u["spent_usd"] >= budget and not args.force:
            sys.exit(f"ERROR: месячный бюджет SpyFu исчерпан "
                     f"(${u['spent_usd']:.2f}/${budget}, месяц {u['month']}). --force чтобы продолжить.")
        # R3-1 (независимый гейт, круг 4), по аналогии с R2-3 в
        # dataforseo-fetch.py: вызов, чья сумма осталась неизвестна (обрыв
        # ДО получения ответа — Ctrl-C, SIGTERM, SIGKILL), обязан блокировать
        # ДАЛЬНЕЙШИЕ платные вызовы, пока человек не разберётся — иначе
        # write-ahead ниже просто пишет мусор, который никто не читает.
        if u.get("cost_unknown_calls", 0) > 0 and not args.force:
            sys.exit(f"ERROR: {u['cost_unknown_calls']} вызов(ов) SpyFu в этом "
                     f"месяце учтены БЕЗ суммы (запрос прервался до ответа) — "
                     f"дальнейшие платные вызовы заблокированы, реальный расход "
                     f"неизвестен. Сверь {usage_file(out_dir)} вручную, либо "
                     f"--force чтобы продолжить вслепую.")

        # F-13 (гейт круга 2): раньше call() сама пропускала HTTPError/URLError/
        # битый JSON наружу необработанными — исключение улетало из-под
        # usage_lock БЕЗ записи вообще (не только на status 400, который
        # круг 1 уже закрывал). Теперь call() поднимает ApiCallError, и запись
        # идёт по ЕДИНОМУ пути на любой ветке ДО sys.exit — включая ветку, где
        # ответ вообще не получен (rows/cost неизвестны и честно равны нулю:
        # SpyFu берёт деньги за фактически ВОЗВРАЩЁННЫЕ строки, ноль ответа —
        # ноль строк — ноль cost по их же модели биллинга, но сам факт
        # попытки обязан остаться в учёте, а не пропасть бесследно).
        #
        # R3-1 (независимый гейт, круг 4): круг 3 закрыл потерю расхода через
        # `except Exception` в call() — но `except Exception` не ловит
        # BaseException (Ctrl-C/KeyboardInterrupt, SystemExit, GeneratorExit),
        # и ни один except не ловит SIGKILL. Правильный уровень — до отправки
        # запроса: пишем намерение (write-ahead) ДО call(), не после. SpyFu
        # не знает cost/rows до ответа — поэтому write-ahead помечает вызов
        # как cost_unknown_calls, а после успешного ответа уточняет запись на
        # месте (никакой отдельной «уточняющей» записи, R3-4).
        u["cost_unknown_calls"] = u.get("cost_unknown_calls", 0) + 1
        save_usage(out_dir, u)

        error_message: str | None = None
        rows = 0
        cost = 0.0
        resp: dict = {}
        try:
            resp = call(b64, path, params)
        except ApiCallError as e:
            error_message = str(e)
            u["failed_calls"] = u.get("failed_calls", 0) + 1
            # Сумма так и остаётся неизвестной — write-ahead запись уже это
            # отражает (cost_unknown_calls), второй записи не будет (R3-4).
            save_usage(out_dir, u)
        else:
            is_error = isinstance(resp, dict) and resp.get("status") == 400
            rows = 0 if is_error else (len(resp.get("results", [])) if isinstance(resp, dict) else 0)
            cost = rows / 1000.0 * cpm
            if is_error:
                error_message = str(resp.get("errors", resp.get("title")))
            u["cost_unknown_calls"] = u.get("cost_unknown_calls", 0) - 1
            u["spent_usd"] = round(u.get("spent_usd", 0.0) + cost, 4)
            u["rows"] = u.get("rows", 0) + rows
            save_usage(out_dir, u)

        if error_message is not None:
            print(f"↑ вызов SpyFu {path} зафиксирован в учёте ({rows} строк, ${cost:.4f})",
                  file=sys.stderr)
            sys.exit(f"ERROR SpyFu: {error_message}")

    cpath.write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {rows} строк, ~${cost:.4f} (CPM ${cpm}); месяц: ${u['spent_usd']:.2f}/${budget} → {cpath}",
          file=sys.stderr)
    distill(resp)


def d_domain_stats(resp):
    rows = resp.get("results", []) if isinstance(resp, dict) else []
    print(f"domain: {resp.get('domain','')}")
    print("| мес | organic clicks | organic results | paid clicks | бюджет PPC $ | strength |")
    print("|---|---|---|---|---|---|")
    for r in rows[-12:]:  # последние 12 месяцев максимум
        print(f"| {r.get('searchYear')}-{r.get('searchMonth'):02d} | {r.get('monthlyOrganicClicks')} | "
              f"{r.get('totalOrganicResults')} | {r.get('monthlyPaidClicks')} | "
              f"{r.get('monthlyBudget')} | {r.get('strength')} |")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["usage", "domain-stats", "raw"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--all", action="store_true", help="domain-stats: вся история (дороже)")
    ap.add_argument("--cc", default="US", help="countryCode: US|GB|CA|DE|FR|AU... (НЕ RU)")
    ap.add_argument("--budget", type=budget_arg, default=40, help="месячный бюджет $ (Pro=$40)")
    ap.add_argument("--ttl", type=ttl_arg, default=30)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--cpm", type=cpm_arg, default=0.50, help="для raw: CPM эндпоинта")
    ap.add_argument("--param", action="append", default=[], help="для raw: k=v (повторяемо)")
    ap.add_argument("--out", default="./seo/research/spyfu")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out)

    if args.cmd == "usage":
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            u = load_usage(out_dir)
        except UsageLedgerError as e:
            sys.exit(f"ERROR: файл учёта трат SpyFu повреждён ({e}). Почини или "
                     f"удали {usage_file(out_dir)}.")
        budget = effective_budget(args)
        print(f"SpyFu usage за {u['month']}: ${u['spent_usd']:.2f}/${budget} "
              f"({u['rows']} строк). Точная сверка: spyfu.com/account/api")
        return 0

    b64 = load_auth()

    if args.cmd == "domain-stats":
        if not args.args:
            sys.exit("ERROR: domain-stats требует DOMAIN")
        key = "domain-stats-all" if args.all else "domain-stats-latest"
        path, cpm = ENDPOINTS[key]
        run(b64, path, cpm, {"domain": args.args[0], "countryCode": args.cc}, args, d_domain_stats)
    elif args.cmd == "raw":
        if not args.args:
            sys.exit("ERROR: raw требует PATH (напр. competitors_api/v2/...)")
        params = dict(p.split("=", 1) for p in args.param)
        run(b64, args.args[0], args.cpm, params, args,
            lambda r: print(json.dumps(r, ensure_ascii=False, indent=2)[:2000]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
