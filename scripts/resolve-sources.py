#!/usr/bin/env python3
"""
resolve-sources.py — разворачивает региональный профиль источников в финальный
список «что запускать в Phase 2», объединяя его с локальными override проекта.

Логика слияния (по убыванию приоритета):
  1. sources_disable профиля   → жёсткий OFF (недоступно в регионе), не переопределить.
  2. локальный sources.<name>.enabled в seo-cycle.yaml → override профиля.
  3. sources_enable профиля     → база (ON по умолчанию для региона).
  4. sources_proxy профиля      → ON, но с warning «нужен прокси».

Если в конфиге нет region_profile — работает в legacy-режиме: берёт sources.*
как есть (обратная совместимость со старыми конфигами).

Выводит человекочитаемый отчёт и пишет машинный JSON в
  <project>/seo/cycles/<date>/active-sources.json
(каталог можно переопределить через --out).

Использование:
    python3 ~/.codex/skills/seo-cycle/scripts/resolve-sources.py [config] [--out DIR] [--json]
"""

from __future__ import annotations
import argparse, datetime, json, pathlib, sys

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. `pip3 install pyyaml`", file=sys.stderr)
    sys.exit(2)

CONFIG_SEARCH_PATHS = [
    "seo-cycle.yaml", ".seo-cycle.yaml",
    "seo/seo-cycle.yaml", ".claude/seo-cycle.yaml",
]
PROFILES_DIR = pathlib.Path(__file__).resolve().parent.parent / "config" / "region-profiles"


def find_config(start: pathlib.Path) -> pathlib.Path | None:
    for rel in CONFIG_SEARCH_PATHS:
        p = start / rel
        if p.exists():
            return p
    return None


def load_yaml(path: pathlib.Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def local_source_enabled(sources: dict, name: str):
    """Вернёт True/False если в конфиге явно задан sources.<name>.enabled, иначе None."""
    node = sources.get(name)
    if isinstance(node, dict) and "enabled" in node:
        return bool(node["enabled"])
    # llm_cli — особый случай: вложенные antigravity/codex
    return None


def resolve(cfg: dict, profile: dict) -> dict:
    sources = cfg.get("sources", {}) or {}
    enable = set(profile.get("sources_enable", []))
    disable = set(profile.get("sources_disable", []))
    proxy = set(profile.get("sources_proxy", []))

    # Вселенная имён источников = всё, что упомянуто в профиле или локально
    universe = enable | disable | proxy | set(sources.keys())

    active, skipped = {}, {}
    for name in sorted(universe):
        local = local_source_enabled(sources, name)

        if name in disable:
            # Жёсткий регион-блок. Локальный enable=true → конфликт, предупреждаем.
            reason = "недоступно в регионе (sources_disable профиля)"
            if local is True:
                reason += " — ВНИМАНИЕ: локальный enabled:true проигнорирован"
            skipped[name] = reason
            continue

        if local is False:
            skipped[name] = "выключено локально (sources.{}.enabled: false)".format(name)
            continue

        if local is True or name in enable:
            entry = {"via": "local-override" if local is True else "profile"}
            if name in proxy:
                entry["proxy_required"] = True
                entry["note"] = "работает в регионе только через прокси"
            active[name] = entry
            continue

        # Не в enable, локально не указан, не disable — нейтрально пропускаем
        skipped[name] = "не входит в профиль региона"

    return {"active": active, "skipped": skipped}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("config", nargs="?", help="путь к seo-cycle.yaml")
    ap.add_argument("--out", help="каталог для active-sources.json")
    ap.add_argument("--json", action="store_true", help="печатать только JSON в stdout")
    args = ap.parse_args()

    cwd = pathlib.Path.cwd()
    cfg_path = pathlib.Path(args.config) if args.config else find_config(cwd)
    if not cfg_path or not cfg_path.exists():
        print("ERROR: seo-cycle.yaml не найден", file=sys.stderr)
        return 2
    project_root = cfg_path.parent if cfg_path.parent.name != "seo" and cfg_path.parent.name != ".claude" else cfg_path.parent.parent
    cfg = load_yaml(cfg_path)

    profile_id = cfg.get("region_profile")
    legacy = profile_id is None

    if legacy:
        # Обратная совместимость: профиля нет — отдаём sources.* как есть
        sources = cfg.get("sources", {}) or {}
        active, skipped = {}, {}
        for name, _node in sources.items():
            en = local_source_enabled(sources, name)
            if en is False:
                skipped[name] = "выключено локально"
            else:
                active[name] = {"via": "legacy-config"}
        result = {"active": active, "skipped": skipped}
        profile = {"id": None}
    else:
        prof_path = PROFILES_DIR / f"{profile_id}.yaml"
        if not prof_path.exists():
            avail = ", ".join(sorted(p.stem for p in PROFILES_DIR.glob("*.yaml")))
            print(f"ERROR: профиль '{profile_id}' не найден. Доступны: {avail}", file=sys.stderr)
            return 2
        profile = load_yaml(prof_path)
        result = resolve(cfg, profile)

    out = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "region_profile": profile_id,
        "engines": profile.get("engines", cfg.get("engines")),
        "atp_translate": profile.get("atp_translate"),
        "neuronwriter_engine": profile.get("neuronwriter_engine"),
        **result,
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # Человекочитаемый отчёт
    print(f"== resolve-sources ==")
    print(f"  config:  {cfg_path}")
    print(f"  profile: {profile_id or '(legacy — нет region_profile)'}")
    if profile.get("engines"):
        eng = ", ".join(f"{e['name']}(#{e['priority']})" for e in profile["engines"])
        print(f"  engines: {eng}")
    print(f"\n  АКТИВНЫЕ источники ({len(result['active'])}):")
    for name, meta in sorted(result["active"].items()):
        tag = " [PROXY]" if meta.get("proxy_required") else ""
        print(f"    + {name}{tag}  ({meta['via']})")
    print(f"\n  ПРОПУЩЕНО ({len(result['skipped'])}):")
    for name, reason in sorted(result["skipped"].items()):
        print(f"    - {name}: {reason}")

    # JSON-артефакт
    out_dir = pathlib.Path(args.out) if args.out else (
        project_root / "seo" / "cycles" / datetime.date.today().isoformat()
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "active-sources.json"
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  → {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
