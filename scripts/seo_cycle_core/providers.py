"""Provider health checks for optional SEO evidence sources."""

from __future__ import annotations

import os
import pathlib
import re
from typing import Any


DEFAULT_PERPLEXITY_APP_PATHS = (
    pathlib.Path("/Applications/Perplexity.app"),
    pathlib.Path.home() / "Applications/Perplexity.app",
)


def perplexity_health(
    *,
    app_paths: list[pathlib.Path] | tuple[pathlib.Path, ...] | None = None,
    browser_available: bool = False,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env if env is not None else os.environ
    paths = list(app_paths or DEFAULT_PERPLEXITY_APP_PATHS)
    app_detected = any(path.exists() for path in paths)
    api_key_present = bool(env.get("PERPLEXITY_API_KEY"))
    modes = ["manual_browser"]
    if app_detected or browser_available:
        modes.insert(0, "persistent_browser")
    if app_detected:
        modes.append("app_detected")
    if api_key_present:
        modes.append("api_optional")
    status = "available" if app_detected or browser_available or api_key_present else "degraded"
    return {
        "provider": "perplexity",
        "status": status,
        "app_detected": app_detected,
        "browser_available": browser_available,
        "api_optional": api_key_present,
        "preferred_mode": modes[0],
        "fallback_mode": "manual_browser",
        "modes": modes,
        "stores_password": False,
    }


def notebooklm_health(
    config_path: pathlib.Path,
    *,
    tools_exposed: bool = False,
    notebook_url: str | None = None,
) -> dict[str, Any]:
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    configured = "[mcp_servers.notebooklm]" in text
    disabled_tools: list[str] = []
    match = re.search(r'NOTEBOOKLM_DISABLED_TOOLS\s*=\s*"([^"]*)"', text)
    if match:
        disabled_tools = [item.strip() for item in match.group(1).split(",") if item.strip()]
    if configured and tools_exposed:
        status = "available"
        access_mode = "mcp"
    elif configured:
        status = "fallback_required"
        access_mode = "browser_export"
    else:
        status = "unavailable"
        access_mode = "manual_export"
    return {
        "provider": "notebooklm",
        "configured": configured,
        "tools_exposed": tools_exposed,
        "status": status,
        "access_mode": access_mode,
        "disabled_tools": disabled_tools,
        "notebook_url": notebook_url,
        "ranking_signal": False,
        "allowed_use": "curated expert evidence with citations/source excerpts",
    }

