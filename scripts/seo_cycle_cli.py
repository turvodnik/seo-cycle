"""Unified `seo-cycle` command-line entrypoint.

One command instead of dozens of `python3 scripts/*.py` invocations. The CLI is
a thin dispatcher: every subcommand shells out to the existing script with the
remaining arguments passed through untouched, so all script contracts
(exit codes, stdout data, --write conventions) stay intact.

Launcher: `bin/seo-cycle` (symlinked into ~/.local/bin by the bootstrap
scripts). Run `seo-cycle <command> --help` for the wrapped script's own help.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import time
from typing import Any

from seo_cycle_core.config import config_section, coerce_int, find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.env_profile import env_chain
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.monitoring import find_latest_snapshot, monitoring_dir
from seo_cycle_core.registry import registry_path

DEFAULT_SNAPSHOT_MAX_AGE_DAYS = 7

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS_DIR.parent

# command -> wrapped script (+ optional prepended args). Passthrough args follow.
COMMANDS: dict[str, dict[str, Any]] = {
    "init": {"script": "init-project.sh", "help": "Bootstrap a new project (wizard, config, policies)"},
    "intake": {"script": "project-intake-wizard.py", "help": "Detailed project intake wizard"},
    "journey": {"script": "project-journey.py", "help": "Current stage, blockers, and next commands"},
    "loop": {"script": "loop-runner.py", "help": "Bounded quality loop: check -> repair -> re-check"},
    "triggers": {"script": "triggers-eval.py", "help": "Phase 10 action list from a snapshot (ranked by potential)"},
    "snapshot": {"script": "snapshot-build.py", "help": "Normalize fetched data into snapshot.json"},
    "cannibalization": {"script": "cannibalization-audit.py", "help": "Query→multiple-URL conflicts report"},
    "lost-keywords": {"script": "lost-keywords.py", "help": "Lost/dropped queries between two snapshots"},
    "ice": {"script": "ice-score.py", "help": "ICE prioritization (Impact x Confidence x Ease)"},
    "attribution": {"script": "source-attribution.py", "help": "Which keyword sources actually rank (Phase 10)"},
    "secret-scan": {"script": "secret-scan.py", "help": "Scan the project tree for leaked secret values"},
    "repair": {"script": "research-package-repair.py", "help": "Run the research-package repair layer"},
    "approvals": {"script": "approval-gate.py", "prepend": ["list"], "help": "List approval tickets"},
    "approve": {"script": "approval-gate.py", "prepend": ["approve"], "help": "Approve a ticket by id"},
    "reject": {"script": "approval-gate.py", "prepend": ["reject"], "help": "Reject a ticket by id"},
    "queue": {"script": "keyword-queue.py", "help": "Keyword queue operations"},
    "db": {"script": "db-sync.py", "help": "Sync CSV/JSON artifacts into seo.db"},
    "dashboard": {"script": "monthly-dashboard.py", "help": "Monthly status dashboard"},
    "ledger": {"script": "usage-ledger.py", "help": "Token/budget usage ledger (report/check/record)"},
    "spend": {"script": "spend-guard.py", "help": "Paid service allow/approval/block report"},
    "validate": {"script": "validate-config.py", "help": "Validate seo-cycle.yaml"},
    "control-plane": {"script": "setup-control-plane.py", "help": "Full setup/readiness control plane"},
    "context": {"script": "context-pack.py", "help": "Low-token context pack for a task"},
    "notify": {"script": "notify.py", "help": "Send a Telegram notification"},
    "cycle": {"script": "cycle-state.py", "help": "Phase DAG state (init/next/show/set/gate)"},
    "forecast": {"script": "seo-forecast.py", "help": "Traffic/lead forecast from core + positions"},
    "kpi": {"script": "kpi-contract.py", "help": "KPI contract check: plan vs fact, escalation"},
    "budget": {"script": "budget-mix-planner.py", "help": "SEO+PPC budget mix by leads per unit"},
    "report": {"script": "client-report.py", "help": "White-label client report (md + HTML)"},
    "score": {"script": "scorecard.py", "help": "Self-assessment scorecards: record/show 0-10 grades"},
    "progress": {"script": "position-progress.py", "help": "Ranking progress per project or --global portfolio"},
    "pulse": {"script": "pulse.py", "help": "Daily pulse: fetch fresh positions -> snapshot -> db -> progress + alerts"},
    "auth": {"script": "auth-assistant.py", "help": "Provider logins: list | login <provider> [--global] | set VAR"},
    "web": {"script": "webapp.py", "help": "Visual agency dashboard in the browser (web --open)"},
    "crawl": {"script": "site-crawl.py", "help": "Own site crawler: --live BFS with findings"},
    "structure": {"script": "structure-map.py", "help": "Visual site-structure tree (crawl/mirror/sitemap)"},
    "intel": {"script": "serp-intel.py", "help": "SERP overlap clusters, features, entity candidates (offline)"},
    "links": {"script": "link-liveness.py", "help": "External-source liveness check (E-E-A-T rot)"},
    "repurpose": {"script": "content-repurpose.py", "help": "Draft → TG/VK/video/email skeletons"},
    "cohorts": {"script": "metrika-cohorts.py", "help": "Метрика Logs cohorts: return/conversion by first-visit week"},
    "geo-log": {"script": "geo-citation-log.py", "help": "Brand citations in AI answers: record/import/trend"},
    "feed": {"script": "woo-yml-feed.py", "help": "YML feed from WooCommerce (--live) or a products export"},
}

SYNC_ADAPTERS = {
    "wordpress": "wp-content-pull.py",
    "tilda": "tilda-content-pull.py",
    "bitrix": "bitrix-content-pull.py",
}

GATE_SCRIPTS = {
    "research-package": "research-package-quality.py",
    "outline": "page-outline-quality.py",
    "draft": "draft-quality-gate.py",
}

ADS_SCRIPTS = {
    "health": None,  # both platform health scripts
    "fetch": None,  # platform-dependent
    "analytics": "ads-analytics.py",
    "draft": "ads-draft-builder.py",
    "apply": "ads-apply.py",
}
ADS_FETCH = {"yandex_direct": "yandex-direct-fetch.py", "google_ads": "google-ads-fetch.py"}
ADS_HEALTH = ("yandex-direct-health.py", "google-ads-health.py")

RAG_SCRIPTS = {"index": "rag-index.py", "query": "rag-query.py"}

DOCTOR_STEPS = (
    ("config", "validate-config.py", []),
    ("journey", "project-journey.py", []),
    ("spend-guard", "spend-guard.py", []),
    ("usage-ledger", "usage-ledger.py", ["report"]),
    ("perplexity", "perplexity-health.py", []),
    ("notebooklm", "notebooklm-health.py", []),
    ("xmlriver", "xmlriver-health.py", []),
    ("yandex-direct", "yandex-direct-health.py", []),
    ("google-ads", "google-ads-health.py", []),
    ("merchant", "merchant-health.py", []),
    ("gbp", "gbp-health.py", []),
    ("yandex-business", "yandex-business-health.py", []),
)

log = setup_logging("cli")


def run_script(script: str, args: list[str], project: pathlib.Path) -> int:
    path = SCRIPTS_DIR / script
    if not path.exists():
        print(f"ERROR: script not found: {path}", file=sys.stderr)
        return 2
    if script.endswith(".sh"):
        command = ["bash", str(path), *args]
    else:
        command = [sys.executable, str(path), *args]
    started = time.monotonic()
    # env chain: process > project .env > ~/.seo-cycle/env.global — a global
    # login works everywhere until a project overrides it with its own account
    proc = subprocess.run(command, cwd=project, env=env_chain(project), check=False)
    log.info("dispatch %s args=%s rc=%s duration=%.1fs", script, args, proc.returncode, time.monotonic() - started)
    return proc.returncode


def newest_snapshot(project: pathlib.Path, cfg: dict[str, Any] | None = None) -> tuple[pathlib.Path | None, int | None]:
    """Newest monitoring snapshot and its age in days.

    Same resolution (`monitoring.path` config key, T-052 R3) and same
    validated pick (date-in-filename first, mtime tie-break; unrelated files
    that merely contain "snapshot" in the name are rejected — T-052 R1 / mask
    hardening) as pulse.py (writer) and the dashboard (reader) — see
    `seo_cycle_core.monitoring`.
    """
    search_dirs = [
        monitoring_dir(cfg or {}, project),
        project / "seo" / "09-monitoring",  # v1 top-level fallback
    ]
    # v1 nested per-cycle layout (historical projects)
    search_dirs.extend(project.glob("seo/cycles/*/09-monitoring"))
    latest = find_latest_snapshot(search_dirs)
    if latest is None:
        return None, None
    age_days = int((time.time() - latest.stat().st_mtime) // 86400)
    return latest, age_days


def cmd_doctor(args: list[str], project: pathlib.Path) -> int:
    """Read-only aggregated health: config, journey, spend, ledger, providers, freshness.

    Freshness threshold: `monitoring.snapshot_max_age_days` in seo-cycle.yaml
    (default 7) — snapshot older than that is ПРОСРОЧЕН and fails (exit 1).
    Also reports `agy` (Antigravity CLI) and Perplexity-key presence — both
    are declared mandatory for Phase 2 by the phase skill, so doctor must be
    able to say whether they are actually available (T-052).
    """
    cfg_path = find_config(project)
    cfg = load_yaml(cfg_path) if cfg_path else {}
    max_age = coerce_int(
        nested_get(cfg, "monitoring.snapshot_max_age_days", DEFAULT_SNAPSHOT_MAX_AGE_DAYS),
        DEFAULT_SNAPSHOT_MAX_AGE_DAYS,
        name="monitoring.snapshot_max_age_days",
    )
    results: list[tuple[str, int, str]] = []
    for label, script, prepend in DOCTOR_STEPS:
        path = SCRIPTS_DIR / script
        if not path.exists():
            results.append((label, -1, f"script not found: {script}"))
            continue
        proc = subprocess.run(
            [sys.executable, str(path), *prepend],
            cwd=project,
            env=env_chain(project),
            text=True,
            capture_output=True,
            check=False,
        )
        tail = ""
        if proc.returncode != 0:
            err_lines = [ln for ln in (proc.stderr or proc.stdout or "").strip().splitlines() if ln.strip()]
            tail = " · ".join(err_lines[-2:])[:220]
        results.append((label, proc.returncode, tail))
    print("# seo-cycle doctor\n")
    worst = 0
    for label, rc, tail in results:
        if rc == 0:
            print(f"- {label}: ok")
            continue
        # missing script is a FAILURE, not a shrug — a silently absent check hides breakage
        status = "MISSING" if rc == -1 else f"needs attention (rc={rc})"
        print(f"- {label}: {status}")
        if tail:
            print(f"    ↳ {tail}")
        worst = 1
    snap, age = newest_snapshot(project, cfg)
    if snap is None:
        print(f"- snapshot-freshness: нет снапшотов мониторинга (порог {max_age} дн.; запусти `seo-cycle pulse`)")
    elif age is not None and age >= max_age:
        print(f"- snapshot-freshness: ПРОСРОЧЕН — {age} дн., порог {max_age} ({snap.name}); данные Phase 10 неактуальны")
        worst = 1
    elif age is not None and age >= 3:
        print(f"- snapshot-freshness: warn — {age} дн., порог {max_age} ({snap.name})")
    else:
        print(f"- snapshot-freshness: ok — {age} дн., порог {max_age} ({snap.name})")
    rag_db = project / "seo" / "rag.db"
    if rag_db.exists() and rag_db.stat().st_size > 0:
        print(f"- rag-index: ok ({rag_db.stat().st_size // 1024} KB)")
    else:
        print("- rag-index: отсутствует (info; создать: `seo-cycle rag index --write`)")
    agy_path = shutil.which("agy")
    print(f"- agy: {'found (' + agy_path + ')' if agy_path else 'missing'} "
          "— обязателен для Phase 2 (Antigravity)")
    perplexity_key = bool(env_chain(project).get("PERPLEXITY_API_KEY"))
    print(f"- perplexity-key: {'present' if perplexity_key else 'missing'} "
          "— обязателен для Phase 2 (значение не проверяется, только наличие)")
    print("\nDetails: rerun any step directly, e.g. `seo-cycle spend` or `seo-cycle journey`.")
    return worst


def cmd_status(args: list[str], project: pathlib.Path) -> int:
    """Dashboard: project, snapshot age, loops/escalations, last triggers run — then journey."""
    cfg_path = find_config(project)
    if not cfg_path:
        # Проверка ДО печати шапки (T-052): иначе выводится «снапшот: нет /
        # triggers не строился» для несуществующего проекта — читается как
        # реальное состояние, а не как «конфига вообще нет».
        print(f"ERROR: seo-cycle.yaml not found in {project}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    name = config_section(cfg, "project").get("name")
    print(f"# seo-cycle status · {name or project.name}\n")
    snap, age = newest_snapshot(project, cfg)
    if snap is None:
        print("- снапшот: нет (запусти `seo-cycle pulse`)")
    else:
        marker = "ok" if (age or 0) < 3 else ("warn" if (age or 0) < 7 else "ПРОСРОЧЕН")
        print(f"- снапшот: {snap.name} · {age} дн. · {marker}")
    iterations = sorted(project.glob("seo/**/10-iterations*.md"), key=lambda p: p.stat().st_mtime)
    if iterations:
        latest_iter = iterations[-1]
        iter_age = int((time.time() - latest_iter.stat().st_mtime) // 86400)
        print(f"- triggers: {latest_iter.relative_to(project)} · {iter_age} дн.")
    else:
        print("- triggers: action list ещё не строился (`seo-cycle triggers <snapshot> --output 10-iterations.md`)")
    loops_dir = project / "seo" / "loops"
    if loops_dir.is_dir():
        escalated = [p.name for p in loops_dir.glob("*.json")
                     if "escalated" in p.read_text(encoding="utf-8", errors="replace")[:2000]]
        if escalated:
            print(f"- loops: ⚠ эскалации ждут человека: {', '.join(sorted(escalated)[:5])}")
    print()
    sys.stdout.flush()  # дочерний journey пишет в fd напрямую — без flush его вывод обгонит наш
    return run_script("project-journey.py", args, project)


MENU_ACTIONS: tuple[tuple[str, str, list[str]], ...] = (
    ("Статус проекта (journey)", "project-journey.py", []),
    ("Прогресс позиций", "position-progress.py", []),
    ("Прогресс по всем проектам (портфель)", "position-progress.py", ["--global"]),
    ("Месячный дашборд", "monthly-dashboard.py", []),
    ("Approvals: что ждёт решения", "approval-gate.py", ["list"]),
    ("Самооценки инструментов", "scorecard.py", ["show"]),
    ("Doctor: health всех провайдеров", None, []),  # special-cased below
    ("Auth: кто настроен и откуда", "auth-assistant.py", ["list"]),
)


def load_registry_projects() -> list[dict[str, Any]]:
    registry = registry_path(SKILL_ROOT)
    if not registry.exists():
        return []
    projects = (load_yaml(registry).get("projects") or [])
    return [item for item in projects if isinstance(item, dict) and item.get("path")]


def pick_project(default: pathlib.Path) -> pathlib.Path:
    """Choose a project: current dir if it is one, otherwise from the registry."""
    if find_config(default):
        return default
    projects = load_registry_projects()
    if not projects:
        print(f"Проект не найден в {default} и реестр пуст — запустите из папки проекта.", file=sys.stderr)
        return default
    print("\nПроекты из реестра:")
    for index, item in enumerate(projects, 1):
        print(f"  {index}. {item.get('name', '?')} — {item['path']} [{item.get('status', 'active')}]")
    choice = input("Номер проекта [1]: ").strip() or "1"
    try:
        selected = projects[int(choice) - 1]
        return pathlib.Path(str(selected["path"])).expanduser()
    except (ValueError, IndexError):
        print("Не понял номер — остаюсь в текущей папке.", file=sys.stderr)
        return default


def cmd_menu(project: pathlib.Path) -> int:
    """Interactive menu — the double-click entrypoint for non-terminal users."""
    if not sys.stdin.isatty():
        print("menu требует интерактивный терминал; используйте подкоманды seo-cycle напрямую.", file=sys.stderr)
        return 2
    project = pick_project(project)
    while True:
        name = config_section(load_yaml(find_config(project)), "project").get("name") if find_config(project) else None
        print(f"\n=== seo-cycle · {name or project} ===")
        for index, (title, _, _) in enumerate(MENU_ACTIONS, 1):
            print(f"  {index}. {title}")
        print("  p. Сменить проект    0. Выход")
        choice = input("Выбор: ").strip().lower()
        if choice in {"0", "q", "exit"}:
            return 0
        if choice == "p":
            project = pick_project(project)
            continue
        try:
            title, script, extra = MENU_ACTIONS[int(choice) - 1]
        except (ValueError, IndexError):
            continue
        print(f"\n--- {title} ---\n")
        if script is None:
            cmd_doctor([], project)
        else:
            run_script(script, extra, project)
        input("\n[Enter — в меню] ")


def cmd_run(args: list[str], project: pathlib.Path) -> int:
    if not args:
        print("usage: seo-cycle run monthly [...] | run script <name> [...] | run <task words>", file=sys.stderr)
        return 2
    head, *rest = args
    if head == "monthly":
        return run_script("monthly-runner.sh", rest, project)
    if head == "script":
        if not rest:
            print("usage: seo-cycle run script <name> [args...]", file=sys.stderr)
            return 2
        name = rest[0]
        if not name.endswith((".py", ".sh")):
            name += ".py"
        return run_script(name, rest[1:], project)
    task = " ".join(args)
    return run_script("task-router.py", ["--task", task, "--write"], project)


def cmd_gate(args: list[str], project: pathlib.Path) -> int:
    if not args or args[0] not in GATE_SCRIPTS:
        print(f"usage: seo-cycle gate {{{'|'.join(GATE_SCRIPTS)}}} [args...]", file=sys.stderr)
        return 2
    return run_script(GATE_SCRIPTS[args[0]], args[1:], project)


def cmd_ads(args: list[str], project: pathlib.Path) -> int:
    if not args or args[0] not in ADS_SCRIPTS:
        print("usage: seo-cycle ads {health|fetch|analytics|draft|apply} [args...]\n"
              "  fetch: --platform yandex_direct|google_ads (default: yandex_direct)", file=sys.stderr)
        return 2
    sub, *rest = args
    if sub == "health":
        worst = 0
        for script in ADS_HEALTH:
            worst = max(worst, run_script(script, rest, project))
        return worst
    if sub == "fetch":
        platform = "yandex_direct"
        if "--platform" in rest:
            index = rest.index("--platform")
            platform = rest[index + 1] if index + 1 < len(rest) else platform
            rest = rest[:index] + rest[index + 2:]
        script = ADS_FETCH.get(platform)
        if not script:
            print(f"ERROR: unknown platform `{platform}`", file=sys.stderr)
            return 2
        return run_script(script, rest, project)
    return run_script(ADS_SCRIPTS[sub], rest, project)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seo-cycle",
        description="Unified entrypoint for the seo-cycle orchestrator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=command_overview(),
    )
    parser.add_argument("--project", help="Project directory (default: current directory)")
    parser.add_argument("--version", action="store_true", help="Print skill version and exit")
    parser.add_argument("command", nargs="?", help="Subcommand (see list below)")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to the wrapped script")
    return parser


def command_overview() -> str:
    lines = ["commands:"]
    for name, spec in sorted(COMMANDS.items()):
        lines.append(f"  {name:<14} {spec['help']}")
    lines.extend(
        [
            "  gate           Quality gates: gate research-package|outline|draft [...]",
            "  ads            Paid ads: ads health|fetch|analytics|draft|apply [...]",
            "  rag            Local RAG: rag index [--write|--global] | rag query \"<вопрос>\" [...]",
            "  sync           Site→local mirror via the publishing.cms adapter (wordpress|tilda|bitrix)",
            "  run            run monthly [...] | run script <name> [...] | run <task words>",
            "  status         Dashboard: snapshot age, triggers, escalations + journey"
            " (exit 2 if seo-cycle.yaml is missing — no header printed)",
            "  resume         Continue an interrupted quality loop (= loop ... --resume)",
            "  doctor         Read-only aggregated health: providers, agy/perplexity-key presence,"
            " snapshot freshness (threshold: monitoring.snapshot_max_age_days in seo-cycle.yaml,"
            " default 7 days). Exit 1 on a missing check or a snapshot past the threshold.",
            "  menu           Interactive menu (double-click entrypoint; picks a project from the registry)",
            "  version        Print skill version",
            "",
            "Every command forwards remaining args to the wrapped script:",
            "  seo-cycle loop research-package seo/research-package",
            "  seo-cycle gate draft <draft.md> --outline <outline.json> --write",
            "  seo-cycle approve <ticket-id>",
        ]
    )
    return "\n".join(lines)


def resolve_project(raw: str | None) -> pathlib.Path:
    project = pathlib.Path(raw).expanduser().resolve() if raw else pathlib.Path.cwd()
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}", file=sys.stderr)
        raise SystemExit(2)
    return project


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version or args.command == "version":
        print((SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip())
        return 0
    if not args.command:
        parser.print_help()
        return 0

    project = resolve_project(args.project)
    global log
    cfg_path = find_config(project)
    if cfg_path:
        log = setup_logging("cli", project_root_for(cfg_path), load_yaml(cfg_path))

    passthrough = list(args.args)
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]

    if "--project" in passthrough:
        print("⚠ `--project` указан после подкоманды и уйдёт во вложенный скрипт. "
              "Глобальный выбор проекта: seo-cycle --project DIR <command> ...", file=sys.stderr)

    if args.command == "doctor":
        return cmd_doctor(passthrough, project)
    if args.command == "status":
        return cmd_status(passthrough, project)
    if args.command == "resume":
        if not passthrough:
            print("usage: seo-cycle resume <loop-target> <path> [...] (= loop ... --resume)", file=sys.stderr)
            return 2
        extra = [] if "--resume" in passthrough else ["--resume"]
        return run_script("loop-runner.py", [*passthrough, *extra], project)
    if args.command == "menu":
        return cmd_menu(project)
    if args.command == "run":
        return cmd_run(passthrough, project)
    if args.command == "gate":
        return cmd_gate(passthrough, project)
    if args.command == "ads":
        return cmd_ads(passthrough, project)
    if args.command == "sync":
        cms = "wordpress"
        cfg_for_sync = find_config(project)
        if cfg_for_sync:
            cms = str(config_section(load_yaml(cfg_for_sync), "publishing").get("cms") or "wordpress")
        script = SYNC_ADAPTERS.get(cms)
        if not script:
            print(f"ERROR: no sync adapter for publishing.cms={cms!r}"
                  f" (supported: {', '.join(SYNC_ADAPTERS)})", file=sys.stderr)
            return 2
        return run_script(script, passthrough, project)
    if args.command == "rag":
        if not passthrough or passthrough[0] not in RAG_SCRIPTS:
            print("usage: seo-cycle rag {index|query} [args...]", file=sys.stderr)
            return 2
        return run_script(RAG_SCRIPTS[passthrough[0]], passthrough[1:], project)
    spec = COMMANDS.get(args.command)
    if not spec:
        print(f"ERROR: unknown command `{args.command}`. Run `seo-cycle --help`.", file=sys.stderr)
        return 2
    return run_script(spec["script"], [*spec.get("prepend", []), *passthrough], project)


if __name__ == "__main__":
    raise SystemExit(main())
