#!/usr/bin/env python3
"""Add curated official MCP servers to this project's .codex/config.toml.

Project-local by design (same philosophy as project-mcp-config.py): nothing is
installed globally, secrets stay in the project's .env, and the managed block
uses its own markers so it never collides with the WordPress MCP block.

Curated presets (see docs/ecosystem-integrations.md for the why):
  chrome-devtools    npx chrome-devtools-mcp — performance traces/debugging
  perplexity         npx server-perplexity-ask — Sonar API search (needs PERPLEXITY_API_KEY)
  google-analytics   pipx run analytics-mcp — official GA4 MCP (needs GOOGLE_APPLICATION_CREDENTIALS)

Usage:
  python3 scripts/mcp-preset.py --list
  python3 scripts/mcp-preset.py --enable chrome-devtools --enable perplexity --write
  python3 scripts/mcp-preset.py --disable perplexity --write
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, project_root_for, write_text

BEGIN = "# BEGIN seo-cycle managed ecosystem MCP"
END = "# END seo-cycle managed ecosystem MCP"

PRESETS: dict[str, dict[str, Any]] = {
    "chrome-devtools": {
        "why": "official Chrome DevTools MCP: perf traces, network/console debugging for CWV work",
        "docs": "https://github.com/ChromeDevTools/chrome-devtools-mcp",
        "command": "npx",
        "args": ["-y", "chrome-devtools-mcp@latest"],
        "env_required": [],
    },
    "perplexity": {
        "why": "official Perplexity Sonar MCP: API-mode research alternative to the browser collector",
        "docs": "https://github.com/perplexityai/modelcontextprotocol",
        "command": "npx",
        "args": ["-y", "server-perplexity-ask"],
        "env_required": ["PERPLEXITY_API_KEY"],
    },
    "google-analytics": {
        "why": "official GA4 MCP: conversational property queries beyond ga4-fetch snapshots",
        "docs": "https://github.com/googleanalytics/google-analytics-mcp",
        "command": "pipx",
        "args": ["run", "analytics-mcp"],
        "env_required": ["GOOGLE_APPLICATION_CREDENTIALS"],
    },
}


def state_path(project_root: pathlib.Path) -> pathlib.Path:
    return project_root / ".codex" / "mcp-presets.json"


def load_enabled(project_root: pathlib.Path) -> list[str]:
    try:
        data = json.loads(state_path(project_root).read_text(encoding="utf-8"))
        return [name for name in data.get("enabled", []) if name in PRESETS]
    except (OSError, json.JSONDecodeError):
        return []


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def preset_block(project_root: pathlib.Path, name: str) -> list[str]:
    preset = PRESETS[name]
    guards = "".join(
        f': "${{{env}:?{env} missing in project .env}}"; ' for env in preset["env_required"]
    )
    inner = " ".join(f"{preset['command']}" if index == 0 else part
                     for index, part in enumerate([preset["command"], *preset["args"]]))
    command = (f"cd {shell_quote(str(project_root))} && "
               "set -a; [ -f .env ] && . ./.env; set +a; "
               f"{guards}exec {inner}")
    server = f"seo-cycle-{name}"
    return [
        f"# {name}: {preset['why']}",
        f"# docs: {preset['docs']}",
        f"[mcp_servers.{server}]",
        'command = "bash"',
        f"args = [\"-lc\", {toml_string(command)}]",
        "startup_timeout_sec = 45",
        "",
    ]


def managed_block(project_root: pathlib.Path, enabled: list[str]) -> str:
    lines = [BEGIN,
             "# Curated ecosystem MCP servers (seo-cycle mcp-preset.py).",
             "# Verify launch commands against each project's README if a server fails to start.",
             ""]
    for name in enabled:
        lines.extend(preset_block(project_root, name))
    lines.append(END)
    return "\n".join(lines) + "\n"


def replace_managed_block(existing: str, block: str) -> str:
    if BEGIN in existing and END in existing:
        head = existing.split(BEGIN)[0].rstrip()
        tail = existing.split(END, 1)[1].lstrip("\n")
        parts = [part for part in (head, block.rstrip(), tail.rstrip()) if part]
        return "\n\n".join(parts) + "\n"
    base = existing.rstrip()
    return (base + "\n\n" if base else "") + block


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--list", action="store_true", help="Show presets and their status")
    parser.add_argument("--enable", action="append", default=[], choices=sorted(PRESETS.keys()))
    parser.add_argument("--disable", action="append", default=[], choices=sorted(PRESETS.keys()))
    parser.add_argument("--write", action="store_true", help="Update .codex/config.toml managed block")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    project_root = project_root_for(cfg_path)

    enabled = load_enabled(project_root)
    for name in args.enable:
        if name not in enabled:
            enabled.append(name)
    enabled = [name for name in enabled if name not in set(args.disable)]

    if args.list or not (args.enable or args.disable):
        print("Curated MCP presets (project-local, secrets from .env):\n")
        for name, preset in PRESETS.items():
            status = "enabled" if name in enabled else "off"
            env = f" · env: {', '.join(preset['env_required'])}" if preset["env_required"] else ""
            print(f"  [{status:^7}] {name:<17} {preset['why']}{env}")
        print("\nEnable: python3 scripts/mcp-preset.py --enable <name> --write")
        if not (args.enable or args.disable):
            return 0

    if not args.write:
        print("\nDry-run (no --write). Managed block preview:\n", file=sys.stderr)
        print(managed_block(project_root, enabled))
        return 0

    toml_path = project_root / ".codex" / "config.toml"
    existing = toml_path.read_text(encoding="utf-8") if toml_path.exists() else ""
    write_text(toml_path, replace_managed_block(existing, managed_block(project_root, enabled)))
    write_text(state_path(project_root), json.dumps({"enabled": enabled}, ensure_ascii=False, indent=2) + "\n")
    print(f"✓ {toml_path}: ecosystem MCP block updated (enabled: {', '.join(enabled) or 'none'})",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
