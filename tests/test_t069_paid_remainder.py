"""T-069 — the remainder of the money/quota class: places that used to spend
with no consent flag and/or no accounting (T-066 round-3 gate, R3-5).

Every probe here drives the REAL script as a subprocess and observes the
external boundary the spend crosses — a local HTTP listener for the
embedding endpoint, fake `codex`/`agy`/`curl`/`node` executables placed
first on PATH that log each invocation — never a mock of the script's own
functions. The proof of accounting is the JSONL line in
`seo/usage/usage-ledger.jsonl`, the proof of a refused spend is an empty
invocation log plus the documented exit code.

Positions covered (the packet's table):
  * rag-query.py / rag-index.py — same paid `/embeddings` call, same
    preflight, same record (the rag-index preflight used to be dead: no
    estimate metric → `usage-ledger check` rc=2 → always "blocked");
  * llm-cli-collect.sh, img-generate.sh, nw-cli.sh — mandatory `--live`
    plus a write-ahead ledger record before the external CLI runs;
  * writerzen-browser-collect.py — mandatory `--live`, preflight, record of
    reports actually started (from the runner's `actions`);
  * gsc-request-indexing-browser.py — record of clicks actually made (from
    the runner's `actions`; `--auto-click` was already the consent gate);
  * usage_ledger.finite_nonneg — R5-1, a 400-digit int no longer raises.

Fix round 1 (gate 2026-09-13, F-1/F-2 — the class grew a sixth time because
the executor's grep was not recursive and did not walk the sink's callers):
  * page-outline-v3.py --rag — the THIRD caller of `rag.search()` (one paid
    embedding per MVP page), now the same preflight/record as the other two;
  * scripts/knowledge/graphify-refresh.sh — LLM CLI probe + extraction, or
    `graphify extract` on API keys, with no flag at all; now `--live` +
    write-ahead like llm-cli-collect.sh.
"""

from __future__ import annotations

import http.server
import json
import os
import pathlib
import shutil
import socketserver
import stat
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.usage_ledger import finite_nonneg  # noqa: E402

LEDGER_REL = pathlib.Path("seo") / "usage" / "usage-ledger.jsonl"


def _ledger_lines(project: pathlib.Path) -> list[dict]:
    path = project / LEDGER_REL
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_exe(path: pathlib.Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class _FakeEmbeddings(http.server.BaseHTTPRequestHandler):
    """Local stand-in for an OpenAI-compatible `/embeddings` endpoint — every
    POST is one paid call; the server counts them."""

    hits = 0

    def do_POST(self) -> None:  # noqa: N802 — http.server API
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        type(self).hits += 1
        data = [{"embedding": [1.0, 0.0, 0.0]} for _ in payload.get("input") or []]
        body = json.dumps({"data": data}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # silence
        return


class FiniteNonnegOverflowTest(unittest.TestCase):
    def test_r5_1_huge_int_is_rejected_not_a_traceback(self) -> None:
        huge = int("1" + "0" * 400)  # `json.loads("1" + "0"*400)` gives exactly this
        with self.assertRaises(OverflowError):
            float(huge)  # the primitive the old check tripped over
        self.assertFalse(finite_nonneg(huge))
        self.assertTrue(finite_nonneg(5))
        self.assertFalse(finite_nonneg(float("nan")))


class _RagFixture(unittest.TestCase):
    """A project with one source pack and a local fake `/embeddings` server."""

    def setUp(self) -> None:
        try:
            import sqlite3
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        except Exception:  # pragma: no cover - platform without FTS5
            self.skipTest("sqlite3 built without FTS5")
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="t069-rag-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.project = self.tmp / "project"
        vector = self.project / "seo" / "research" / "vector"
        vector.mkdir(parents=True)
        (vector / "source_pack.jsonl").write_text(
            json.dumps({"topic": "вагонка", "summary": "Вагонка из кедра для бани.",
                        "provider": "perplexity"}, ensure_ascii=False) + "\n", encoding="utf-8")
        self.write_config(cap=None)
        _FakeEmbeddings.hits = 0
        self.server = socketserver.TCPServer(("127.0.0.1", 0), _FakeEmbeddings)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def write_config(self, cap: int | None) -> None:
        text = "project:\n  name: t069\n"
        if cap is not None:
            text += f"governance:\n  subscriptions:\n    embedding_api:\n      monthly_request_cap: {cap}\n"
        (self.project / "seo-cycle.yaml").write_text(text, encoding="utf-8")

    def env(self, embeddings: bool = True) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("EMBEDDING_")}
        if embeddings:
            env["EMBEDDING_API_URL"] = f"http://127.0.0.1:{self.port}"
            env["EMBEDDING_MODEL"] = "fake"
        return env

    def run_script(self, script: str, *args: str, cwd: pathlib.Path | None = None,
                   embeddings: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPTS / script), *args], cwd=cwd or self.project,
                              env=self.env(embeddings), text=True, capture_output=True, check=False)


class RagEmbeddingSymmetryTest(_RagFixture):
    """rag-index.py and rag-query.py on the same paid call."""

    def test_index_then_query_hit_the_endpoint_and_both_land_in_the_ledger(self) -> None:
        index = self.run_script("rag-index.py", "--write", "--format", "json")
        self.assertEqual(index.returncode, 0, index.stderr)
        report = json.loads(index.stdout)
        self.assertGreaterEqual(report["stats"]["embedded"], 1, report)
        hits_after_index = _FakeEmbeddings.hits
        self.assertGreaterEqual(hits_after_index, 1)
        rows = _ledger_lines(self.project)
        self.assertEqual([r["service"] for r in rows], ["embedding_api"], rows)
        self.assertEqual(rows[0]["category"], "llm")

        query = self.run_script("rag-query.py", "вагонка кедр", "--format", "json")
        self.assertEqual(query.returncode, 0, query.stderr)
        self.assertTrue(json.loads(query.stdout))
        self.assertEqual(_FakeEmbeddings.hits, hits_after_index + 1, "the query embedding is one paid call")
        rows = _ledger_lines(self.project)
        self.assertEqual(len(rows), 2, rows)
        self.assertEqual(rows[1]["service"], "embedding_api")
        self.assertEqual(rows[1]["metrics"], {"requests": 1.0})
        self.assertIn("rag-query", rows[1]["note"])

    def test_bm25_mode_never_touches_the_endpoint(self) -> None:
        self.assertEqual(self.run_script("rag-index.py", "--write").returncode, 0)
        before = _FakeEmbeddings.hits
        query = self.run_script("rag-query.py", "вагонка", "--mode", "bm25", "--format", "json")
        self.assertEqual(query.returncode, 0, query.stderr)
        self.assertEqual(_FakeEmbeddings.hits, before)
        self.assertEqual(len(_ledger_lines(self.project)), 1, "only rag-index recorded")

    def test_negative_control_cap_blocks_both_scripts_before_any_byte(self) -> None:
        # cap 1: rag-index (requests=1) still passes, and its own record
        # brings used to 1 — the query's estimate (1 more) projects 2 > 1.
        self.write_config(cap=1)
        index = self.run_script("rag-index.py", "--write", "--format", "json")
        self.assertEqual(index.returncode, 0, index.stderr)
        before = _FakeEmbeddings.hits
        query = self.run_script("rag-query.py", "вагонка", "--format", "json")
        self.assertEqual(query.returncode, 2, query.stdout)
        self.assertIn("preflight blocked", query.stderr)
        self.assertEqual(_FakeEmbeddings.hits, before, "a blocked query must not reach the endpoint")
        self.assertEqual(len(_ledger_lines(self.project)), 1)
        # Same stop, same exit code, same message shape on the index side.
        index2 = self.run_script("rag-index.py", "--write", "--format", "json")
        self.assertEqual(index2.returncode, 2, index2.stdout)
        self.assertIn("preflight blocked", index2.stderr)
        self.assertEqual(_FakeEmbeddings.hits, before)

    def test_global_query_outside_a_project_cannot_account_so_it_does_not_spend(self) -> None:
        self.assertEqual(self.run_script("rag-index.py", "--write").returncode, 0)
        outside = self.tmp / "outside"
        outside.mkdir()
        home = self.tmp / "home"
        (home / ".seo-cycle" / "rag").mkdir(parents=True)
        shutil.copy(self.project / "seo" / "rag.db", home / ".seo-cycle" / "rag" / "global.db")
        env = self.env()
        env["HOME"] = str(home)
        before = _FakeEmbeddings.hits
        explicit = subprocess.run([sys.executable, str(SCRIPTS / "rag-query.py"), "вагонка", "--global",
                                   "--mode", "hybrid"], cwd=outside, env=env, text=True,
                                  capture_output=True, check=False)
        self.assertEqual(explicit.returncode, 2, explicit.stdout)
        self.assertIn("seo-cycle.yaml not found", explicit.stderr)
        auto = subprocess.run([sys.executable, str(SCRIPTS / "rag-query.py"), "вагонка", "--global",
                               "--format", "json"], cwd=outside, env=env, text=True,
                              capture_output=True, check=False)
        self.assertEqual(auto.returncode, 0, auto.stderr)
        self.assertIn("falling back to BM25", auto.stderr)
        self.assertTrue(json.loads(auto.stdout))
        self.assertEqual(_FakeEmbeddings.hits, before, "no project → no accounting → no paid call")


class PageOutlineRagTest(_RagFixture):
    """F-1: `page-outline-v3.py --all-mvp --rag` — one paid embedding per
    MVP page, same contract as rag-query/rag-index."""

    PACKAGE = pathlib.Path("seo") / "research-package"

    def setUp(self) -> None:
        super().setUp()
        pkg = self.project / self.PACKAGE
        pkg.mkdir(parents=True)
        (pkg / "semantic-architecture-final.json").write_text(json.dumps({"clusters": [
            {"id": "vagonka", "name": "Вагонка из кедра", "primary_keyword": "вагонка кедр", "mvp": True,
             "intent": "commercial", "url": "/catalog/vagonka/", "page_type": "category"},
            {"id": "osina", "name": "Вагонка из осины", "primary_keyword": "вагонка осина", "mvp": True,
             "intent": "commercial", "url": "/catalog/osina/", "page_type": "category"},
        ]}, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(self.run_script("rag-index.py", "--write").returncode, 0)
        self.base_rows = len(_ledger_lines(self.project))  # rag-index's own record

    def outline(self, *extra: str, embeddings: bool = True) -> subprocess.CompletedProcess:
        return self.run_script("page-outline-v3.py", str(self.PACKAGE), "--all-mvp", "--rag", "--format", "json",
                               *extra, embeddings=embeddings)

    def test_rag_flag_embeds_one_call_per_page_and_records_them(self) -> None:
        before = _FakeEmbeddings.hits
        proc = self.outline()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["count"], 2)
        self.assertTrue(all(o.get("related_passages") for o in payload["outlines"]), "passages attached")
        self.assertEqual(_FakeEmbeddings.hits, before + 2, "one paid call per MVP page")
        rows = _ledger_lines(self.project)
        self.assertEqual(len(rows), self.base_rows + 1, rows)
        self.assertEqual((rows[-1]["service"], rows[-1]["category"], rows[-1]["metrics"]),
                         ("embedding_api", "llm", {"requests": 2.0}))
        self.assertIn("page-outline-v3", rows[-1]["note"])

    def test_negative_control_cap_blocks_rag_before_any_byte(self) -> None:
        self.write_config(cap=1)  # rag-index already used 1 → 2 more pages project 3 > 1
        before = _FakeEmbeddings.hits
        proc = self.outline()
        self.assertEqual(proc.returncode, 2, proc.stdout[:200])
        self.assertIn("preflight blocked", proc.stderr)
        self.assertEqual(_FakeEmbeddings.hits, before)
        self.assertEqual(len(_ledger_lines(self.project)), self.base_rows)

    def test_without_embeddings_env_rag_is_free_and_unrecorded(self) -> None:
        before = _FakeEmbeddings.hits
        proc = self.outline(embeddings=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(_FakeEmbeddings.hits, before)
        self.assertEqual(len(_ledger_lines(self.project)), self.base_rows)


class _ShellFixture(unittest.TestCase):
    """A project dir plus a bin dir first on PATH with logging fakes."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="t069-sh-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.log = self.tmp / "calls.log"
        (self.project / "seo-cycle.yaml").write_text("project:\n  name: t069\n", encoding="utf-8")

    def fake(self, name: str, body: str) -> None:
        # One line per invocation even when an argument (the LLM prompt)
        # spans many lines: %q renders newlines as $'\n'.
        _write_exe(self.bin / name, f'printf \'%s %q\\n\' "{name}" "$*" >> "{self.log}"\n' + body)

    def calls(self) -> list[str]:
        # errors="replace": bash's %q under a C locale may emit raw bytes for
        # a non-ASCII prompt; only the leading command word matters here.
        return self.log.read_text(encoding="utf-8", errors="replace").splitlines() if self.log.exists() else []

    def run_cmd(self, *cmd: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["PATH"] = f"{self.bin}{os.pathsep}{env.get('PATH', '')}"
        env["HOME"] = str(self.home)
        env.pop("SEO_RUNTIME", None)
        for key in list(env):
            if key.startswith("CODEX_"):
                env.pop(key)
        env.update(env_extra or {})
        return subprocess.run(list(cmd), cwd=self.project, env=env, text=True, capture_output=True, check=False)

    def set_cap(self, yaml_block: str) -> None:
        (self.project / "seo-cycle.yaml").write_text("project:\n  name: t069\n" + yaml_block, encoding="utf-8")


class LlmCliCollectTest(_ShellFixture):
    SCRIPT = str(SCRIPTS / "llm-cli-collect.sh")

    def setUp(self) -> None:
        super().setUp()
        self.fake("agy", 'echo "agy output"\n')
        self.fake("codex", 'echo "codex output"\n')

    def test_without_live_nothing_runs_exit_3(self) -> None:
        proc = self.run_cmd("bash", self.SCRIPT, "тема")
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("--live", proc.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(_ledger_lines(self.project), [])

    def test_with_live_both_clis_run_after_one_writeahead_record(self) -> None:
        proc = self.run_cmd("bash", self.SCRIPT, "--live", "тема")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        names = sorted(line.split()[0] for line in self.calls())
        self.assertEqual(names, ["agy", "codex"])
        rows = _ledger_lines(self.project)
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["service"], "llm_cli")
        self.assertEqual(rows[0]["category"], "llm")
        self.assertEqual(rows[0]["metrics"], {"requests": 2.0})

    def test_negative_control_ledger_block_stops_before_any_cli(self) -> None:
        self.set_cap("governance:\n  subscriptions:\n    llm_cli:\n      monthly_request_cap: 1\n")
        proc = self.run_cmd("bash", self.SCRIPT, "--live", "тема")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("usage-ledger", proc.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(_ledger_lines(self.project), [], "record --fail-on-block writes nothing when blocked")

    def test_no_project_config_is_a_stop_not_a_silent_run(self) -> None:
        (self.project / "seo-cycle.yaml").unlink()
        proc = self.run_cmd("bash", self.SCRIPT, "--live", "тема")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.calls(), [])


class ImgGenerateTest(_ShellFixture):
    SCRIPT = str(SCRIPTS / "img-generate.sh")

    def setUp(self) -> None:
        super().setUp()
        # `timeout` is GNU coreutils — absent on a stock macOS; the gate sits
        # before it, but the live path needs it: shim it to just exec.
        _write_exe(self.bin / "timeout", 'shift\nexec "$@"\n')
        target = self.project / "incoming" / "hero.png"
        self.fake("codex", f'mkdir -p "{target.parent}"\necho png > "{target}"\necho "DONE: {target}"\n')

    def test_without_live_exit_3_and_codex_not_run(self) -> None:
        proc = self.run_cmd("bash", self.SCRIPT, "a cedar sauna", "hero.png")
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("--live", proc.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.project / "incoming" / "hero.png").exists())
        self.assertEqual(_ledger_lines(self.project), [])

    def test_with_live_codex_runs_after_writeahead_record(self) -> None:
        proc = self.run_cmd("bash", self.SCRIPT, "a cedar sauna", "hero.png", "--live")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(proc.stdout.startswith("OK:"), proc.stdout)
        self.assertEqual([line.split()[0] for line in self.calls()], ["codex"])
        rows = _ledger_lines(self.project)
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual((rows[0]["service"], rows[0]["category"], rows[0]["metrics"]),
                         ("codex", "llm", {"requests": 1.0}))
        self.assertIn("hero.png", rows[0]["note"])

    def test_codex_runtime_mode_prints_instruction_and_spends_nothing_without_live(self) -> None:
        proc = self.run_cmd("bash", self.SCRIPT, "a cedar sauna", "hero.png", env_extra={"SEO_RUNTIME": "codex"})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("CODEX_NATIVE_IMAGE", proc.stdout)
        self.assertEqual(self.calls(), [])
        self.assertEqual(_ledger_lines(self.project), [])

    def test_negative_control_ledger_block_stops_before_codex(self) -> None:
        self.set_cap("governance:\n  subscriptions:\n    codex:\n      monthly_request_cap: 1\n")
        first = self.run_cmd("bash", self.SCRIPT, "--live", "a", "hero.png")
        self.assertEqual(first.returncode, 0, first.stderr)
        (self.project / "incoming" / "hero.png").unlink()
        second = self.run_cmd("bash", self.SCRIPT, "--live", "a", "hero.png")
        self.assertEqual(second.returncode, 1, second.stdout + second.stderr)
        self.assertEqual(len(self.calls()), 1, "second run must not reach codex")
        self.assertEqual(len(_ledger_lines(self.project)), 1)


class GraphifyRefreshTest(_ShellFixture):
    """F-2: `scripts/knowledge/graphify-refresh.sh` — LLM CLI probe/extract or
    `graphify extract` on API keys must not start without --live."""

    SCRIPT = str(SCRIPTS / "knowledge" / "graphify-refresh.sh")

    def setUp(self) -> None:
        super().setUp()
        # graphify present (so the LLM branch is reachable); agy present and
        # "healthy"; both log every invocation. `graphify` itself is a fake
        # python-shebang script so graphify_python() resolves to sys.executable.
        (self.bin / "graphify").write_text(
            f"#!{sys.executable}\nimport sys\nopen({str(self.log)!r}, 'a').write('graphify ' + ' '.join(sys.argv[1:]) + '\\n')\n",
            encoding="utf-8")
        (self.bin / "graphify").chmod(0o755)
        self.fake("agy", 'echo "готов"\n')
        # Keep the corpus/wiki stage cheap: point the wiki root inside the project.
        self.env_base = {"SEO_CYCLE_PROJECT_ROOT": str(self.project), "GRAPHIFY_GEMINI_CLI": "0"}
        for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "KIMI_API_KEY",
                    "GRAPHIFY_BACKEND", "GRAPHIFY_LIVE"):
            os.environ.pop(key, None)

    def llm_calls(self) -> list[str]:
        return [line for line in self.calls() if line.startswith(("agy", "graphify extract"))]

    def test_plain_run_with_llm_path_reachable_exits_3_without_any_llm_call(self) -> None:
        proc = self.run_cmd("bash", self.SCRIPT, env_extra=self.env_base)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("--live", proc.stderr)
        self.assertEqual(self.llm_calls(), [], self.calls())
        self.assertEqual(_ledger_lines(self.project), [])

    def test_api_key_backend_is_also_gated(self) -> None:
        # No CLI requested at all; an API key alone makes `graphify extract` reachable.
        env = {**self.env_base, "GRAPHIFY_ANTIGRAVITY_CLI": "0", "OPENAI_API_KEY": "fake-not-real"}
        proc = self.run_cmd("bash", self.SCRIPT, env_extra=env)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertEqual(self.llm_calls(), [])

    def test_live_writes_ahead_then_probes_and_builds(self) -> None:
        proc = self.run_cmd("bash", self.SCRIPT, "--live", env_extra=self.env_base)
        # The build itself needs the real `graphify` Python package (not a
        # test dependency): what is under test is that the gate opened, the
        # write-ahead landed and the CLI probe ran — not the graph outcome.
        self.assertNotEqual(proc.returncode, 3, proc.stderr)
        agy = [line for line in self.calls() if line.startswith("agy")]
        self.assertGreaterEqual(len(agy), 1, self.calls())
        rows = _ledger_lines(self.project)
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual((rows[0]["service"], rows[0]["category"], rows[0]["metrics"]),
                         ("graphify", "llm", {"requests": 1.0}))

    def test_negative_control_ledger_block_stops_before_probe(self) -> None:
        self.set_cap("governance:\n  subscriptions:\n    graphify:\n      monthly_request_cap: 1\n")
        first = self.run_cmd("bash", self.SCRIPT, "--live", env_extra=self.env_base)
        self.assertNotEqual(first.returncode, 3, first.stderr)
        self.assertEqual(len(_ledger_lines(self.project)), 1)
        n = len(self.llm_calls())
        self.assertGreaterEqual(n, 1)
        second = self.run_cmd("bash", self.SCRIPT, "--live", env_extra=self.env_base)
        self.assertEqual(second.returncode, 1, second.stdout + second.stderr)
        self.assertEqual(len(self.llm_calls()), n, "blocked run must not probe the CLI")

    def test_local_fallback_without_llm_path_needs_no_flag(self) -> None:
        env = {**self.env_base, "GRAPHIFY_ANTIGRAVITY_CLI": "0"}
        proc = self.run_cmd("bash", self.SCRIPT, env_extra=env)
        # Not gated (rc 3) — the local graph itself needs the real `graphify`
        # package, whose absence is not what this test is about.
        self.assertNotEqual(proc.returncode, 3, proc.stderr)
        self.assertEqual(self.llm_calls(), [])
        self.assertEqual(_ledger_lines(self.project), [])


@unittest.skipUnless(shutil.which("jq") and shutil.which("curl"), "nw-cli.sh needs jq and curl")
class NwCliTest(_ShellFixture):
    SCRIPT = str(SCRIPTS / "nw-cli.sh")

    def setUp(self) -> None:
        super().setUp()
        self.fake("curl", 'echo "{}"\n')  # shadows the real curl: every call is logged, none leaves

    def env(self) -> dict[str, str]:
        return {"NEURON_API_KEY": "test-not-a-real-key"}

    def test_new_without_live_sends_nothing_exit_3(self) -> None:
        proc = self.run_cmd("bash", self.SCRIPT, "new", "proj", "kw", env_extra=self.env())
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("--live", proc.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(_ledger_lines(self.project), [])

    def test_new_with_live_records_one_analysis_then_calls(self) -> None:
        proc = self.run_cmd("bash", self.SCRIPT, "--live", "new", "proj", "kw", env_extra=self.env())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        calls = self.calls()
        self.assertEqual(len(calls), 1, calls)
        self.assertIn("/new-query", calls[0])
        rows = _ledger_lines(self.project)
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual((rows[0]["service"], rows[0]["metrics"]), ("neuronwriter", {"content_writer": 1.0}))

    def test_plagiarism_with_live_records_one_check(self) -> None:
        env = {**self.env(), "NW_PLAGIARISM_PATH": "/account-path"}
        blocked = self.run_cmd("bash", self.SCRIPT, "plagiarism", "q1", env_extra=env)
        self.assertEqual(blocked.returncode, 3)
        self.assertEqual(self.calls(), [])
        proc = self.run_cmd("bash", self.SCRIPT, "--live", "plagiarism", "q1", env_extra=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(len(self.calls()), 1)
        rows = _ledger_lines(self.project)
        self.assertEqual(rows[-1]["metrics"], {"plagiarism_checks": 1.0})

    def test_read_only_commands_need_no_flag_and_no_ledger(self) -> None:
        proc = self.run_cmd("bash", self.SCRIPT, "projects", env_extra=self.env())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(_ledger_lines(self.project), [])

    def test_negative_control_content_writer_cap_blocks_before_curl(self) -> None:
        self.set_cap("governance:\n  subscriptions:\n    neuronwriter:\n      monthly_content_writer_limit: 1\n")
        first = self.run_cmd("bash", self.SCRIPT, "--live", "new", "proj", "kw", env_extra=self.env())
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_cmd("bash", self.SCRIPT, "--live", "new", "proj", "kw2", env_extra=self.env())
        self.assertEqual(second.returncode, 1, second.stdout + second.stderr)
        self.assertEqual(len(self.calls()), 1, "the blocked second run must not reach curl")


class _BrowserFixture(_ShellFixture):
    """Fake `node` on PATH that writes the runner's result file from a
    canned payload — the wrapper's only view of what happened in the
    browser."""

    def setUp(self) -> None:
        super().setUp()
        self.deps = self.tmp / "deps"
        (self.deps / "node_modules" / "playwright-core").mkdir(parents=True)
        (self.deps / "node_modules" / "playwright-core" / "package.json").write_text("{}", encoding="utf-8")
        self.payload = self.tmp / "payload.json"

    def fake_node(self) -> None:
        self.fake("node", (
            'out=""\nwhile [ $# -gt 0 ]; do\n  if [ "$1" = "--result-file" ]; then out="$2"; shift; fi\n  shift\ndone\n'
            f'cp "{self.payload}" "$out"\ncat "$out"\n'
        ))


class GscRequestIndexingAccountingTest(_BrowserFixture):
    SCRIPT = str(SCRIPTS / "gsc-request-indexing-browser.py")

    def setUp(self) -> None:
        super().setUp()
        self.queue = self.project / "queue.csv"
        self.queue.write_text(
            "url,priority,priority_score\n"
            "https://example.com/a,P0,10\nhttps://example.com/b,P0,9\nhttps://example.com/c,P1,8\n",
            encoding="utf-8")
        self.payload.write_text(json.dumps({
            "status": "finished", "auto_click": True,
            "results": [
                {"url": "https://example.com/a", "status": "submitted_or_requested", "actions": ["request:Request indexing"]},
                {"url": "https://example.com/b", "status": "submitted_or_requested", "actions": []},  # already submitted — no click
                {"url": "https://example.com/c", "status": "submitted_or_requested",
                 "actions": ["live_test:Test live URL", "request_after_live:Request indexing"]},
            ],
        }), encoding="utf-8")
        self.fake_node()

    def run_wrapper(self, *extra: str) -> subprocess.CompletedProcess:
        return self.run_cmd(sys.executable, self.SCRIPT, str(self.project / "seo-cycle.yaml"),
                        "--site-url", "sc-domain:example.com", "--queue-file", str(self.queue),
                        "--node-deps-dir", str(self.deps), "--format", "json", *extra)

    def test_clicks_are_counted_from_runner_actions_not_from_status(self) -> None:
        proc = self.run_wrapper("--auto-click")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["summary"]["submitted_or_requested"], 3)
        self.assertEqual(report["summary"]["quota_clicks"], 2, report["summary"])
        self.assertTrue(report["summary"]["quota_clicks_recorded"])
        rows = _ledger_lines(self.project)
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual((rows[0]["service"], rows[0]["category"], rows[0]["metrics"]),
                         ("gsc_request_indexing", "browser", {"requests": 2.0}))

    def test_without_auto_click_nothing_is_recorded(self) -> None:
        self.payload.write_text(json.dumps({
            "status": "manual_action_required", "auto_click": False,
            "results": [{"url": "https://example.com/a", "status": "manual_action_required", "actions": []}],
        }), encoding="utf-8")
        proc = self.run_wrapper()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["summary"]["quota_clicks"], 0)
        self.assertEqual(_ledger_lines(self.project), [])


class WriterzenBrowserConsentTest(_BrowserFixture):
    SCRIPT = str(SCRIPTS / "writerzen-browser-collect.py")

    def setUp(self) -> None:
        super().setUp()
        self.payload.write_text(json.dumps({
            "provider": "writerzen", "status": "no_downloads",
            "results": [
                {"report": "topic_discovery", "status": "download_not_captured",
                 "actions": ["seed_filled", "report_started", "export_button_not_found"]},
                {"report": "keyword_explorer", "status": "download_not_captured",
                 "actions": ["seed_input_not_found"]},  # nothing started — no credits
            ],
            "downloads": [],
        }), encoding="utf-8")
        self.fake_node()

    def run_wrapper(self, *extra: str) -> subprocess.CompletedProcess:
        return self.run_cmd(sys.executable, self.SCRIPT, str(self.project / "seo-cycle.yaml"),
                        "--topic", "osb", "--reports", "topic_discovery,keyword_explorer",
                        "--profile-dir", str(self.tmp / "profile"), "--node-deps-dir", str(self.deps),
                        "--no-import-after", "--format", "json", *extra)

    def test_plain_run_is_refused_exit_3_browser_never_opened(self) -> None:
        proc = self.run_wrapper()
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "consent_required")
        self.assertEqual(self.calls(), [], "node (the browser) must not start without --live")
        self.assertEqual(_ledger_lines(self.project), [])

    def test_dry_run_still_only_plans(self) -> None:
        proc = self.run_wrapper("--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "planned")
        self.assertEqual(self.calls(), [])

    def test_live_run_records_reports_actually_started(self) -> None:
        proc = self.run_wrapper("--live")
        self.assertEqual([line.split()[0] for line in self.calls()], ["node"])
        report = json.loads(proc.stdout)
        self.assertEqual(report["browser"]["credits_reports_started"], 1, report["browser"])
        self.assertTrue(report["browser"]["credits_recorded"])
        rows = _ledger_lines(self.project)
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual((rows[0]["service"], rows[0]["category"], rows[0]["metrics"]),
                         ("writerzen", "paid_api", {"requests": 1.0}))

    def test_negative_control_cap_blocks_before_the_browser_opens(self) -> None:
        self.set_cap("governance:\n  subscriptions:\n    writerzen:\n      monthly_request_cap: 1\n")
        proc = self.run_wrapper("--live")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["browser"]["status"], "ledger_blocked", report)
        self.assertEqual(self.calls(), [], "a blocked preflight must not launch node")


if __name__ == "__main__":
    unittest.main()
