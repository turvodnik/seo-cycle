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
  init   --topic "<тема>" [--dir DIR] [--force]
                                           создать цикл + _state.json (существующий
                                           _state.json — отказ кода 1; --force перезаписывает)
  show   [--dir DIR]                       показать состояние (таблица)
  next   [--dir DIR] [--json]              какие фазы разблокированы сейчас
  set    <phase> --status S [--output F] [--gate-passed|--gate-failed] [--dir DIR]
  gate   <phase> [--dir DIR]               авто-проверка gate (output существует/непуст)
  import <тема> [--from DIR] [--map F] [--dry-run|--write] [--dir DIR]
                                           поднять старые артефакты фаз в _state.json
                                           (по умолчанию dry-run; импорт ставит
                                           gate_passed: false — ворота не проходились)

Использование:
  python3 cycle-state.py init --topic "минеральная вата"
  python3 cycle-state.py next
  python3 cycle-state.py set keywords --status done --output 02-keywords.md --gate-passed
"""

from __future__ import annotations
import argparse, contextlib, datetime, glob, io, json, os, pathlib, re, shlex, sys

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


# T-057: где у старых проектов лежат артефакты фаз (пути относительно --from,
# по умолчанию `seo/`). Первый найденный путь фазы становится её `output`.
# Фаз без записи (content_plan, publishing, schema, iteration) старые
# раскладки не знают — они остаются pending/blocked.
IMPORT_MAP: dict[str, list[str]] = {
    "discovery":  ["setup/context-pack.md"],
    "audit":      ["technical/technical-site-audit.md"],
    "keywords":   ["02-keywords.md", "keywords/"],
    "clusters":   ["03-clusters.md"],
    "entity_map": ["entities/"],
    "writing":    ["content-drafts/"],
    "monitoring": ["monitoring/"],
}


# Транслит кириллицы для имени каталога цикла (QA 3.0.1 Y7): раньше NFKD+ascii
# выбрасывал кириллицу целиком — тема «минеральная вата» давала md5-каталог,
# а «вата 2026» и «утеплитель 2026» сливались в один `2026`.
_TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g", "ў": "u",
})


def slugify(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFC", text).lower().translate(_TRANSLIT)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    if not t:
        import hashlib
        t = hashlib.md5(text.encode()).hexdigest()[:12]
    return t


def quarter(d: datetime.date) -> str:
    return f"{d.year}-q{(d.month - 1) // 3 + 1}"


def cycles_base() -> pathlib.Path:
    """Корень циклов: `artifacts.cycles_root` из конфига проекта (тот же ключ
    и тот же разбор, что у journey, — одна модель прогресса, QA 3.0.1 Y2);
    без конфига или при ошибке разбора — `seo/cycles`. Путь внутри проекта
    возвращается относительным от cwd (корня проекта), как раньше."""
    default = pathlib.Path("seo/cycles")
    try:
        from seo_cycle_core.config import find_config, load_yaml, project_root_for
        from seo_cycle_core.journey import cycles_root
        cfg_path = find_config(pathlib.Path.cwd())
        if cfg_path is None:
            return default
        # Битый конфиг — не дело cycle-state: молча берём seo/cycles, без
        # чужой строки об ошибке в выводе каждой подкоманды.
        with contextlib.redirect_stderr(io.StringIO()):
            cfg = load_yaml(cfg_path)
        root = cycles_root(cfg, project_root_for(cfg_path))
    except (Exception, SystemExit):
        return default
    return project_relative(root, pathlib.Path.cwd())


def project_relative(root: pathlib.Path, cwd: pathlib.Path) -> pathlib.Path:
    """`root` relative to the project (cwd) when it lies inside it, else as is.

    Never `resolve()` the whole `root`: `seo/` or `seo/cycles` may be a
    symlink to a folder outside the project (an Obsidian vault), and its
    resolved path is outside — an absolute path in `_state.json` breaks gates
    after a move (QA2 3.0.1 #1). But an absolute `cycles_root` may reach the
    project through a symlink above it (`~/ai` -> `~/Проекты ai`), so a purely
    lexical comparison misses it (QA3 3.0.1 #2). Order: lexical; then the
    nearest ancestor of `root` that is the cwd itself (symlinks above the
    project resolved, the part inside the project kept as written); else
    `root` unchanged (a root outside the project stays absolute)."""
    try:
        return root.relative_to(cwd)
    except ValueError:
        pass
    if root.is_absolute():
        try:
            real_cwd = cwd.resolve()
        except OSError:
            return root
        for ancestor in root.parents:
            try:
                if ancestor.resolve() == real_cwd:
                    return root.relative_to(ancestor)
            except (OSError, RuntimeError):
                continue
    return root


def find_state(dir_arg: str | None) -> pathlib.Path:
    if dir_arg:
        sp = pathlib.Path(dir_arg) / "_state.json"
        if not sp.is_file():
            print(f"ERROR: нет цикла в {dir_arg} ({sp} не найден). Каталог цикла печатают init/import; "
                  f"список: ls {cycles_base()}", file=sys.stderr)
            raise SystemExit(2)
        return sp
    # последний по времени цикл
    cands = sorted(glob.glob(str(cycles_base() / "*" / "_state.json")),
                   key=lambda p: pathlib.Path(p).stat().st_mtime, reverse=True)
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
    for _name, p in ph.items():
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
    cdir = pathlib.Path(args.dir) if args.dir else cycles_base() / f"{slugify(topic)}-{quarter(datetime.date.today())}"
    sp = cdir / "_state.json"
    if sp.exists() and not args.force:
        # QA6 3.0.1 #5: a repeated init silently wiped phases and gate marks.
        print(f"ERROR: {sp} уже существует — init не перезаписывает состояние цикла.\n"
              f"  Посмотреть: seo-cycle cycle show --dir {shlex.quote(str(cdir))}\n"
              f"  Начать заново (прогресс фаз будет стёрт): добавь --force",
              file=sys.stderr)
        return 1
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
    save(sp, state)
    print(f"✓ Цикл создан: {cdir}")
    print(f"  state: {sp}")
    print(f"  следующие фазы: {', '.join(ready_phases(state)) or '—'}")


def cmd_show(args):
    sp = find_state(args.dir)
    state = load(sp)
    print(f"== Цикл: {state['topic']} ({state['cycle_dir']}) ==")
    icons = {"done": "✓", "in_progress": "▶", "pending": "·", "blocked": "✗"}
    unconfirmed = []
    waiting = []
    for name, p in state["phases"].items():
        g = " [gate✓]" if p.get("gate_passed") else ""
        if p.get("imported_from") and p.get("status") != "done":
            g += " [импорт: файлы есть, предыдущая фаза не найдена]"
            waiting.append(name)
        elif p.get("imported_from") and not p.get("gate_passed"):
            g = " [импорт, gate_passed: false — ворота не проходились]"
            unconfirmed.append(name)
        dep = f" ← {','.join(p['depends_on'])}" if p.get("depends_on") else ""
        print(f"  {icons.get(p['status'],'?')} {name:<13} {p['status']}{g}{dep}")
    print(f"\n  READY: {', '.join(ready_phases(state)) or '—'}")
    if unconfirmed:
        print(f"\n  ⚠ Импортированы из старых артефактов, ворота не проходились: {', '.join(unconfirmed)}.\n"
              f"    Файлы есть, качество не подтверждено; следующие фазы ждут ворот.\n"
              f"    Подтвердить: seo-cycle cycle gate <фаза> --dir {shlex.quote(str(state['cycle_dir']))}")
    if waiting:
        print(f"\n  ⚠ Импортированы, но ждут предыдущих фаз: {', '.join(waiting)}.\n"
              f"    Файлы найдены, а фаза перед ними — нет; закрыть их можно после предыдущих:\n"
              f"    seo-cycle cycle set <фаза> --status done --dir {shlex.quote(str(state['cycle_dir']))}")


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


def resolve_output(cycle_dir: str, phase: dict) -> pathlib.Path:
    """Артефакт фазы — внутри каталога цикла (`02-keywords.md`), как в 3.0.0.

    Путь от корня проекта (`seo/02-keywords.md`) берётся ТОЛЬКО для фазы,
    записанной `import`: её `output` взят из `imported_from` и отсчитан от
    корня. Для фаз из `init`/`set` запасного пути нет: стандартные имена
    одинаковы у всех циклов, и посторонний `02-keywords.md` в корне открыл бы
    ворота любому циклу (QA 3.0.1 R1). `cycle_dir` в state отсчитан от корня
    проекта, поэтому оба варианта считаются от одной точки — cwd."""
    output = phase.get("output", "") or ""
    out = pathlib.Path(cycle_dir) / output
    imported = phase.get("imported_from")
    if (output and not out.exists() and isinstance(imported, list) and output in imported
            and pathlib.Path(output).exists()):
        return pathlib.Path(output)
    return out


def _file_has_content(path: pathlib.Path) -> bool:
    """Хоть один непробельный байт (читается кусками, файл целиком не грузится)."""
    try:
        with path.open("rb") as fh:
            while chunk := fh.read(65536):
                if chunk.strip():
                    return True
    except OSError:
        return False
    return False


def _has_content(path: pathlib.Path) -> bool:
    """Артефакт есть: файл с непробельным содержимым или каталог, где где-то
    внутри лежит такой файл. Скрытые записи (`.gitkeep`, `.DS_Store`, `.git`)
    и пустые подкаталоги не считаются (QA 3.0.1 Y4). Одно правило для
    `import` и для `gate`."""
    if path.is_dir():
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                if not name.startswith(".") and _file_has_content(pathlib.Path(root) / name):
                    return True
        return False
    return path.is_file() and _file_has_content(path)


def _display(path: pathlib.Path) -> str:
    """Путь от корня проекта (cwd), если артефакт внутри него; иначе абсолютный."""
    try:
        return path.resolve().relative_to(pathlib.Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def load_import_map(map_file: str | None) -> dict[str, list[str]]:
    """Карта по умолчанию + JSON-файл `{"фаза": "путь" | ["путь", ...]}` поверх неё."""
    mapping = {phase: list(paths) for phase, paths in IMPORT_MAP.items()}
    if not map_file:
        return mapping
    try:
        raw = json.loads(pathlib.Path(map_file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"ERROR: карта {map_file} не читается как JSON: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if not isinstance(raw, dict):
        print(f"ERROR: карта {map_file}: нужен объект {{\"фаза\": [\"путь\", ...]}}", file=sys.stderr)
        raise SystemExit(2)
    for phase, paths in raw.items():
        if phase not in DEFAULT_PHASES:
            print(f"ERROR: карта {map_file}: неизвестная фаза '{phase}' "
                  f"(есть: {', '.join(DEFAULT_PHASES)})", file=sys.stderr)
            raise SystemExit(2)
        if isinstance(paths, str):
            paths = [paths]
        if not isinstance(paths, list) or not all(isinstance(x, str) and x for x in paths):
            print(f"ERROR: карта {map_file}: у фазы '{phase}' нужен путь или список путей", file=sys.stderr)
            raise SystemExit(2)
        mapping[phase] = paths
    return mapping


def cmd_import(args):
    cdir = pathlib.Path(args.dir) if args.dir else cycles_base() / slugify(args.topic)
    sp = cdir / "_state.json"
    src = pathlib.Path(args.from_dir)
    if not src.is_dir():
        print(f"ERROR: каталог артефактов {src} не найден (запускай из корня проекта или задай --from)",
              file=sys.stderr)
        return 2
    mapping = load_import_map(args.map)
    exists = sp.exists()
    if exists and args.write:
        alt = f"{args.topic}-import"
        print(f"ERROR: {sp} уже существует — импорт не перезаписывает состояние цикла.\n"
              f"  Посмотреть: seo-cycle cycle show --dir {shlex.quote(str(cdir))}\n"
              f"  Новый цикл: другая тема, например seo-cycle cycle import {shlex.quote(alt)} --write"
              f" (каталог {cdir.parent / slugify(alt)})",
              file=sys.stderr)
        return 1

    phases: dict = {}
    found: dict[str, list[str]] = {}
    for name, deps in DEFAULT_PHASES.items():
        deps = deps if isinstance(deps, list) else deps[0]
        hits = [_display(src / rel) for rel in mapping.get(name, []) if _has_content(src / rel)]
        phase = {"status": "pending", "depends_on": deps,
                 "output": hits[0] if hits else OUTPUTS.get(name, ""), "gate_passed": False}
        if hits:
            # Ворота задним числом не подтверждаем: done, но gate_passed: false.
            # Фаза, чей предшественник не найден, остаётся blocked (файлы
            # записаны в imported_from): иначе её ворота закрыли бы стадию
            # journey в обход DAG (гейт T-057, 💭2). DEFAULT_PHASES идут в
            # порядке DAG, поэтому статус предшественника уже известен.
            if all(phases.get(d, {}).get("status") == "done" for d in deps):
                phase["status"] = "done"
            phase["imported_from"] = hits
            found[name] = hits
        phases[name] = phase
    now = datetime.datetime.now().isoformat(timespec="seconds")
    state = {"topic": args.topic, "cycle_dir": str(cdir), "created": now, "updated": "",
             "imported_at": now, "phases": phases}
    recompute_blocked(state)

    mode = "запись" if args.write else "dry-run, ничего не записано"
    print(f"== cycle import: {args.topic} → {sp} ({mode}) ==")
    for name, p in phases.items():
        if name in found:
            extra = f" (+ {', '.join(found[name][1:])})" if len(found[name]) > 1 else ""
            print(f"  {name:<13} {p['status']:<8} {found[name][0]}{extra}")
        else:
            print(f"  {name:<13} {p['status']:<8} — не найдено")
    print(f"\n  Найдено фаз: {len(found)} из {len(phases)}. Импортированные фазы получают gate_passed: false —"
          f" ворота задним числом не подтверждаются.")
    if not args.write:
        if exists:
            print(f"  ⚠ {sp} уже существует — --write откажет.")
        else:
            hint = ["seo-cycle", "cycle", "import", args.topic]
            if args.dir:
                hint += ["--dir", args.dir]
            if args.from_dir != "seo":
                hint += ["--from", args.from_dir]
            if args.map:
                hint += ["--map", args.map]
            print(f"  Записать: {shlex.join(hint + ['--write'])}")
        return 0
    cdir.mkdir(parents=True, exist_ok=True)
    save(sp, state)
    print(f"✓ Записано: {sp}")
    print(f"  Подтвердить фазу: seo-cycle cycle gate <фаза> --dir {shlex.quote(str(cdir))}")
    return 0


def cmd_gate(args):
    sp = find_state(args.dir)
    state = load(sp)
    p = state["phases"].get(args.phase)
    if not p:
        sys.exit(f"ERROR: неизвестная фаза '{args.phase}'")
    out = resolve_output(state["cycle_dir"], p)
    # generic gate: артефакт существует и непуст (файл) либо непустой каталог
    ok = _has_content(out)
    p["gate_passed"] = ok
    recompute_blocked(state)
    save(sp, state)
    print(f"{'✓ PASS' if ok else '✗ FAIL'}: gate {args.phase} (output: {out})")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("init"); pi.add_argument("--topic", required=True); pi.add_argument("--dir")
    pi.add_argument("--force", action="store_true", help="перезаписать существующий _state.json (прогресс фаз стирается)")
    ps = sub.add_parser("show"); ps.add_argument("--dir")
    pn = sub.add_parser("next"); pn.add_argument("--dir"); pn.add_argument("--json", action="store_true")
    pst = sub.add_parser("set"); pst.add_argument("phase")
    pst.add_argument("--status", choices=["pending", "in_progress", "done", "blocked"])
    pst.add_argument("--output"); pst.add_argument("--dir")
    pst.add_argument("--gate-passed", action="store_true"); pst.add_argument("--gate-failed", action="store_true")
    pg = sub.add_parser("gate"); pg.add_argument("phase"); pg.add_argument("--dir")
    pim = sub.add_parser("import", help="поднять старые артефакты фаз в _state.json (dry-run по умолчанию)")
    pim.add_argument("topic")
    pim.add_argument("--from", dest="from_dir", default="seo", help="каталог артефактов (по умолчанию seo)")
    pim.add_argument("--map", help="JSON {\"фаза\": [\"путь от --from\", ...]} поверх карты по умолчанию")
    pim.add_argument("--dir", help="каталог цикла (по умолчанию <artifacts.cycles_root>/<тема>, обычно seo/cycles)")
    mode = pim.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="только показать карту (по умолчанию)")
    mode.add_argument("--write", action="store_true", help="создать _state.json")
    args = ap.parse_args()

    return {"init": cmd_init, "show": cmd_show, "next": cmd_next,
            "set": cmd_set, "gate": cmd_gate, "import": cmd_import}[args.cmd](args) or 0


if __name__ == "__main__":
    sys.exit(main())
