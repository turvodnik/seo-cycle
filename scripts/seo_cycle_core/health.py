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
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Callable, Sequence

from .config import find_config, load_yaml, project_root_for
from .reports import write_report_bundle

MISSING_CONFIG_MSG = "ERROR: seo-cycle.yaml not found in {cwd}"
CONFIG_PATH_MISSING_MSG = "ERROR: {cfg_path} not found"

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
    cfg = load_yaml(cfg_path)
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

    report = spec.build_report(cfg_path, args)
    if args.write:
        paths = spec.output_paths(load_yaml(cfg_path), project_root_for(cfg_path))
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
