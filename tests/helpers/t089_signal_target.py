#!/usr/bin/env python3
"""Subprocess target for T-089's write-ahead signal matrix (F-1).

Run as a real, separate OS process (not a mocked in-process call) so
SIGINT/SIGTERM/SIGKILL are genuine signal deliveries, not a simulated
exception. Prints "STARTED" and flushes the instant the write-ahead record
has already landed on disk and the (faked) paid network call has begun to
hang — the parent test only sends the signal after seeing that line, so the
signal is guaranteed to land strictly after the write-ahead write, exactly
the window F-1 exploited in google-nlp-audit.py.

The paid network primitive is replaced with a stub that blocks — the actual
HTTP/urllib call for each client is out of scope here (T-089 is about
ordering: record-before-call), and the standing rule against live paid
requests still applies. Every other line of the real script executes.

Usage: t089_signal_target.py <client> <out_dir> [<project_root>]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import signal
import sys
import time
from types import SimpleNamespace

# T-066 QA-v2.2.0 lesson (F-1 repro): a background/detached shell can inherit
# SIGINT=SIG_IGN, in which case CPython does not install its normal
# KeyboardInterrupt-raising handler and `kill -INT` silently does nothing —
# giving a false "protected" result. Force the default disposition
# explicitly so this target script behaves the same regardless of how the
# parent test launched it.
signal.signal(signal.SIGINT, signal.default_int_handler)
signal.signal(signal.SIGTERM, signal.SIG_DFL)

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hang(*_args, **_kwargs):
    print("STARTED", flush=True)
    time.sleep(60)
    raise AssertionError("hang() was not interrupted by the expected signal")


def run_dataforseo(out_dir: pathlib.Path) -> None:
    dfs = _load("dataforseo_fetch_t089", "dataforseo-fetch.py")
    dfs.call = _hang
    args = SimpleNamespace(out=str(out_dir), force=False, budget=1e9, ttl=0.0)
    dfs.fetch("b64", "some/path", {"k": 1}, args)


def run_spyfu(out_dir: pathlib.Path) -> None:
    spyfu = _load("spyfu_fetch_t089", "spyfu-fetch.py")
    spyfu.find_config = lambda *_a, **_kw: None
    spyfu.call = _hang
    args = SimpleNamespace(out=str(out_dir), force=False, budget=1e9, ttl=0.0)
    spyfu.run("b64", "some/path", 0.5, {"domain": "x"}, args, lambda _r: None)


def run_google_nlp(out_dir: pathlib.Path) -> None:
    gnlp = _load("google_nlp_audit_t089", "google-nlp-audit.py")
    gnlp.call_feature = _hang
    config = {
        "GOOGLE_NLP_CACHE_DIR": str(out_dir),
        "GOOGLE_NLP_CACHE_DAYS": "30",
        "GOOGLE_NLP_TOTAL_ENTITY_UNITS_CAP_PER_MONTH": "100000",
    }
    gnlp.analyze_source(
        project_root=out_dir, source_id="https://example.com", text="hello world " * 20,
        language="en", features=["analyzeEntities"], config=config,
        dry_run=False, force_refresh=False, include_cache_result=False,
    )


CFG = (
    "project:\n  name: t089-signal-matrix\n  url: https://example.com\n"
    "governance:\n  budget_policy:\n    monthly_total_usd_cap: 500\n"
    "    monthly_paid_api_usd_cap: 90\n"
    "ads:\n  enabled: true\n  policy: approval_only\n"
    "  yandex_direct:\n    enabled: true\n    sandbox: true\n"
    "  google_ads:\n    enabled: true\n"
)


def _ads_project_root(project_root: pathlib.Path) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "seo-cycle.yaml").write_text(CFG, encoding="utf-8")


def run_ads_apply(project_root: pathlib.Path) -> None:
    """Runs the REAL main() → armed_spend(ledger_record) → apply_direct()
    path (review round-2 finding R2-9: round 2's harness called
    apply_direct() directly and armed it with the harness's OWN
    armed_spend()/ledger_record() call, never executing main()'s own
    write-ahead call site — the matrix cell proved the harness, not the
    product). Only the environment/approval PRECONDITIONS (which need real
    env vars / a real approved ticket) and the network primitive are
    stubbed; ledger_record()/armed_spend()/apply_direct() are the real
    functions, called from the real main()."""
    _ads_project_root(project_root)
    os.chdir(project_root)
    mod = _load("ads_apply_t089", "ads-apply.py")
    mod.direct_request = _hang
    mod.env_status = lambda _platform: {"present": True, "missing": []}
    mod.ticket_status = lambda _project_root, _ticket: "approved"
    draft = {
        "platform": "yandex_direct",
        "campaigns": [{"name": "camp-1", "channel": "search", "budget_daily": 0, "ad_groups": []}],
    }
    draft_path = project_root / "draft.json"
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    mod.sys.argv = ["ads-apply.py", "--draft", str(draft_path), "--ticket", "T-1",
                    "--live", "--allow-write"]
    mod.main()


def run_yandex_direct(project_root: pathlib.Path) -> None:
    """Runs the REAL main() → armed_spend(ledger_record) → live_fetch() path
    (R2-9) — only direct_request() (the network primitive) and the
    env/preflight preconditions are stubbed."""
    _ads_project_root(project_root)
    os.chdir(project_root)
    mod = _load("yandex_direct_fetch_t089", "yandex-direct-fetch.py")
    mod.direct_request = _hang
    mod.env_status = lambda _platform: {"present": True, "missing": []}
    mod.ledger_preflight = lambda *_a, **_kw: (True, "ok")
    mod.sys.argv = ["yandex-direct-fetch.py", "--report", "campaigns", "--live"]
    mod.main()


def run_google_ads(project_root: pathlib.Path) -> None:
    """Runs the REAL main() → armed_spend(ledger_record) → gaql_search()
    path (R2-9). gaql_search()'s urlopen() call is inline (no separate
    transport helper) — hung via a module-level urlopen stub; a valid-
    looking OAuth token is stubbed so the run reaches the actual paid call."""
    _ads_project_root(project_root)
    os.chdir(project_root)
    mod = _load("google_ads_fetch_t089", "google-ads-fetch.py")
    mod.oauth_access_token = lambda: "fake-token"
    mod.urllib.request.urlopen = _hang_urlopen
    mod.env_status = lambda _platform: {"present": True, "missing": []}
    mod.ledger_preflight = lambda *_a, **_kw: (True, "ok")
    os.environ["GOOGLE_ADS_CUSTOMER_ID"] = "1234567890"
    os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"] = "fake-dev-token"
    mod.sys.argv = ["google-ads-fetch.py", "--report", "campaigns", "--live"]
    mod.main()


def _hang_urlopen(*_a, **_kw):
    print("STARTED", flush=True)
    time.sleep(60)
    raise AssertionError("hang() was not interrupted by the expected signal")


def run_keyso(out_dir: pathlib.Path) -> None:
    """keyso-fetch.py (review finding H, second gate) hardcodes its usage
    directory to `./seo/research/keyso` regardless of --out — chdir into
    out_dir so the write-ahead record lands under it, same as the other
    clients' out_dir contract."""
    os.chdir(out_dir)
    mod = _load("keyso_fetch_t089", "keyso-fetch.py")
    mod.urllib.request.urlopen = _hang_urlopen
    mod.call("fake-token", "/report/simple/keyword_dashboard", {"keyword": "x", "base": "msk"})


def run_competitor_discovery(out_dir: pathlib.Path) -> None:
    """competitor-discovery.py (review finding H) — same api.keys.so quota,
    same hardcoded `./seo/research/keyso` cache dir."""
    os.chdir(out_dir)
    mod = _load("competitor_discovery_t089", "competitor-discovery.py")
    mod.urllib.request.urlopen = _hang_urlopen
    mod.fetch_top("fake-token", "minvata", "msk", 60)


CLIENTS = {
    "dataforseo": run_dataforseo,
    "spyfu": run_spyfu,
    "google_nlp": run_google_nlp,
    "ads_apply": run_ads_apply,
    "yandex_direct": run_yandex_direct,
    "google_ads": run_google_ads,
    "keyso": run_keyso,
    "competitor_discovery": run_competitor_discovery,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("client", choices=sorted(CLIENTS))
    parser.add_argument("out_dir")
    args = parser.parse_args()
    CLIENTS[args.client](pathlib.Path(args.out_dir))
    print("FINISHED", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
