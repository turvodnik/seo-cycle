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

from seo_cycle_core.spend_guard import armed_spend
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
    try:
        import yaml
    except ImportError:
        return {}
    for rel in ("seo-cycle.yaml", ".seo-cycle.yaml", "seo/seo-cycle.yaml"):
        p = pathlib.Path.cwd() / rel
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}


def post(token: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode(),
                                 headers={"X-Keyso-TOKEN": token, "Content-Type": "application/json"})

    # T-089 round 3: found while strengthening the static host-scan (a third
    # api.keys.so client sharing the same quota as keyso-fetch.py/
    # competitor-discovery.py, R2-4/finding H) — bump_counter() was called
    # AFTER reading the response, the exact F-1 class. api.keys.so is a
    # PAID_HOSTS member; urlopen() to it now refuses without this block.
    def _write_ahead() -> bool:
        bump_counter(_USAGE_DIR, field="requests")
        return True

    try:
        with armed_spend(_write_ahead, hosts="api.keys.so"):
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
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
