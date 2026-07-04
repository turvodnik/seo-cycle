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
import subprocess
import sys
import time
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for
from seo_cycle_core.logging_setup import setup_logging

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS_DIR.parent

# command -> wrapped script (+ optional prepended args). Passthrough args follow.
COMMANDS: dict[str, dict[str, Any]] = {
    "init": {"script": "init-project.sh", "help": "Bootstrap a new project (wizard, config, policies)"},
    "intake": {"script": "project-intake-wizard.py", "help": "Detailed project intake wizard"},
    "journey": {"script": "project-journey.py", "help": "Current stage, blockers, and next commands"},
    "status": {"script": "project-journey.py", "help": "Alias for journey"},
    "loop": {"script": "loop-runner.py", "help": "Bounded quality loop: check -> repair -> re-check"},
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
    proc = subprocess.run(command, cwd=project, check=False)
    log.info("dispatch %s args=%s rc=%s duration=%.1fs", script, args, proc.returncode, time.monotonic() - started)
    return proc.returncode


def cmd_doctor(args: list[str], project: pathlib.Path) -> int:
    """Read-only aggregated health: config, journey, spend, ledger, providers."""
    results: list[tuple[str, int]] = []
    for label, script, prepend in DOCTOR_STEPS:
        path = SCRIPTS_DIR / script
        if not path.exists():
            results.append((label, -1))
            continue
        proc = subprocess.run(
            [sys.executable, str(path), *prepend],
            cwd=project,
            text=True,
            capture_output=True,
            check=False,
        )
        results.append((label, proc.returncode))
    print("# seo-cycle doctor\n")
    worst = 0
    for label, rc in results:
        status = "ok" if rc == 0 else "missing" if rc == -1 else f"needs attention (rc={rc})"
        print(f"- {label}: {status}")
        worst = max(worst, 0 if rc <= 0 else 1)
    print("\nDetails: rerun any step directly, e.g. `seo-cycle spend` or `seo-cycle journey`.")
    return worst


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
            "  run            run monthly [...] | run script <name> [...] | run <task words>",
            "  doctor         Read-only aggregated health check",
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

    if args.command == "doctor":
        return cmd_doctor(passthrough, project)
    if args.command == "run":
        return cmd_run(passthrough, project)
    if args.command == "gate":
        return cmd_gate(passthrough, project)
    if args.command == "ads":
        return cmd_ads(passthrough, project)
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
