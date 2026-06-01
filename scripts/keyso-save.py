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

API = "https://api.keys.so"

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
    try:
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
