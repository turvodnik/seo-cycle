"""Shared engine for provider `*-health.py` scripts (T-053).

Seven scripts — `gbp`, `google-ads`, `merchant`, `yandex-direct`,
`yandex-business`, `notebooklm`, `perplexity` — were hand-copied from one
template (difflib line-similarity 0.58-0.69 pairwise, see
`optimize/reports/2026-09-03-seo-cycle-audit-code.md` §5.1). A fix that
landed in one copy in v2.0.2 never reached the other five — exactly the
failure mode `vnext_audit_core.py` (13 audits as five-line wrappers over one
engine) already solved elsewhere in this repo. This module is that same
pattern applied to health checks: `scripts/*-health.py` become a spec plus
`sys.exit(run_health(SPEC))`.

The output format of `seo/setup/<provider>-health.md` (and the paired
`.json`) is frozen — dashboards, `doctor`, and humans read it. This module
changes nothing about what gets written for any of the seven providers; it
only stops duplicating the argparse / config-loading / write-dispatch
skeleton that surrounded each provider's own report-building logic.

Two call conventions exist among the seven scripts (verified byte-for-byte
against the pre-refactor originals, `tests/fixtures/health/`):

- ``style="simple"`` (gbp, google-ads, merchant, yandex-direct,
  yandex-business): ``ArgumentParser(description=<wrapper __doc__>)``, only
  ``config``/``--write``/``--format``; ``build_report(cfg)``; on ``--write``
  the report is written AND still printed per ``--format``.
- ``style="policy"`` (notebooklm, perplexity): bare ``ArgumentParser()``,
  provider-specific extra CLI flags before ``--write``/``--format``;
  ``build_report(cfg_path, args)`` (loads the config itself, needs the raw
  args for its extra flags); output paths resolve through
  ``policy_files`` in the project config (`policy_path`); on ``--write``
  only ``Wrote <path>`` is printed, and JSON is NOT `sort_keys` (field
  order in ``build_report`` is load-bearing for `policy` reports).

A `HealthSpec` never guesses at these differences — every field that
differs between the two families is explicit, so a reviewer can see the
divergence instead of it hiding in copy-paste drift.

T-062 — the one BEHAVIOUR change layered on top of the T-053 refactor: a
provider switched off in the project config (`enabled_key`, e.g.
`sources.google_merchant.enabled` or `ads.google_ads.enabled`) is not
probed at all. The wrapper's `build_report` is never called — no env
lookup, no app/browser detection, no network — and a short report with
status `disabled_in_config` is printed/written instead (exit 0: a report
was produced, same rung as `partner_limited`/`needs_credentials`). The
switch semantics mirror `pulse.py` → `engines.engine_names()` (`if
enabled`: a falsy flag means "skip"): the key must be PRESENT and falsy;
a missing key is "no signal" and the wrapper runs exactly as before,
which is what keeps the pre-T-062 goldens byte-identical.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any, Callable, Sequence

from .config import find_config, load_config, nested_get, project_root_for, require_section
from .reports import write_report_bundle

MISSING_CONFIG_MSG = "ERROR: seo-cycle.yaml not found in {cwd}"
CONFIG_PATH_MISSING_MSG = "ERROR: {cfg_path} not found"
DISABLED_STATUS = "disabled_in_config"
DISABLED_NOTE = (
    "Провайдер выключен в конфиге проекта ({key}: false) — health-проверка не запускалась: "
    "переменные окружения не читались, сеть и локальные приложения не опрашивались. "
    "Это ожидаемое состояние, не ошибка. Чтобы проверять провайдера, поставь {key}: true "
    "или убери ключ."
)

# `build_report` has two incompatible call shapes depending on `style`
# (`(cfg)` for "simple", `(cfg_path, args)` for "policy") — a Union of the
# two Callables makes mypy reject calling the attribute at all, since it
# cannot know which arity applies at the call site. `style` is the runtime
# discriminator instead; the two wrappers (`_run_simple`/`_run_policy`) are
# each written for exactly one arity and never call the other's shape.
BuildReport = Callable[..., dict[str, Any]]
OutputPaths = Callable[[dict[str, Any], pathlib.Path], dict[str, pathlib.Path]]
RenderMarkdown = Callable[[dict[str, Any]], str]


class HealthSpec:
    """Describes one provider health check. See module docstring for the
    two `style` conventions this maps onto."""

    def __init__(
        self,
        *,
        slug: str,
        style: str,
        build_report: BuildReport,
        render_markdown: RenderMarkdown,
        write_help: str,
        description: str | None = None,
        output_paths: OutputPaths | None = None,
        extra_arguments: Sequence[dict[str, Any]] = (),
        enabled_key: str | None = None,
    ) -> None:
        if style not in ("simple", "policy"):
            raise ValueError(f"unknown health spec style: {style!r}")
        self.slug = slug
        self.style = style
        self.build_report = build_report
        self.render_markdown = render_markdown
        self.write_help = write_help
        self.description = description
        self.output_paths = output_paths or (lambda cfg, project_root: default_output_paths(project_root, slug))
        self.extra_arguments = extra_arguments
        # Dotted path of the provider's on/off switch in seo-cycle.yaml
        # (T-062). None = this provider has no switch and is always probed.
        self.enabled_key = enabled_key


def default_output_paths(project_root: pathlib.Path, slug: str) -> dict[str, pathlib.Path]:
    """The `seo/setup/<slug>-health.*` (+ `latest-`) bundle every `style="simple"`
    provider used, spelled out once instead of five times."""
    base = project_root / "seo" / "setup"
    return {
        "markdown": base / f"{slug}-health.md",
        "json": base / f"{slug}-health.json",
        "latest_markdown": base / f"latest-{slug}-health.md",
        "latest_json": base / f"latest-{slug}-health.json",
    }


def render_sections(sections: Sequence[tuple[str, Sequence[str]]]) -> list[str]:
    """Renders the repeating `["", "## <title>", "- item", ...]` tail shared
    by every provider report (Capabilities/Guardrails/Official Docs for most;
    yandex-business swaps "Capabilities" for "Working paths" — same shape,
    different label, so this stays label-driven rather than hardcoded)."""
    lines: list[str] = []
    for title, items in sections:
        lines.extend(["", f"## {title}"])
        lines.extend(f"- {item}" for item in items)
    return lines


def disabled_config_key(cfg: dict[str, Any], enabled_key: str | None) -> str | None:
    """Returns the switch key when the provider is explicitly OFF in `cfg`,
    else None. Present-and-falsy only — the same reading `pulse.py` gives
    an engine flag via `engines.engine_names()` (`if enabled`); an absent
    key is not a signal, so a config that never mentions the provider
    behaves exactly as before T-062."""
    if not enabled_key:
        return None
    sentinel = object()
    value = nested_get(cfg, enabled_key, sentinel)
    if value is sentinel or value:
        return None
    return enabled_key


def disabled_report(spec: HealthSpec, cfg: dict[str, Any], key: str) -> dict[str, Any]:
    return {
        "provider": spec.slug,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": cfg.get("project", {}),
        "status": DISABLED_STATUS,
        "config_key": key,
        "status_note": DISABLED_NOTE.format(key=key),
        "checked": False,
    }


def render_disabled_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Provider Health: {report['provider']}",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}`",
        f"- Config key: `{report['config_key']}`",
        f"- Note: {report['status_note']}",
    ]
    return "\n".join(lines) + "\n"


def _emit_disabled(spec: HealthSpec, cfg: dict[str, Any], cfg_path: pathlib.Path, key: str,
                   args: argparse.Namespace) -> int:
    """Print/write the disabled report along the SAME output path the
    provider's family uses (simple: write AND print, sorted JSON; policy:
    write → only `Wrote …`, JSON in build order), so a dashboard or a human
    reading `seo/setup/<slug>-health.*` sees the state where they always
    looked. Exit 0: a report was produced."""
    report = disabled_report(spec, cfg, key)
    markdown = render_disabled_markdown(report)
    if args.write:
        paths = spec.output_paths(cfg, project_root_for(cfg_path))
        write_report_bundle(paths, markdown, report)
        if spec.style == "policy":
            print(f"Wrote {paths['markdown']}")
            return 0
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=spec.style == "simple"))
    else:
        print(markdown, end="")
    return 0


def _run_simple(spec: HealthSpec) -> int:
    parser = argparse.ArgumentParser(description=spec.description)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help=spec.write_help)
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(MISSING_CONFIG_MSG.format(cwd=pathlib.Path.cwd()), file=sys.stderr)
        return 2
    cfg = load_config(cfg_path)
    # T-093 круг 2 (R-3, независимый гейт): все `style="simple"` вызывающие
    # (`gbp-health.py`, `google-ads-health.py`, `merchant-health.py`,
    # `yandex-business-health.py`, `yandex-direct-health.py`) кладут
    # `cfg.get("project", {})` прямо в отчёт без проверки формы — на
    # `project: null` печатали заголовок отчёта с пустой идентичностью и
    # `rc=0`. Один вызов здесь закрывает класс для всех пяти разом.
    require_section(cfg, "project", cfg_path)
    disabled_key = disabled_config_key(cfg, spec.enabled_key)
    if disabled_key:
        return _emit_disabled(spec, cfg, cfg_path, disabled_key, args)
    project_root = project_root_for(cfg_path)
    report = spec.build_report(cfg)
    if args.write:
        write_report_bundle(spec.output_paths(cfg, project_root), spec.render_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(spec.render_markdown(report), end="")
    return 0


def _run_policy(spec: HealthSpec) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    for extra in spec.extra_arguments:
        flags = extra["flags"]
        kwargs = {k: v for k, v in extra.items() if k != "flags"}
        parser.add_argument(*flags, **kwargs)
    parser.add_argument("--write", action="store_true", help=spec.write_help)
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    if args.config:
        cfg_path = pathlib.Path(args.config).expanduser().resolve()
    else:
        found = find_config(pathlib.Path.cwd())
        if not found:
            print(MISSING_CONFIG_MSG.format(cwd=pathlib.Path.cwd()), file=sys.stderr)
            return 2
        cfg_path = found.resolve()
    if not cfg_path.exists():
        print(CONFIG_PATH_MISSING_MSG.format(cfg_path=cfg_path), file=sys.stderr)
        return 2

    # T-062: the gate runs BEFORE the provider's own `build_report`, which
    # for this family is where env/app/browser probing happens. Loading the
    # config here (the wrapper loads it again on the enabled path — cheap,
    # and keeps the enabled path byte-identical to pre-T-062).
    cfg = load_config(cfg_path)
    disabled_key = disabled_config_key(cfg, spec.enabled_key)
    if disabled_key:
        require_section(cfg, "project", cfg_path)
        return _emit_disabled(spec, cfg, cfg_path, disabled_key, args)

    report = spec.build_report(cfg_path, args)
    if args.write:
        paths = spec.output_paths(load_config(cfg_path), project_root_for(cfg_path))
        write_report_bundle(paths, spec.render_markdown(report), report)
        print(f"Wrote {paths['markdown']}")
    elif args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(spec.render_markdown(report), end="")
    return 0


def run_health(spec: HealthSpec) -> int:
    """Entry point every `scripts/*-health.py` wrapper calls:
    `sys.exit(run_health(SPEC))`."""
    if spec.style == "simple":
        return _run_simple(spec)
    return _run_policy(spec)
