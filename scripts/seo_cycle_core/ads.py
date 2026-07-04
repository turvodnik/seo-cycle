"""Shared helpers for the guarded Google Ads / Yandex Direct layer.

Contract mirrors the XMLRiver guarded provider: health checks never touch the
network, fetch scripts default to cache/--input-file and require --live plus a
usage-ledger preflight for real API calls, apply requires an approved ticket
plus --live --allow-write, and secrets are never printed or stored.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
from typing import Any

from .config import nested_get, write_text

PLATFORMS = ("yandex_direct", "google_ads")

ENV_NAMES = {
    "yandex_direct": ["YANDEX_DIRECT_TOKEN"],
    "google_ads": [
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
        "GOOGLE_ADS_CUSTOMER_ID",
    ],
}
OPTIONAL_ENV_NAMES = {
    "yandex_direct": ["YANDEX_DIRECT_CLIENT_LOGIN"],
    "google_ads": ["GOOGLE_ADS_LOGIN_CUSTOMER_ID", "GOOGLE_ADS_API_VERSION"],
}

ADS_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "primary_platform": "auto",
    "policy": "approval_only",  # report_only | approval_only
    "cache_ttl_hours": 24,
    "fetch": {"max_requests_per_run": 200},
    "yandex_direct": {"enabled": False, "sandbox": False, "client_login": ""},
    "google_ads": {"enabled": False, "apply_enabled": False, "customer_id": ""},
    "analytics": {"top_position_threshold": 3, "wasted_spend_min_cost": 300},
    "apply": {"max_changes_per_run": 20, "max_daily_budget": 0},
}


def merge_defaults(defaults: dict[str, Any], override: Any) -> dict[str, Any]:
    merged = dict(defaults)
    if isinstance(override, dict):
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = merge_defaults(merged[key], value)
            else:
                merged[key] = value
    return merged


def ads_config(cfg: dict[str, Any]) -> dict[str, Any]:
    return merge_defaults(ADS_DEFAULTS, cfg.get("ads"))


def primary_platform(cfg: dict[str, Any]) -> str:
    ads = ads_config(cfg)
    explicit = str(ads.get("primary_platform") or "auto")
    if explicit in PLATFORMS:
        return explicit
    region = str(cfg.get("region_profile") or "").lower()
    return "yandex_direct" if region == "ru" else "google_ads"


def region_limited(cfg: dict[str, Any], platform: str) -> bool:
    return platform == "google_ads" and str(cfg.get("region_profile") or "").lower() == "ru"


def env_status(platform: str) -> dict[str, Any]:
    required = ENV_NAMES.get(platform, [])
    missing = [name for name in required if not os.environ.get(name)]
    return {"required": required, "optional": OPTIONAL_ENV_NAMES.get(platform, []),
            "missing": missing, "present": not missing}


def platform_health_status(cfg: dict[str, Any], platform: str) -> str:
    status = env_status(platform)
    if status["present"]:
        return "available"
    return "region_limited" if region_limited(cfg, platform) else "needs_credentials"


def raw_dir(project_root: pathlib.Path, platform: str) -> pathlib.Path:
    return project_root / "seo" / "ads" / "raw" / platform


def save_raw(project_root: pathlib.Path, platform: str, report: str, payload: Any) -> dict[str, pathlib.Path]:
    directory = raw_dir(project_root, platform)
    today = dt.date.today().isoformat()
    dated = directory / f"{today}-{report}.json"
    latest = directory / f"{report}-latest.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    write_text(dated, text)
    write_text(latest, text)
    return {"dated": dated, "latest": latest}


def load_latest_raw(project_root: pathlib.Path, platform: str, report: str,
                    ttl_hours: float | None = None) -> Any:
    path = raw_dir(project_root, platform) / f"{report}-latest.json"
    if not path.exists():
        return None
    if ttl_hours is not None:
        age_hours = (dt.datetime.now().timestamp() - path.stat().st_mtime) / 3600
        if age_hours > ttl_hours:
            return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def ledger_preflight(project_root: pathlib.Path, service: str, *, requests: int = 0,
                     usd: float = 0.0, category: str = "ads") -> tuple[bool, str]:
    """Run `usage-ledger.py check --fail-on-block`; ok=True when spend is allowed."""
    script = pathlib.Path(__file__).resolve().parent.parent / "usage-ledger.py"
    command = [sys.executable, str(script), "check", "--service", service, "--category", category,
               "--fail-on-block"]
    if requests:
        command += ["--requests", str(requests)]
    if usd:
        command += ["--usd", str(usd)]
    proc = subprocess.run(command, cwd=project_root, text=True, capture_output=True, check=False)
    tail = (proc.stdout or proc.stderr).strip().splitlines()
    return proc.returncode == 0, tail[-1] if tail else f"rc={proc.returncode}"


def ledger_record(project_root: pathlib.Path, service: str, *, requests: int = 0,
                  usd: float = 0.0, note: str = "", category: str = "ads") -> None:
    script = pathlib.Path(__file__).resolve().parent.parent / "usage-ledger.py"
    command = [sys.executable, str(script), "record", "--service", service, "--category", category]
    if requests:
        command += ["--requests", str(requests)]
    if usd:
        command += ["--usd", str(usd)]
    if note:
        command += ["--note", note]
    subprocess.run(command, cwd=project_root, text=True, capture_output=True, check=False)


def redact(text: str) -> str:
    """Replace configured ads secret values with *** in arbitrary output."""
    result = text
    for names in (*ENV_NAMES.values(), *OPTIONAL_ENV_NAMES.values()):
        for name in names:
            value = os.environ.get(name)
            if value and len(value) > 3:
                result = result.replace(value, "***")
    return result


def summary_paths(cfg: dict[str, Any], project_root: pathlib.Path, platform: str) -> dict[str, pathlib.Path]:
    slug = platform.replace("_", "-")
    base = project_root / "seo" / "ads"
    return {
        "markdown": base / f"{slug}-summary.md",
        "json": base / f"{slug}-summary.json",
        "latest_markdown": base / f"latest-{slug}-summary.md",
        "latest_json": base / f"latest-{slug}-summary.json",
    }


def require_enabled(cfg: dict[str, Any], platform: str | None = None) -> str | None:
    """Return an error string when the ads layer (or a platform) is disabled."""
    ads = ads_config(cfg)
    if not ads.get("enabled"):
        return ("ads layer is disabled: set `ads.enabled: true` (and per-platform enabled) "
                "in seo-cycle.yaml after reviewing spend policy")
    if platform and not nested_get(ads, f"{platform}.enabled", False):
        return f"platform {platform} is disabled: set `ads.{platform}.enabled: true` in seo-cycle.yaml"
    return None
