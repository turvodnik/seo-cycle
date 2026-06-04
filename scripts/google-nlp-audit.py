#!/usr/bin/env python3
"""Guarded Google Cloud Natural Language audits with project-local caching.

This script is intentionally conservative:
- reads `.env`, `seo/.env`, and `seo/entities/google-nlp-policy.yaml` from a project;
- skips cached results by default;
- enforces monthly unit caps before calling Google;
- never publishes or edits site content.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import requests
import yaml
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request as AuthRequest
from google.oauth2 import service_account


DEFAULT_POLICY_REL = "seo/entities/google-nlp-policy.yaml"
DEFAULT_ENV_RELS = (".env", "seo/.env")

FEATURE_ENDPOINTS = {
    "analyzeEntities": ("v2", "https://language.googleapis.com/v2/documents:analyzeEntities"),
    "classifyText": ("v2", "https://language.googleapis.com/v2/documents:classifyText"),
    "analyzeSyntax": ("v1", "https://language.googleapis.com/v1/documents:analyzeSyntax"),
    "moderateText": ("v1", "https://language.googleapis.com/v1/documents:moderateText"),
    "analyzeSentiment": ("v2", "https://language.googleapis.com/v2/documents:analyzeSentiment"),
    "analyzeEntitySentiment": (
        "v1beta2",
        "https://language.googleapis.com/v1beta2/documents:analyzeEntitySentiment",
    ),
}

FEATURE_ENV_TOKENS = {
    "analyzeEntities": "ENTITY",
    "classifyText": "CLASSIFICATION",
    "analyzeSyntax": "SYNTAX",
    "moderateText": "MODERATION",
    "analyzeSentiment": "SENTIMENT",
    "analyzeEntitySentiment": "ENTITY_SENTIMENT",
}

UNIT_SIZE = {
    "moderateText": 100,
}


class GuardError(RuntimeError):
    """Raised when a configured cost or policy guard blocks a call."""


def project_path(project_root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            values[key] = value
    return values


def load_config(project_root: Path, extra_env_files: list[str] | None = None) -> dict[str, str]:
    config: dict[str, str] = {}
    for rel in DEFAULT_ENV_RELS:
        config.update(parse_env_file(project_path(project_root, rel)))
    for raw_path in extra_env_files or []:
        config.update(parse_env_file(project_path(project_root, raw_path)))
    config.update(os.environ)
    return config


def load_policy(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def setdefault_str(config: dict[str, str], key: str, value: Any) -> None:
    if value is not None and key not in config:
        config[key] = str(value)


def apply_policy_defaults(config: dict[str, str], policy: dict[str, Any]) -> dict[str, str]:
    next_config = dict(config)

    cache = policy.get("cache", {}) if isinstance(policy.get("cache"), dict) else {}
    selection = policy.get("selection", {}) if isinstance(policy.get("selection"), dict) else {}
    budget = policy.get("budget", {}) if isinstance(policy.get("budget"), dict) else {}

    setdefault_str(next_config, "GOOGLE_NLP_CACHE_DIR", cache.get("dir"))
    setdefault_str(next_config, "GOOGLE_NLP_CACHE_DAYS", cache.get("ttl_days"))
    setdefault_str(next_config, "GOOGLE_NLP_MAX_URLS_PER_RUN", selection.get("max_urls_per_run"))
    setdefault_str(next_config, "GOOGLE_NLP_MAX_CHARS_PER_URL", selection.get("max_cleaned_chars_per_url"))
    setdefault_str(next_config, "GOOGLE_NLP_CLOUD_BUDGET_USD", budget.get("monthly_budget_alert_usd"))

    feature_defaults: list[str] = []
    features = policy.get("features", {}) if isinstance(policy.get("features"), dict) else {}
    for feature, feature_policy in features.items():
        if feature not in FEATURE_ENV_TOKENS or not isinstance(feature_policy, dict):
            continue
        token = FEATURE_ENV_TOKENS[feature]
        setdefault_str(next_config, f"GOOGLE_NLP_FREE_{token}_UNITS_PER_MONTH", feature_policy.get("free_units_per_month"))
        setdefault_str(next_config, f"GOOGLE_NLP_PAID_{token}_UNITS_CAP_PER_MONTH", feature_policy.get("paid_units_cap_per_month"))
        setdefault_str(next_config, f"GOOGLE_NLP_TOTAL_{token}_UNITS_CAP_PER_MONTH", feature_policy.get("total_units_cap_per_month"))
        if feature_policy.get("default"):
            feature_defaults.append(feature)

    if feature_defaults and "GOOGLE_NLP_DEFAULT_FEATURES" not in next_config:
        next_config["GOOGLE_NLP_DEFAULT_FEATURES"] = ",".join(feature_defaults)

    return next_config


def csv_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def policy_disabled_for_language(policy: dict[str, Any], language: str) -> set[str]:
    disabled: set[str] = set()
    features = policy.get("features", {}) if isinstance(policy.get("features"), dict) else {}
    for feature, feature_policy in features.items():
        if not isinstance(feature_policy, dict):
            continue
        disabled_languages = set(feature_policy.get("disabled_for_languages", []) or [])
        supported_languages = set(feature_policy.get("languages", []) or [])
        if language in disabled_languages or (supported_languages and language not in supported_languages):
            disabled.add(feature)
    return disabled


def configured_features(
    config: dict[str, str],
    policy: dict[str, Any],
    language: str,
    requested: list[str] | None,
) -> list[str]:
    if requested:
        features = requested
    else:
        features = [item.strip() for item in config.get("GOOGLE_NLP_DEFAULT_FEATURES", "").split(",") if item.strip()]

    allowed = csv_set(config.get("GOOGLE_NLP_ALLOWED_FEATURES"))
    if allowed:
        features = [feature for feature in features if feature in allowed]

    disabled = csv_set(config.get(f"GOOGLE_NLP_DISABLED_FEATURES_FOR_{language.upper()}"))
    disabled |= policy_disabled_for_language(policy, language)
    return [feature for feature in features if feature not in disabled]


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


def fetch_url_text(url: str, timeout: int = 30) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "seo-cycle-GoogleNLPAudit/1.0"},
    )
    response.raise_for_status()
    return clean_html(response.text)


def units_for(feature: str, text: str) -> int:
    if not text:
        return 0
    size = UNIT_SIZE.get(feature, 1000)
    return max(1, math.ceil(len(text) / size))


def env_int(config: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(config.get(key, default))
    except ValueError:
        return default


def total_cap_for(config: dict[str, str], feature: str) -> int:
    token = FEATURE_ENV_TOKENS[feature]
    configured_total = env_int(config, f"GOOGLE_NLP_TOTAL_{token}_UNITS_CAP_PER_MONTH", -1)
    if configured_total >= 0:
        return configured_total
    free = env_int(config, f"GOOGLE_NLP_FREE_{token}_UNITS_PER_MONTH", 0)
    paid = env_int(config, f"GOOGLE_NLP_PAID_{token}_UNITS_CAP_PER_MONTH", 0)
    return free + paid


def month_key(today: dt.date | None = None) -> str:
    current = today or dt.date.today()
    return current.strftime("%Y-%m")


def usage_path(cache_dir: Path, month: str) -> Path:
    return cache_dir / f"usage-{month}.json"


def load_usage(cache_dir: Path, month: str) -> dict[str, Any]:
    path = usage_path(cache_dir, month)
    if not path.exists():
        return {"month": month, "features": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_usage(cache_dir: Path, usage: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = usage_path(cache_dir, usage["month"])
    path.write_text(json.dumps(usage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_monthly_cap(config: dict[str, str], usage: dict[str, Any], feature: str, units: int) -> None:
    cap = total_cap_for(config, feature)
    used = int(usage.get("features", {}).get(feature, 0))
    if used + units > cap:
        raise GuardError(f"{feature} would use {used + units} units, above configured cap {cap}")


def add_usage(usage: dict[str, Any], feature: str, units: int) -> dict[str, Any]:
    next_usage = json.loads(json.dumps(usage))
    features = next_usage.setdefault("features", {})
    features[feature] = int(features.get(feature, 0)) + units
    return next_usage


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def cache_file(cache_dir: Path, source_id: str, text: str, language: str, feature: str, api_version: str) -> Path:
    payload = {
        "source": source_id,
        "text_sha256": sha256_text(text),
        "language": language,
        "feature": feature,
        "api_version": api_version,
    }
    return cache_dir / f"{sha256_text(json.dumps(payload, sort_keys=True))}.json"


def is_cache_fresh(path: Path, ttl_days: int, now: dt.datetime | None = None) -> bool:
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    cached_at = dt.datetime.fromisoformat(data["cached_at"])
    return ((now or dt.datetime.now(dt.timezone.utc)) - cached_at).days < ttl_days


def credentials(project_root: Path, config: dict[str, str]) -> service_account.Credentials:
    key_path_raw = config.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not key_path_raw:
        raise GuardError("GOOGLE_APPLICATION_CREDENTIALS is not configured")
    key_path = project_path(project_root, key_path_raw)
    if not key_path.exists():
        raise GuardError(f"GOOGLE_APPLICATION_CREDENTIALS file not found: {key_path}")
    creds = service_account.Credentials.from_service_account_file(
        key_path,
        scopes=["https://www.googleapis.com/auth/cloud-language"],
    )
    creds.refresh(AuthRequest())
    return creds


def document_payload(text: str, language: str, api_version: str, include_encoding: bool) -> dict[str, Any]:
    language_key = "languageCode" if api_version == "v2" else "language"
    payload: dict[str, Any] = {
        "document": {
            "type": "PLAIN_TEXT",
            "content": text,
            language_key: language,
        }
    }
    if include_encoding:
        payload["encodingType"] = "UTF8"
    return payload


def call_feature(project_root: Path, feature: str, text: str, language: str, config: dict[str, str]) -> dict[str, Any]:
    api_version, endpoint = FEATURE_ENDPOINTS[feature]
    creds = credentials(project_root, config)
    body = document_payload(text, language, api_version, include_encoding=feature != "classifyText")
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def analyze_source(
    *,
    project_root: Path,
    source_id: str,
    text: str,
    language: str,
    features: list[str],
    config: dict[str, str],
    dry_run: bool,
    force_refresh: bool,
    include_cache_result: bool,
) -> list[dict[str, Any]]:
    cache_dir = project_path(project_root, config.get("GOOGLE_NLP_CACHE_DIR", "seo/cache/google-nlp"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    ttl_days = env_int(config, "GOOGLE_NLP_CACHE_DAYS", 30)
    max_chars = env_int(config, "GOOGLE_NLP_MAX_CHARS_PER_URL", 10000)
    clipped_text = text[:max_chars]
    usage = load_usage(cache_dir, month_key())
    results: list[dict[str, Any]] = []

    for feature in features:
        if feature not in FEATURE_ENDPOINTS:
            results.append({"feature": feature, "status": "skipped", "reason": "unsupported_feature"})
            continue

        api_version, _endpoint = FEATURE_ENDPOINTS[feature]
        path = cache_file(cache_dir, source_id, clipped_text, language, feature, api_version)
        units = units_for(feature, clipped_text)
        if not force_refresh and is_cache_fresh(path, ttl_days):
            cache_hit = {"feature": feature, "status": "cache_hit", "units": 0, "cache_file": str(path)}
            if include_cache_result:
                cache_hit["result"] = json.loads(path.read_text(encoding="utf-8"))
            results.append(cache_hit)
            continue

        try:
            check_monthly_cap(config, usage, feature, units)
        except GuardError as exc:
            results.append({"feature": feature, "status": "guard_blocked", "units": units, "reason": str(exc)})
            continue

        plan = {"feature": feature, "status": "planned", "units": units, "cache_file": str(path)}
        if dry_run:
            results.append(plan)
            continue

        response = call_feature(project_root, feature, clipped_text, language, config)
        record = {
            "cached_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source": source_id,
            "language": language,
            "feature": feature,
            "api_version": api_version,
            "cleaned_text_sha256": sha256_text(clipped_text),
            "units": units,
            "response": response,
        }
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        usage = add_usage(usage, feature, units)
        save_usage(cache_dir, usage)
        results.append({"feature": feature, "status": "api_call", "units": units, "cache_file": str(path)})

    return results


def read_sources(project_root: Path, args: argparse.Namespace, config: dict[str, str]) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    max_urls = env_int(config, "GOOGLE_NLP_MAX_URLS_PER_RUN", 50)

    if args.text:
        sources.append(("inline-text", args.text))
    if args.text_file:
        path = project_path(project_root, args.text_file)
        sources.append((str(path), path.read_text(encoding="utf-8")))
    if args.url:
        sources.append((args.url, fetch_url_text(args.url)))
    if args.urls_file:
        urls_path = project_path(project_root, args.urls_file)
        urls = [
            line.strip()
            for line in urls_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ][:max_urls]
        for url in urls:
            sources.append((url, fetch_url_text(url)))

    if len(sources) > max_urls:
        raise GuardError(f"run has {len(sources)} sources, above GOOGLE_NLP_MAX_URLS_PER_RUN={max_urls}")
    if not sources:
        raise GuardError("provide --url, --urls-file, --text, or --text-file")
    return sources


def check_global_guards(config: dict[str, str], policy: dict[str, Any], dry_run: bool) -> None:
    if config.get("GOOGLE_NLP_ENABLED") != "1":
        raise GuardError("GOOGLE_NLP_ENABLED is not 1")
    if policy.get("status", {}).get("enabled") is False:
        raise GuardError("policy status.enabled is false")
    if dry_run:
        return
    if config.get("GOOGLE_NLP_BILLING_APPROVED") != "1":
        raise GuardError("GOOGLE_NLP_BILLING_APPROVED is not 1")
    budget_status = config.get("GOOGLE_NLP_BUDGET_STATUS", "")
    if budget_status.startswith("disabled"):
        raise GuardError(f"GOOGLE_NLP_BUDGET_STATUS blocks calls: {budget_status}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Project root with .env and seo/ policy files.")
    parser.add_argument("--env-file", action="append", dest="env_files", help="Extra env file, relative to project root or absolute.")
    parser.add_argument("--policy-file", help=f"Policy file path. Default: {DEFAULT_POLICY_REL}")
    parser.add_argument("--url")
    parser.add_argument("--urls-file")
    parser.add_argument("--text")
    parser.add_argument("--text-file")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--feature", action="append", dest="features")
    parser.add_argument("--output", help="Write JSON result to file instead of stdout.")
    parser.add_argument("--dry-run", action="store_true", help="Plan units/cache only; do not call Google.")
    parser.add_argument("--force-refresh", action="store_true", help="Ignore fresh cache entries.")
    parser.add_argument("--include-cache-result", action="store_true", help="Print full cached Google responses.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    config = load_config(project_root, args.env_files)
    policy_path = project_path(project_root, args.policy_file or config.get("GOOGLE_NLP_POLICY_FILE", DEFAULT_POLICY_REL))
    policy = load_policy(policy_path)
    config = apply_policy_defaults(config, policy)
    check_global_guards(config, policy, args.dry_run)

    features = configured_features(config, policy, args.language, args.features)
    if not features:
        raise GuardError("no enabled features after language/policy filtering")

    sources = read_sources(project_root, args, config)
    output = []
    for source_id, text in sources:
        output.append(
            {
                "source": source_id,
                "language": args.language,
                "chars": min(len(text), env_int(config, "GOOGLE_NLP_MAX_CHARS_PER_URL", 10000)),
                "policy_file": str(policy_path),
                "features": analyze_source(
                    project_root=project_root,
                    source_id=source_id,
                    text=text,
                    language=args.language,
                    features=features,
                    config=config,
                    dry_run=args.dry_run,
                    force_refresh=args.force_refresh,
                    include_cache_result=args.include_cache_result,
                ),
            }
        )

    payload = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output_path = project_path(project_root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Wrote {output_path}")
    else:
        print(payload, end="")
    return 0


def run() -> int:
    try:
        return main()
    except GuardError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
