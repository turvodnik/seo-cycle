#!/usr/bin/env python3
"""Append project decisions to the SEO wiki.

Use this after any content update, audit decision, or publication decision so
the wiki remains the project source of truth instead of scattered chat memory.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

from wiki_common import WIKI_ROOT, ensure_wiki_tree, slugify, utc_now, write_jsonl


def split_values(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        result.extend(part.strip() for part in value.split(",") if part.strip())
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, help="URL, slug, category, brand, or task id")
    parser.add_argument("--action", required=True, help="planned|updated|published|skipped|blocked|rolled_back|audited")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--changes", action="append", default=[])
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--risk", action="append", default=[])
    parser.add_argument("--next-step", action="append", default=[])
    parser.add_argument("--status", default="recorded")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    ensure_wiki_tree()
    now = utc_now()
    item: dict[str, Any] = {
        "id": f"decision-{now}-{slugify(args.target)[:80]}",
        "recorded_at": now,
        "target": args.target,
        "action": args.action,
        "reason": args.reason,
        "changes": split_values(args.changes),
        "sources": split_values(args.source),
        "risks": split_values(args.risk),
        "next_steps": split_values(args.next_step),
        "status": args.status,
    }
    print(json.dumps(item, ensure_ascii=False, indent=2))
    if not args.write:
        return 0

    log_path = WIKI_ROOT / "decisions" / "decision-log.jsonl"
    existing = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.append(json.loads(line))
    existing.append(item)
    write_jsonl(log_path, existing)

    safe = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ_-]+", "-", item["id"]).strip("-")[:140]
    md = WIKI_ROOT / "decisions" / f"{safe}.md"
    md.write_text(
        "\n".join(
            [
                f"# {args.action}: {args.target}",
                "",
                f"- Recorded: `{now}`",
                f"- Status: `{args.status}`",
                "",
                "## Reason",
                args.reason,
                "",
                "## Changes",
                *(f"- {value}" for value in item["changes"]),
                "" if item["changes"] else "- нет",
                "",
                "## Sources",
                *(f"- {value}" for value in item["sources"]),
                "" if item["sources"] else "- нет",
                "",
                "## Risks",
                *(f"- {value}" for value in item["risks"]),
                "" if item["risks"] else "- нет",
                "",
                "## Next Steps",
                *(f"- {value}" for value in item["next_steps"]),
                "" if item["next_steps"] else "- нет",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
