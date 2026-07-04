#!/usr/bin/env python3
"""Record and show 0-10 self-assessment scorecards for tool runs.

Every meaningful task run gets a grade so progress is visible in the journey,
dashboards, and chat. Quality-loop runs record automatically; agents record
their own grade after finishing any other task:

  python3 scripts/scorecard.py record --tool draft-writing --score 8.5 \
      --done "статья 1800 слов, FAQ, schema" --missing "нет 2 внутренних ссылок"
  python3 scripts/scorecard.py show [--tool draft-writing] [--format json]

Score can be derived from a findings JSON instead of --score:
  python3 scripts/scorecard.py record --tool gate --findings-json report.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from seo_cycle_core.config import find_config, project_root_for
from seo_cycle_core.scorecard import (
    clamp_score,
    load_history,
    load_latest,
    render_scorecards_markdown,
    score_badge,
    score_from_findings,
    write_scorecard,
)


def resolve_root() -> pathlib.Path | None:
    cfg_path = find_config(pathlib.Path.cwd())
    return project_root_for(cfg_path) if cfg_path else None


def cmd_record(args: argparse.Namespace, project_root: pathlib.Path) -> int:
    score = args.score
    if score is None and args.findings_json:
        try:
            report = json.loads(pathlib.Path(args.findings_json).read_text(encoding="utf-8"))
            findings = report.get("findings", []) if isinstance(report, dict) else []
            score = score_from_findings(findings)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot read findings JSON: {exc}", file=sys.stderr)
            return 2
    if score is None:
        print("ERROR: pass --score 0..10 or --findings-json <report.json>", file=sys.stderr)
        return 2
    entry = write_scorecard(
        project_root,
        args.tool,
        clamp_score(score),
        status=args.status,
        done=args.done,
        missing=args.missing,
        notes=args.notes or "",
    )
    if args.format == "json":
        print(json.dumps(entry, ensure_ascii=False, indent=2))
    else:
        badge = score_badge(entry["score"])
        print(f"{badge} {entry['tool']}: {entry['score']}/10 ({entry['status']})")
        for item in entry["done"]:
            print(f"  + {item}")
        for item in entry["missing"]:
            print(f"  - {item}")
    return 0


def cmd_show(args: argparse.Namespace, project_root: pathlib.Path) -> int:
    if args.tool:
        history = load_history(project_root, args.tool, args.limit)
        if args.format == "json":
            print(json.dumps(history, ensure_ascii=False, indent=2))
            return 0
        if not history:
            print(f"Нет оценок для инструмента {args.tool}.")
            return 0
        print(f"# Оценки: {args.tool}\n")
        for entry in reversed(history):
            print(f"- {entry.get('at', '')[:16]} {score_badge(clamp_score(entry.get('score')))} "
                  f"{clamp_score(entry.get('score'))}/10 ({entry.get('status')}) {entry.get('notes', '')}")
            for item in entry.get("missing", []):
                print(f"    - не хватает: {item}")
        return 0
    latest = load_latest(project_root)
    if args.format == "json":
        print(json.dumps(latest, ensure_ascii=False, indent=2))
        return 0
    print("# Самооценки инструментов (последний запуск каждого)\n")
    print(render_scorecards_markdown(latest, args.limit), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="Record a scorecard entry")
    record.add_argument("--tool", required=True, help="Tool/task name, e.g. draft-writing")
    record.add_argument("--score", type=float, help="Grade 0..10")
    record.add_argument("--findings-json", help="Derive the score from a quality report JSON")
    record.add_argument("--status", choices=("done", "partial", "failed"), default="done")
    record.add_argument("--done", action="append", default=[], help="What was accomplished (repeatable)")
    record.add_argument("--missing", action="append", default=[], help="What is still missing (repeatable)")
    record.add_argument("--notes", help="Free-form context")
    record.add_argument("--format", choices=("md", "json"), default="md")

    show = sub.add_parser("show", help="Show latest scorecards or one tool's history")
    show.add_argument("--tool", help="Show history for one tool")
    show.add_argument("--limit", type=int, default=20)
    show.add_argument("--format", choices=("md", "json"), default="md")

    args = parser.parse_args(argv)
    project_root = resolve_root()
    if not project_root:
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    if args.command == "record":
        return cmd_record(args, project_root)
    return cmd_show(args, project_root)


if __name__ == "__main__":
    raise SystemExit(main())
