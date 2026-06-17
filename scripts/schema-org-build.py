#!/usr/bin/env python3
"""
schema-org-build.py — строит канонический JSON-LD узел организации
(Organization / LocalBusiness) из секции business_profile в seo-cycle.yaml.

Это E-E-A-T фундамент: один узел с @id, на который ссылаются author/publisher
во ВСЕХ Article/Product schema. Несёт trust-сигналы: адрес, телефон, часы,
areaServed, knowsAbout, sameAs — то, что связывает контент с реальным бизнесом.

Режимы:
  build         напечатать узел организации (по умолчанию) — stdout JSON.
  inject FILE   вставить узел в @graph указанного schema-файла и заменить
                author/publisher на @id-референс (idempotent).

@id организации: <url>#org  (стабилен, можно ссылаться отовсюду).

Использование:
    python3 schema-org-build.py build
    python3 schema-org-build.py inject schema/article-foo.json
    python3 schema-org-build.py inject schema/*.json     # через shell-glob
"""

from __future__ import annotations
import argparse, json, pathlib, sys

from seo_cycle_core.config import find_config, load_yaml

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. `pip3 install pyyaml`", file=sys.stderr)
    sys.exit(2)


def build_org(cfg: dict) -> dict:
    bp = cfg.get("business_profile") or {}
    if not bp:
        raise SystemExit("ERROR: в конфиге нет секции business_profile")
    url = bp.get("url", "").rstrip("/") + "/"
    org_id = f"{url}#org"
    node: dict = {
        "@type": bp.get("schema_type", "Organization"),
        "@id": org_id,
        "name": bp.get("legal_name") or cfg.get("project", {}).get("brand_name_user_facing"),
        "url": url,
    }
    if bp.get("logo"):
        node["logo"] = {"@type": "ImageObject", "url": bp["logo"]}
    if bp.get("telephone"):
        node["telephone"] = bp["telephone"]

    addr = bp.get("address") or {}
    if addr:
        node["address"] = {
            "@type": "PostalAddress",
            "streetAddress": addr.get("street"),
            "addressLocality": addr.get("locality"),
            "addressRegion": addr.get("region"),
            "addressCountry": addr.get("country"),
        }
    if bp.get("opening_hours"):
        node["openingHours"] = bp["opening_hours"]
    if bp.get("area_served"):
        node["areaServed"] = [{"@type": "AdministrativeArea", "name": a} for a in bp["area_served"]]
    if bp.get("knows_about"):
        node["knowsAbout"] = bp["knows_about"]
    if bp.get("same_as"):
        node["sameAs"] = bp["same_as"]
    # Услуги как makesOffer/Service — мягкий E-E-A-T сигнал охвата
    if bp.get("services"):
        node["makesOffer"] = [
            {"@type": "Offer", "itemOffered": {"@type": "Service", "name": s}}
            for s in bp["services"]
        ]
    return {"id": org_id, "node": {k: v for k, v in node.items() if v is not None}}


def inject(path: pathlib.Path, org_id: str, org_node: dict) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    graph = data.get("@graph")
    if graph is None:
        # одиночный узел → завернуть в @graph
        graph = [data]
        data = {"@context": "https://schema.org", "@graph": graph}

    # 1. upsert org-узла (по @id)
    graph[:] = [n for n in graph if n.get("@id") != org_id]
    graph.insert(0, org_node)

    # 2. author/publisher во всех узлах → @id-референс
    ref = {"@id": org_id}
    changed = 0
    for n in graph:
        if n.get("@id") == org_id:
            continue
        for field in ("author", "publisher"):
            if field in n and n[field] != ref:
                n[field] = ref
                changed += 1

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f"{path.name}: org-узел upsert, ссылок author/publisher переписано: {changed}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "inject"], nargs="?", default="build")
    ap.add_argument("files", nargs="*", help="schema-файлы для inject")
    ap.add_argument("--config", help="путь к seo-cycle.yaml")
    args = ap.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print("ERROR: seo-cycle.yaml не найден", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)

    built = build_org(cfg)

    if args.cmd == "build":
        print(json.dumps({"@context": "https://schema.org", "@graph": [built["node"]]},
                         ensure_ascii=False, indent=2))
        return 0

    if not args.files:
        print("ERROR: inject требует список файлов", file=sys.stderr)
        return 2
    for f in args.files:
        p = pathlib.Path(f)
        if not p.exists():
            print(f"  ! пропуск (нет файла): {f}", file=sys.stderr)
            continue
        print("  " + inject(p, built["id"], built["node"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
