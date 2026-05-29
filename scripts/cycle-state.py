#!/usr/bin/env python3
"""
cycle-state.py — контракт состояния SEO-цикла («цепочка передачи» между фазовыми
скиллами). Хранит seo/cycles/<topic>/_state.json: какая фаза готова, что на
входе/выходе, пройден ли quality-gate. Любой фазовый скилл (seo-keywords,
seo-writing, ...) читает state на входе и обновляет на выходе.

Это основа модульной архитектуры: вместо одного большого скилла — независимые
фазовые скиллы, координируемые через единый файл состояния.

DAG фаз (зависимости по умолчанию):
  discovery → audit → keywords → clusters → entity_map → content_plan
            → writing → publishing → schema → monitoring → iteration

Статусы фаз: pending | in_progress | done | blocked
Фаза «ready» (готова к запуску) = pending И все depends_on имеют done+gate_passed.

Подкоманды:
  init   --topic "<тема>" [--dir DIR]      создать цикл + _state.json
  show   [--dir DIR]                       показать состояние (таблица)
  next   [--dir DIR] [--json]              какие фазы разблокированы сейчас
  set    <phase> --status S [--output F] [--gate-passed|--gate-failed] [--dir DIR]
  gate   <phase> [--dir DIR]               авто-проверка gate (output существует/непуст)

Использование:
  python3 cycle-state.py init --topic "минеральная вата"
  python3 cycle-state.py next
  python3 cycle-state.py set keywords --status done --output 02-keywords.md --gate-passed
"""

from __future__ import annotations
import argparse, datetime, glob, json, pathlib, re, sys

# Фаза → (зависимости, дефолтный артефакт-выход)
DEFAULT_PHASES = {
    "discovery":    ([],              "00-discovery.md"),
    "audit":        ["discovery"],
    "keywords":     ["audit"],
    "clusters":     ["keywords"],
    "entity_map":   ["clusters"],
    "content_plan": ["entity_map"],
    "writing":      ["content_plan"],
    "publishing":   ["writing"],
    "schema":       ["publishing"],
    "monitoring":   ["publishing"],
    "iteration":    ["monitoring"],
}
# дефолтные имена выходных артефактов
OUTPUTS = {
    "discovery": "00-discovery.md", "audit": "01-audit.md", "keywords": "02-keywords.md",
    "clusters": "03-clusters.md", "entity_map": "04-entity-maps/", "content_plan": "05-content-plan.md",
    "writing": "06-drafts/", "publishing": "07-published.md", "schema": "08-schema.md",
    "monitoring": "09-monitoring/", "iteration": "10-iterations.md",
}


def slugify(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    if not t:
        import hashlib
        t = hashlib.md5(text.encode()).hexdigest()[:12]
    return t


def quarter(d: datetime.date) -> str:
    return f"{d.year}-q{(d.month - 1) // 3 + 1}"


def find_state(dir_arg: str | None) -> pathlib.Path:
    if dir_arg:
        return pathlib.Path(dir_arg) / "_state.json"
    # последний по времени цикл
    cands = sorted(glob.glob("seo/cycles/*/_state.json"), key=lambda p: pathlib.Path(p).stat().st_mtime, reverse=True)
    if not cands:
        sys.exit("ERROR: нет циклов. Создай: cycle-state.py init --topic ...")
    return pathlib.Path(cands[0])


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: pathlib.Path, state: dict):
    state["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def recompute_blocked(state: dict):
    """Проставляет blocked фазам, у которых зависимость не done+gate."""
    ph = state["phases"]
    for name, p in ph.items():
        if p["status"] in ("done", "in_progress"):
            continue
        deps = p.get("depends_on", [])
        ok = all(ph.get(d, {}).get("status") == "done" and ph.get(d, {}).get("gate_passed") for d in deps)
        p["status"] = "pending" if ok else "blocked"


def ready_phases(state: dict) -> list[str]:
    ph = state["phases"]
    out = []
    for name, p in ph.items():
        if p["status"] != "pending":
            continue
        deps = p.get("depends_on", [])
        if all(ph.get(d, {}).get("status") == "done" and ph.get(d, {}).get("gate_passed") for d in deps):
            out.append(name)
    return out


def cmd_init(args):
    topic = args.topic
    cdir = pathlib.Path(args.dir) if args.dir else pathlib.Path("seo/cycles") / f"{slugify(topic)}-{quarter(datetime.date.today())}"
    cdir.mkdir(parents=True, exist_ok=True)
    phases = {}
    for name, deps in DEFAULT_PHASES.items():
        deps = deps if isinstance(deps, list) else deps[0]
        phases[name] = {"status": "pending", "depends_on": deps,
                        "output": OUTPUTS.get(name, ""), "gate_passed": False}
    state = {"topic": topic, "cycle_dir": str(cdir),
             "created": datetime.datetime.now().isoformat(timespec="seconds"),
             "updated": "", "phases": phases}
    recompute_blocked(state)
    sp = cdir / "_state.json"
    save(sp, state)
    print(f"✓ Цикл создан: {cdir}")
    print(f"  state: {sp}")
    print(f"  следующие фазы: {', '.join(ready_phases(state)) or '—'}")


def cmd_show(args):
    sp = find_state(args.dir)
    state = load(sp)
    print(f"== Цикл: {state['topic']} ({state['cycle_dir']}) ==")
    icons = {"done": "✓", "in_progress": "▶", "pending": "·", "blocked": "✗"}
    for name, p in state["phases"].items():
        g = " [gate✓]" if p.get("gate_passed") else ""
        dep = f" ← {','.join(p['depends_on'])}" if p.get("depends_on") else ""
        print(f"  {icons.get(p['status'],'?')} {name:<13} {p['status']}{g}{dep}")
    print(f"\n  READY: {', '.join(ready_phases(state)) or '—'}")


def cmd_next(args):
    state = load(find_state(args.dir))
    rp = ready_phases(state)
    if args.json:
        print(json.dumps(rp, ensure_ascii=False))
    else:
        print("\n".join(rp) if rp else "(нет разблокированных фаз — цикл завершён или ждёт gate)")


def cmd_set(args):
    sp = find_state(args.dir)
    state = load(sp)
    if args.phase not in state["phases"]:
        sys.exit(f"ERROR: неизвестная фаза '{args.phase}'")
    p = state["phases"][args.phase]
    if args.status:
        p["status"] = args.status
    if args.output:
        p["output"] = args.output
    if args.gate_passed:
        p["gate_passed"] = True
    if args.gate_failed:
        p["gate_passed"] = False
    recompute_blocked(state)
    save(sp, state)
    print(f"✓ {args.phase}: status={p['status']} gate={p['gate_passed']} output={p.get('output','')}")
    print(f"  READY: {', '.join(ready_phases(state)) or '—'}")


def cmd_gate(args):
    sp = find_state(args.dir)
    state = load(sp)
    p = state["phases"].get(args.phase)
    if not p:
        sys.exit(f"ERROR: неизвестная фаза '{args.phase}'")
    out = pathlib.Path(state["cycle_dir"]) / p.get("output", "")
    # generic gate: артефакт существует и непуст (файл) либо непустой каталог
    ok = False
    if out.is_dir():
        ok = any(out.iterdir())
    elif out.is_file():
        ok = out.stat().st_size > 0
    p["gate_passed"] = ok
    recompute_blocked(state)
    save(sp, state)
    print(f"{'✓ PASS' if ok else '✗ FAIL'}: gate {args.phase} (output: {out})")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("init"); pi.add_argument("--topic", required=True); pi.add_argument("--dir")
    ps = sub.add_parser("show"); ps.add_argument("--dir")
    pn = sub.add_parser("next"); pn.add_argument("--dir"); pn.add_argument("--json", action="store_true")
    pst = sub.add_parser("set"); pst.add_argument("phase")
    pst.add_argument("--status", choices=["pending", "in_progress", "done", "blocked"])
    pst.add_argument("--output"); pst.add_argument("--dir")
    pst.add_argument("--gate-passed", action="store_true"); pst.add_argument("--gate-failed", action="store_true")
    pg = sub.add_parser("gate"); pg.add_argument("phase"); pg.add_argument("--dir")
    args = ap.parse_args()

    return {"init": cmd_init, "show": cmd_show, "next": cmd_next,
            "set": cmd_set, "gate": cmd_gate}[args.cmd](args) or 0


if __name__ == "__main__":
    sys.exit(main())
