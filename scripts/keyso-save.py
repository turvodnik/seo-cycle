#!/usr/bin/env python3
"""
keyso-save.py — сохранение данных В кабинет Keys.so (write-API).

⚠ Из write-операций Keys.so API стабильно работает только групповой отчёт по
доменам (`POST /report/group`) — он сохраняет в кабинет сравнение доменов
(конкуренты + ваш домен). Эндпоинты clustering/my_projects/position-monitoring
на текущем маршруте отвечают "Method not allowed / OPTIONS only" — недоступны
через API (делается в UI Keys.so). Поэтому семантику/кластеризацию храним у себя
(seo/cycles + seo.db + Obsidian), а в Keys.so сохраняем групповой отчёт конкурентов.

Auth: X-Keyso-TOKEN (env KEYSO_API_TOKEN).

Команды:
  group-report --domains a.ru,b.ru[,...] [--name "..."] [--base msk] [--top 10]
  group-report --from-config            # домены = свой + business_profile.competitors

Пример:
  python3 keyso-save.py group-report --from-config --name "emwoody vs конкуренты"
"""

from __future__ import annotations
import argparse, json, os, pathlib, sys, urllib.request, urllib.error

from seo_cycle_core.usage_ledger import bump_counter

API = "https://api.keys.so"
# R2-4 (независимый гейт, круг 3): третий клиент той же квоты api.keys.so,
# что keyso-fetch.py и competitor-discovery.py — тот же out_dir, тот же
# общий bump_counter().
_USAGE_DIR = pathlib.Path("./seo/research/keyso")

def load_token() -> str:
    tok = os.environ.get("KEYSO_API_TOKEN")
    if tok:
        return tok.strip()
    for rel in (".env", "seo/.env"):
        p = pathlib.Path.cwd() / rel
        if p.exists():
            for line in p.read_text().splitlines():
                if line.strip().startswith("KEYSO_API_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("ERROR: KEYSO_API_TOKEN не найден")


def load_config() -> dict:
    # T-090 (F-7/F-8): this used to be its own hand-rolled loader with an
    # `except ImportError: return {}` fallback — a dangerous class on its
    # own: a broken PyYAML install silently looked identical to "no
    # config", the same silent-success failure mode F-7/F-7b exist to
    # close, just triggered by a missing dependency instead of an empty
    # file. Routes through the shared core loader now — if PyYAML truly
    # isn't installed, `seo_cycle_core.config.load_config` itself returns
    # `{}` (unchanged for a missing OPTIONAL config in a write-only tool
    # like this one), but a MALFORMED config gets the same coordinate-
    # bearing error + exit(2) every other command gets, instead of this
    # file's own silent swallow.
    from seo_cycle_core.config import find_config, load_config as _load_config
    found = find_config(pathlib.Path.cwd())
    if found is None:
        return {}
    return _load_config(found)


def post(token: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode(),
                                 headers={"X-Keyso-TOKEN": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
            bump_counter(_USAGE_DIR, field="requests")
            return data
    except urllib.error.HTTPError as e:
        sys.exit(f"ERROR Keys.so HTTP {e.code}: {e.read()[:200]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("group-report")
    g.add_argument("--domains", help="домены через запятую")
    g.add_argument("--from-config", action="store_true", help="свой домен + business_profile.competitors")
    g.add_argument("--name")
    g.add_argument("--base", default="msk")
    g.add_argument("--top", type=int, default=10, choices=[10, 50])
    args = ap.parse_args()

    token = load_token()

    if args.cmd == "group-report":
        domains = []
        if args.from_config:
            cfg = load_config()
            bp = cfg.get("business_profile", {}) or {}
            own = (bp.get("url", "") or "").replace("https://", "").replace("http://", "").strip("/")
            if own:
                domains.append(own)
            for c in bp.get("competitors", []) or []:
                d = c.get("domain") if isinstance(c, dict) else None
                if d:
                    domains.append(d)
        if args.domains:
            domains += [d.strip() for d in args.domains.split(",") if d.strip()]
        domains = list(dict.fromkeys(domains))  # dedup, keep order
        if not domains:
            sys.exit("ERROR: нет доменов (--domains или --from-config)")
        # Keys.so group report: лимит доменов в отчёте обычно ≤ 10-20
        body = {"base": args.base, "top": args.top, "domains": domains[:20], "name": args.name}
        res = post(token, "/report/group", body)
        rid = res.get("rid")
        print(f"✓ Групповой отчёт сохранён в Keys.so (rid: {rid})")
        print(f"  Домены ({len(domains)}): {', '.join(domains)}")
        print(f"  Смотреть: кабинет Keys.so → Отчёты по группе доменов (rid {rid})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
