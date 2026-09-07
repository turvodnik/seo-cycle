#!/usr/bin/env python3
"""skill-manifest-validate.py — консистентность skills/manifest.yaml и дерева skills/.

Проверки:
  * каждый модуль из manifest существует, его entry-файл читается и несёт frontmatter name;
  * фазы 0..10 покрыты ровно один раз (оркестратор + модули, без дыр и дублей);
  * каждый каталог skills/<name> (кроме _shared) объявлен в manifest;
  * все shared-файлы существуют;
  * каждый compat-шим — существующий symlink, указывающий внутрь skills/.

Exit: 0 ok, 1 findings, 2 config error.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: PyYAML не установлен. python3 -m pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = pathlib.Path(__file__).resolve().parent.parent


def validate(root: pathlib.Path) -> list[str]:
    findings: list[str] = []
    manifest_path = root / "skills" / "manifest.yaml"
    if not manifest_path.exists():
        return [f"manifest отсутствует: {manifest_path}"]
    # T-090 (F-8): manifest, not the project's config — tolerant load.
    from seo_cycle_core.config import load_yaml_any
    data = load_yaml_any(manifest_path)
    data = data if isinstance(data, dict) else {}

    modules = data.get("modules") or {}
    phases_seen: dict[int, str] = {}
    for ph in (data.get("orchestrator") or {}).get("phases", []):
        phases_seen[int(ph)] = "orchestrator"

    for name, spec in modules.items():
        entry = root / str((spec or {}).get("entry", ""))
        if not entry.is_file():
            findings.append(f"{name}: entry не найден: {spec.get('entry')}")
            continue
        head = entry.read_text(encoding="utf-8", errors="replace")[:600]
        if f"name: {name}" not in head:
            findings.append(f"{name}: frontmatter name не совпадает с ключом manifest")
        for ph in (spec or {}).get("phases", []):
            ph = int(ph)
            if ph in phases_seen:
                findings.append(f"фаза {ph} объявлена дважды: {phases_seen[ph]} и {name}")
            phases_seen[ph] = name

    missing_phases = [p for p in range(0, 11) if p not in phases_seen]
    if missing_phases:
        findings.append(f"непокрытые фазы: {missing_phases}")

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            if not child.is_dir() or child.name == "_shared":
                continue
            if child.name not in modules:
                findings.append(f"каталог skills/{child.name} не объявлен в manifest")

    for rel in data.get("shared", []) or []:
        if not (root / rel).is_file():
            findings.append(f"shared-файл отсутствует: {rel}")

    for rel in data.get("compat_shims", []) or []:
        shim = root / rel
        if not shim.is_symlink():
            findings.append(f"шим не является symlink: {rel}")
            continue
        target = (shim.parent / shim.readlink()).resolve()
        if not target.exists():
            findings.append(f"шим битый: {rel} → {shim.readlink()}")
        elif "skills" not in target.parts:
            findings.append(f"шим указывает вне skills/: {rel} → {shim.readlink()}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help="корень репозитория seo-cycle")
    args = parser.parse_args(argv)
    findings = validate(pathlib.Path(args.root))
    if findings:
        for f in findings:
            print(f"✗ {f}")
        print(f"\n{len(findings)} finding(s)")
        return 1
    print("✓ skills/manifest.yaml согласован с деревом skills/ (фазы 0–10 покрыты)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
