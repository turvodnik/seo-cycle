#!/usr/bin/env python3
"""Daily data pulse: fresh positions → snapshot → db-sync → progress + freshness watch.

Замыкает обещание «расписание само снимает срез»: до pulse ежедневный джоб
пережёвывал последний снапшот без новых данных (боевой факт: 6 дней подряд
срез от 2026-07-04). Каждый шаг graceful — нет токенов Вебмастера, конвейер
продолжает на имеющихся данных и честно помечает это в findings и самооценке.

Шаги:
  1. webmaster-fetch --live (бесплатный API; только если токены настроены)
  2. snapshot-build --source webmaster  → seo/monitoring/webmaster-snapshot-<дата>.json
  3. db-sync                            → positions в seo.db
  4. position-progress --write --html   → seo/reports/position-progress.*
  5. свежесть среза + детект просадки топ-10 (alert через notify, если настроен)
  6. scorecard: самооценка запуска 0–10 из findings

Config (всё опционально):
  pulse:
    days: 14              # окно выборки Вебмастера
    stale_after_days: 3   # срез старше → warning (старше 7 → error)
    drop_alert_pct: 5     # относительное падение топ-10 → critical + notify

Usage:
  python3 scripts/pulse.py [--days 14] [--skip-fetch] [--format md|json]
Exit: 0 ok/warnings · 1 critical (просадка или конвейер сломан) · 2 config error
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.env_profile import env_chain
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.scorecard import score_from_findings, write_scorecard

log = setup_logging("pulse")

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent

WEBMASTER_TOKEN_VARS = ("YANDEX_WEBMASTER_OAUTH_TOKEN", "YANDEX_OAUTH_TOKEN")
WEBMASTER_HOST_VARS = ("YANDEX_WEBMASTER_HOST_ID", "YANDEX_HOST_ID")
WEBMASTER_USER_VARS = ("YANDEX_WEBMASTER_USER_ID", "YANDEX_USER_ID")

STALE_ERROR_DAYS = 7


def first_env(env: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        if env.get(name):
            return str(env[name])
    return ""


def webmaster_ready(env: dict[str, str]) -> bool:
    # user_id/host_id больше не обязательны: webmaster-fetch выводит их из API
    # по токену (host — по project.domain конфига)
    return bool(first_env(env, WEBMASTER_TOKEN_VARS))


def run_step(script: str, args: list[str], root: pathlib.Path, env: dict[str, str],
             timeout: int = 180) -> tuple[int, str, str]:
    path = SCRIPTS_DIR / script
    if not path.exists():
        return 2, "", f"script not found: {script}"
    try:
        proc = subprocess.run(
            [sys.executable, str(path), *args],
            cwd=root, env=env, text=True, capture_output=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return 2, "", f"timeout {timeout}s"
    return proc.returncode, proc.stdout, proc.stderr


def freshness_findings(latest_date: str, today: dt.date, stale_after: int) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not latest_date:
        findings.append({"id": "no_snapshots", "severity": "error",
                         "message": "нет ни одного среза позиций — конвейер пуст"})
        return findings
    try:
        age = (today - dt.date.fromisoformat(latest_date)).days
    except ValueError:
        findings.append({"id": "bad_snapshot_date", "severity": "warning",
                         "message": f"не разобрал дату среза: {latest_date!r}"})
        return findings
    if age > STALE_ERROR_DAYS:
        findings.append({"id": "stale_snapshot", "severity": "error",
                         "message": f"срез позиций устарел на {age} дн. (порог ошибки {STALE_ERROR_DAYS})"})
    elif age > stale_after:
        findings.append({"id": "stale_snapshot", "severity": "warning",
                         "message": f"срез позиций устарел на {age} дн. (порог {stale_after})"})
    return findings


def drop_finding(progress: dict[str, Any], drop_pct: float) -> dict[str, Any] | None:
    latest = progress.get("latest") or {}
    delta = progress.get("delta_vs_previous") or {}
    top10_delta = delta.get("top10")
    if top10_delta is None:
        return None
    previous_top10 = (latest.get("top10") or 0) - top10_delta
    if previous_top10 <= 0 or top10_delta >= 0:
        return None
    dropped_pct = -top10_delta / previous_top10 * 100
    if dropped_pct < drop_pct:
        return None
    return {"id": "top10_drop", "severity": "critical",
            "message": f"топ-10 просел на {top10_delta} запросов ({dropped_pct:.1f}% от {previous_top10})"}


def build_pulse(root: pathlib.Path, cfg: dict[str, Any], env: dict[str, str],
                days: int, skip_fetch: bool) -> dict[str, Any]:
    today = dt.date.today()
    steps: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    def note(step: str, ok: bool, message: str) -> None:
        steps.append({"step": step, "ok": ok, "note": message})

    # 1-2. fetch + snapshot (graceful: без токенов конвейер живёт на старых данных)
    if skip_fetch:
        note("fetch", True, "пропущен (--skip-fetch)")
    elif not webmaster_ready(env):
        note("fetch", False, "Вебмастер не настроен (auth login yandex)")
        findings.append({"id": "fetch_not_configured", "severity": "warning",
                         "message": "источник позиций не настроен — свежие срезы не снимаются"})
    else:
        raw_path = root / "seo" / "monitoring" / "raw" / f"webmaster-raw-{today.isoformat()}.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        fetch_args = ["--days", str(days), "--output", str(raw_path)]
        domain = str(nested_get(cfg, "project.domain", "") or "")
        if domain:
            fetch_args += ["--domain", domain]
        rc, _, stderr = run_step("webmaster-fetch.py", fetch_args, root, env)
        if rc != 0:
            note("fetch", False, stderr.strip().splitlines()[-1] if stderr.strip() else f"rc={rc}")
            findings.append({"id": "fetch_failed", "severity": "error",
                             "message": "webmaster-fetch упал — работаем на прошлом срезе"})
        else:
            note("fetch", True, f"raw → {raw_path.relative_to(root)}")
            snapshot_path = root / "seo" / "monitoring" / f"webmaster-snapshot-{today.isoformat()}.json"
            rc, _, stderr = run_step("snapshot-build.py",
                                     ["--source", "webmaster", "--input", str(raw_path),
                                      "--output", str(snapshot_path)], root, env, timeout=60)
            if rc != 0:
                note("snapshot", False, stderr.strip()[-200:] or f"rc={rc}")
                findings.append({"id": "snapshot_failed", "severity": "error",
                                 "message": "snapshot-build не собрал срез из raw-выгрузки"})
            else:
                note("snapshot", True, f"{snapshot_path.relative_to(root)}")

    # 3. db-sync
    rc, _, stderr = run_step("db-sync.py", [], root, env)
    if rc != 0:
        note("db-sync", False, stderr.strip()[-200:] or f"rc={rc}")
        findings.append({"id": "db_sync_failed", "severity": "error",
                         "message": "db-sync упал — seo.db не обновлена"})
    else:
        note("db-sync", True, "seo.db пересобрана")

    # 4. position-progress (пишет md/json/html)
    rc, _, stderr = run_step("position-progress.py", ["--write", "--html"], root, env)
    if rc != 0:
        note("progress", False, stderr.strip()[-200:] or f"rc={rc}")
        findings.append({"id": "progress_failed", "severity": "error",
                         "message": "position-progress упал — отчёт прогресса не обновлён"})
    else:
        note("progress", True, "seo/reports/position-progress.md/html")

    # 5. свежесть + просадка — по фактически записанному отчёту
    progress: dict[str, Any] = {}
    progress_path = root / "seo" / "reports" / "position-progress.json"
    if progress_path.exists():
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            progress = {}
    latest_date = str(((progress.get("latest") or {}).get("date")) or "")
    stale_after = int(nested_get(cfg, "pulse.stale_after_days", 3) or 3)
    findings.extend(freshness_findings(latest_date, today, stale_after))
    drop = drop_finding(progress, float(nested_get(cfg, "pulse.drop_alert_pct", 5) or 5))
    if drop:
        findings.append(drop)

    score = score_from_findings(findings)
    return {
        "audit_id": "pulse",
        "date": today.isoformat(),
        "project": str(nested_get(cfg, "project.name", root.name) or root.name),
        "steps": steps,
        "findings": findings,
        "latest_snapshot": latest_date or None,
        "latest": progress.get("latest") or {},
        "delta_vs_previous": progress.get("delta_vs_previous") or {},
        "score": score,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Pulse — {report['project']} · {report['date']}", ""]
    for step in report["steps"]:
        mark = "✓" if step["ok"] else "✗"
        lines.append(f"- {mark} {step['step']}: {step['note']}")
    latest = report.get("latest") or {}
    if latest:
        delta = report.get("delta_vs_previous") or {}
        top10_delta = delta.get("top10")
        delta_note = f" ({'+' if top10_delta > 0 else ''}{top10_delta} vs prev)" if top10_delta else ""
        lines.append(f"- срез {report.get('latest_snapshot')}: топ-10 **{latest.get('top10')}**{delta_note}"
                     f" · клики {latest.get('clicks')}")
    if report["findings"]:
        lines.append("")
        for finding in report["findings"]:
            lines.append(f"- [{finding['severity']}] {finding['message']}")
    lines.extend(["", f"Самооценка запуска: **{report['score']}/10**", ""])
    return "\n".join(lines)


def pulse_project(cfg_path: pathlib.Path, args) -> tuple[dict, int]:
    cfg = load_yaml(cfg_path)
    root = project_root_for(cfg_path)
    global log
    log = setup_logging("pulse", root, cfg)
    env = env_chain(root)

    days = args.days or int(nested_get(cfg, "pulse.days", 14) or 14)
    report = build_pulse(root, cfg, env, days, args.skip_fetch)

    write_scorecard(
        root, "pulse", report["score"],
        status="done" if all(step["ok"] for step in report["steps"]) else "partial",
        done=[step["step"] for step in report["steps"] if step["ok"]],
        missing=[finding["message"] for finding in report["findings"]],
        meta={"snapshot_date": report.get("latest_snapshot")},
    )

    has_critical = any(finding["severity"] == "critical" for finding in report["findings"])
    if has_critical:
        # best effort: без Telegram-токена notify сам скажет об этом в stderr
        messages = "; ".join(f["message"] for f in report["findings"] if f["severity"] == "critical")
        run_step("notify.py", [f"[pulse] {report['project']}: {messages}", "--level", "alert"],
                 root, env, timeout=30)
    return report, (1 if has_critical else 0)


def load_registry_projects(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    projects = load_yaml(path).get("projects") or []
    return [p for p in projects if isinstance(p, dict) and p.get("path")
            and str(p.get("status", "active")) == "active"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--days", type=int, default=0, help="Окно выборки Вебмастера (default: pulse.days|14)")
    parser.add_argument("--skip-fetch", action="store_true", help="Не ходить в сеть — только db/progress/свежесть")
    parser.add_argument("--global", dest="global_run", action="store_true",
                        help="Пульс всех active-проектов реестра (портфельный daily-джоб)")
    parser.add_argument("--registry", type=pathlib.Path,
                        default=SCRIPTS_DIR.parent / "config" / "projects-registry.yaml")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    if args.global_run:
        entries = load_registry_projects(args.registry)
        if not entries:
            print(f"ERROR: нет active-проектов в реестре {args.registry}", file=sys.stderr)
            return 2
        rc = 0
        reports = []
        for entry in entries:
            cfg_path = pathlib.Path(str(entry["path"])).expanduser() / "seo-cycle.yaml"
            if not cfg_path.exists():
                print(f"⚠ {entry.get('name') or entry['path']}: seo-cycle.yaml не найден — пропуск",
                      file=sys.stderr)
                continue
            report, project_rc = pulse_project(cfg_path, args)
            rc = max(rc, project_rc)
            reports.append(report)
            if args.format != "json":
                print(render_markdown(report))
        if args.format == "json":
            print(json.dumps(reports, ensure_ascii=False, indent=2))
        return rc

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    report, rc = pulse_project(cfg_path, args)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
