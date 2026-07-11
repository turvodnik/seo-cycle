#!/usr/bin/env python3
"""Local agency dashboard: the visual web UI over the seo-cycle toolchain.

One stdlib HTTP server + one self-contained page. What you get in the browser:
project switcher (from config/projects-registry.yaml), agency portfolio
overview, per-project view (journey stage, ranking progress with deltas,
self-assessment scorecards), approvals with one-click approve/reject, a
command panel (whitelisted safe tools only — nothing paid, nothing --live),
client reports, and provider auth status.

Security model:
- binds 127.0.0.1 by default; a per-process random token guards every API call;
- optional password (SEO_CYCLE_DASHBOARD_PASSWORD env or --ask-password):
  the login form exchanges it for the token; REQUIRED for non-local --host;
- secrets never leave env files: auth status shows sources only;
- file serving is restricted to known projects' seo/ artifacts.

Usage:
  python3 scripts/webapp.py --open                 # start + open the browser
  seo-cycle web --open
  python3 scripts/webapp.py --port 8899 --ask-password
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import pathlib
import secrets
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for
from seo_cycle_core.env_profile import env_chain
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("webapp")

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS_DIR.parent
REGISTRY = SKILL_ROOT / "config" / "projects-registry.yaml"

FILE_EXTENSIONS = {".md", ".html", ".pdf", ".json", ".csv", ".txt"}
STDOUT_LIMIT = 120_000

# Only safe tools: read-only or writing local artifacts. Nothing --live, nothing paid,
# nothing publishing — those stay behind approvals and the CLI by design.
COMMANDS: dict[str, dict[str, Any]] = {
    "journey": {"label": "Статус проекта (journey)", "group": "Обзор",
                 "script": "project-journey.py", "args": [],
                 "hint": "Текущая стадия, блокеры, план действий"},
    "db-sync": {"label": "Обновить базу (db-sync)", "group": "Данные",
                 "script": "db-sync.py", "args": [],
                 "hint": "Пересобрать seo.db из артефактов"},
    "pulse": {"label": "Снять свежий срез (pulse)", "group": "Данные",
               "script": "pulse.py", "args": [],
               "hint": "Вебмастер → снапшот → база → прогресс + свежесть/алерты", "timeout": 600},
    "pulse-global": {"label": "Пульс всего портфеля", "group": "Данные",
               "script": "pulse.py", "args": ["--global"],
               "hint": "pulse по всем active-проектам реестра (как daily-джоб)", "timeout": 1200},
    "progress": {"label": "Прогресс позиций + HTML", "group": "Обзор",
                  "script": "position-progress.py", "args": ["--write", "--html"],
                  "hint": "Срезы, движения, циклы качества"},
    "portfolio": {"label": "Портфель по всем проектам", "group": "Обзор",
                   "script": "position-progress.py", "args": ["--global", "--write", "--html"],
                   "hint": "Сводка агентства → ~/.seo-cycle/reports"},
    "dashboard": {"label": "Месячный дашборд", "group": "Обзор",
                   "script": "monthly-dashboard.py", "args": [],
                   "hint": "Очередь, approvals, снапшоты"},
    "forecast": {"label": "Прогноз трафика", "group": "Стратегия",
                  "script": "seo-forecast.py", "args": ["--write"],
                  "hint": "CTR-модель: сценарии и потенциал кластеров"},
    "kpi": {"label": "KPI: план vs факт", "group": "Стратегия",
             "script": "kpi-contract.py", "args": ["--write"],
             "hint": "Сверка целей месяца, эскалация при провале"},
    "budget": {"label": "Бюджет-микс SEO+PPC", "group": "Стратегия",
                "script": "budget-mix-planner.py", "args": ["--write"],
                "hint": "Раскладка бюджета по лидам за рубль"},
    "client-report": {"label": "Отчёт клиенту (md+HTML)", "group": "Отчёты",
                       "script": "client-report.py", "args": ["--write"],
                       "hint": "White-label сводка за период"},
    "client-report-pdf": {"label": "Отчёт клиенту + PDF", "group": "Отчёты",
                           "script": "client-report.py", "args": ["--write", "--pdf"],
                           "hint": "То же + печать в PDF через Chrome", "timeout": 300},
    "ads-analytics": {"label": "Аналитика рекламы (кэш)", "group": "Реклама",
                       "script": "ads-analytics.py", "args": ["--write"],
                       "hint": "Кросс-правила SEO+PPC по последним выгрузкам"},
    "yml-feed": {"label": "YML-фид из WooCommerce", "group": "Данные",
                  "script": "woo-yml-feed.py", "args": ["--live", "--write"],
                  "hint": "Товарный фид для Яндекса из Woo REST (read-only)", "timeout": 300},
    "rag-index": {"label": "Обновить RAG-индекс", "group": "Данные",
                   "script": "rag-index.py", "args": ["--write"],
                   "hint": "Инкрементальная индексация артефактов"},
    "cohorts": {"label": "Когорты Метрики", "group": "Данные",
                 "script": "metrika-cohorts.py", "args": ["--write"],
                 "hint": "Возврат/конверсия по неделе первого визита (offline)"},
    "site-crawl": {"label": "Обойти сайт (краулер)", "group": "Техничка",
                    "script": "site-crawl.py", "args": ["--live", "--write"],
                    "hint": "BFS до 300 страниц: битые ссылки, дубли title, noindex", "timeout": 600},
    "structure-map": {"label": "Карта структуры сайта", "group": "Техничка",
                       "script": "structure-map.py", "args": ["--write"],
                       "hint": "Визуальное дерево разделов → Отчёты"},
    "serp-intel": {"label": "SERP-интеллект", "group": "Данные",
                    "script": "serp-intel.py", "args": ["--write"],
                    "hint": "Overlap-кластеры, фичи выдачи, кандидаты сущностей (offline)"},
    "link-liveness": {"label": "Живость внешних источников", "group": "Техничка",
                       "script": "link-liveness.py", "args": ["--live", "--write"],
                       "hint": "HEAD-проверка ссылок из статей (E-E-A-T)", "timeout": 300},
    "validate": {"label": "Проверить конфиг", "group": "Сервис",
                  "script": "validate-config.py", "args": [],
                  "hint": "seo-cycle.yaml: ошибки и подсказки"},
    "doctor": {"label": "Doctor: health провайдеров", "group": "Сервис",
                "script": "seo_cycle_cli.py", "args": ["doctor"],
                "hint": "Сводная проверка config/journey/интеграций", "timeout": 180},
    "triggers": {"label": "Триггеры итерации", "group": "Сервис",
                  "script": "triggers-eval.py", "args": [],
                  "hint": "Просадки, устаревшие факты, refresh-кандидаты"},
}


def load_projects() -> list[dict[str, Any]]:
    """Known projects: the registry plus the current directory if it is one."""
    projects: list[dict[str, Any]] = []
    seen: set[str] = set()
    cwd_cfg = find_config(pathlib.Path.cwd())
    if cwd_cfg:
        root = project_root_for(cwd_cfg)
        name = (load_yaml(cwd_cfg).get("project") or {}).get("name") or root.name
        projects.append({"name": str(name), "path": str(root)})
        seen.add(str(root))
    if REGISTRY.exists():
        for item in (load_yaml(REGISTRY).get("projects") or []):
            if not isinstance(item, dict) or not item.get("path"):
                continue
            path = str(pathlib.Path(str(item["path"])).expanduser())
            if path in seen:
                continue
            seen.add(path)
            projects.append({"name": str(item.get("name") or pathlib.Path(path).name),
                             "path": path, "status": item.get("status", "active")})
    return projects


def run_tool(project: pathlib.Path, script: str, args: list[str], timeout: int = 120) -> dict[str, Any]:
    path = SCRIPTS_DIR / script
    if not path.exists():
        return {"ok": False, "rc": -1, "stdout": "", "stderr": f"script not found: {script}"}
    try:
        proc = subprocess.run(
            [sys.executable, str(path), *args],
            cwd=project, env=env_chain(project), text=True, capture_output=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "rc": -1, "stdout": "", "stderr": f"timeout {timeout}s"}
    return {
        "ok": proc.returncode == 0,
        "rc": proc.returncode,
        "stdout": proc.stdout[-STDOUT_LIMIT:],
        "stderr": proc.stderr[-8000:],
    }


def tool_json(project: pathlib.Path, script: str, args: list[str], timeout: int = 120) -> Any:
    result = run_tool(project, script, args, timeout)
    if not result["ok"]:
        return {"error": result["stderr"] or f"rc={result['rc']}"}
    try:
        return json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {"error": "non-JSON output", "raw": result["stdout"][:2000]}


def list_reports(project: pathlib.Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    candidates = [
        *(project / "seo" / "reports").glob("*.*"),
        project / "seo" / "monthly-dashboard.md",
        project / "seo" / "ads" / "ads-analytics.md",
        *(project / "seo" / "strategy").glob("*.md"),
        *(project / "seo" / "setup").glob("latest-project-journey.md"),
        *(project / "seo" / "crawl").glob("*.md"),
        *(project / "seo" / "crawl").glob("*.html"),
        *(project / "seo" / "research-package").glob("serp-intel.md"),
    ]
    for path in candidates:
        if path.exists() and path.suffix.lower() in FILE_EXTENSIONS:
            reports.append({
                "file": str(path.relative_to(project)),
                "name": path.name,
                "mtime": int(path.stat().st_mtime),
                "size": path.stat().st_size,
            })
    reports.sort(key=lambda item: -item["mtime"])
    return reports


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "seo-cycle-dashboard"

    # --- plumbing ---------------------------------------------------------
    def log_message(self, fmt: str, *args: Any) -> None:
        log.info("http %s", fmt % args)

    @property
    def state(self) -> dict[str, Any]:
        return self.server.dashboard_state  # type: ignore[attr-defined]

    def send_json(self, payload: Any, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def query(self) -> dict[str, str]:
        parsed = urllib.parse.urlparse(self.path)
        return {key: values[0] for key, values in urllib.parse.parse_qs(parsed.query).items()}

    def route(self) -> str:
        return urllib.parse.urlparse(self.path).path

    def authorized(self) -> bool:
        token = self.headers.get("X-Auth-Token") or self.query().get("token") or ""
        return secrets.compare_digest(token, self.state["token"])

    def project_from_query(self) -> pathlib.Path | None:
        raw = self.query().get("project", "")
        allowed = {item["path"] for item in self.state["projects"]}
        if raw in allowed:
            return pathlib.Path(raw)
        return None

    def body_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            return data if isinstance(data, dict) else {}
        except (ValueError, json.JSONDecodeError):
            return {}

    # --- GET ---------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        route = self.route()
        if route == "/":
            body = PAGE_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if route == "/api/ping":
            self.send_json({"ok": True, "needs_password": bool(self.state["password"]),
                            "version": (SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip()})
            return
        if not route.startswith(("/api/", "/files")):
            self.send_json({"error": "not found"}, 404)
            return
        if not self.authorized():
            self.send_json({"error": "unauthorized"}, 401)
            return

        if route == "/api/projects":
            self.send_json(self.state["projects"])
        elif route == "/api/portfolio":
            self.send_json(tool_json(SKILL_ROOT, "position-progress.py", ["--global", "--format", "json"]))
        elif route == "/api/commands":
            self.send_json([
                {"id": key, **{k: v for k, v in spec.items() if k in ("label", "group", "hint")}}
                for key, spec in COMMANDS.items()
            ])
        elif route == "/api/summary":
            project = self.project_from_query()
            if not project:
                self.send_json({"error": "unknown project"}, 400)
                return
            self.send_json({
                "journey": tool_json(project, "project-journey.py", ["--format", "json"]),
                "progress": tool_json(project, "position-progress.py", ["--format", "json"]),
                "scorecards": tool_json(project, "scorecard.py", ["show", "--format", "json"]),
                "dashboard": tool_json(project, "monthly-dashboard.py", ["--json"]),
            })
        elif route == "/api/reports":
            project = self.project_from_query()
            if not project:
                self.send_json({"error": "unknown project"}, 400)
                return
            self.send_json(list_reports(project))
        elif route == "/api/auth-status":
            project = self.project_from_query()
            if not project:
                self.send_json({"error": "unknown project"}, 400)
                return
            self.send_json(tool_json(project, "auth-assistant.py", ["list", "--format", "json"]))
        elif route == "/files":
            self.serve_file()
        else:
            self.send_json({"error": "not found"}, 404)

    def serve_file(self) -> None:
        project = self.project_from_query()
        rel = self.query().get("file", "")
        if not project or not rel:
            self.send_json({"error": "project and file required"}, 400)
            return
        target = (project / rel).resolve()
        try:
            target.relative_to(project.resolve())
        except ValueError:
            self.send_json({"error": "forbidden"}, 403)
            return
        if target.suffix.lower() not in FILE_EXTENSIONS or not target.exists():
            self.send_json({"error": "not found"}, 404)
            return
        content_types = {".html": "text/html; charset=utf-8", ".pdf": "application/pdf",
                         ".json": "application/json; charset=utf-8", ".csv": "text/csv; charset=utf-8"}
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_types.get(target.suffix.lower(), "text/plain; charset=utf-8"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # --- POST ---------------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        route = self.route()
        if route == "/api/login":
            data = self.body_json()
            password = self.state["password"]
            if not password:
                self.send_json({"token": self.state["token"]})
                return
            if secrets.compare_digest(str(data.get("password") or ""), password):
                self.send_json({"token": self.state["token"]})
            else:
                self.send_json({"error": "wrong password"}, 401)
            return
        if not self.authorized():
            self.send_json({"error": "unauthorized"}, 401)
            return
        data = self.body_json()
        project_raw = str(data.get("project") or "")
        allowed = {item["path"] for item in self.state["projects"]}
        if project_raw not in allowed:
            self.send_json({"error": "unknown project"}, 400)
            return
        project = pathlib.Path(project_raw)

        if route == "/api/run":
            spec = COMMANDS.get(str(data.get("command")))
            if not spec:
                self.send_json({"error": "unknown command"}, 400)
                return
            log.info("run %s for %s", data.get("command"), project)
            result = run_tool(project, spec["script"], list(spec["args"]), spec.get("timeout", 120))
            self.send_json(result)
        elif route == "/api/ticket":
            action = str(data.get("action") or "")
            ticket = str(data.get("id") or "").strip()
            if action not in {"approve", "reject"} or not ticket or not ticket.isalnum():
                self.send_json({"error": "action approve|reject and alnum id required"}, 400)
                return
            result = run_tool(project, "approval-gate.py", [action, ticket])
            self.send_json(result)
        else:
            self.send_json({"error": "not found"}, 404)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the browser after start")
    parser.add_argument("--ask-password", action="store_true",
                        help="Prompt for a login password (otherwise SEO_CYCLE_DASHBOARD_PASSWORD env)")
    args = parser.parse_args(argv)

    password = os.environ.get("SEO_CYCLE_DASHBOARD_PASSWORD", "")
    if args.ask_password:
        password = getpass.getpass("Пароль дашборда: ")
    if args.host not in {"127.0.0.1", "localhost"} and not password:
        print("ERROR: внешний --host требует пароль (--ask-password или SEO_CYCLE_DASHBOARD_PASSWORD).",
              file=sys.stderr)
        return 2

    projects = load_projects()
    token = secrets.token_hex(16)
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    server.dashboard_state = {  # type: ignore[attr-defined]
        "token": token,
        "password": password,
        "projects": projects,
    }
    url = f"http://{args.host}:{server.server_address[1]}/"
    if not password:
        url += f"?token={token}"
    print(f"✓ SEO Cycle dashboard: {url}", file=sys.stderr)
    print(f"  Проектов: {len(projects)} · пароль: {'да' if password else 'нет (localhost token)'}"
          f" · Ctrl-C — остановить", file=sys.stderr)
    if args.open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлен", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------
# The page. Self-contained: no external assets, dark agency theme.
# --------------------------------------------------------------------------
PAGE_HTML = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SEO Cycle — агентство</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--panel2:#1e222b;--text:#e6e9ef;--muted:#8b93a3;
--accent:#3ecf8e;--warn:#e8b23e;--bad:#e05f5f;--line:#262b36;--radius:12px}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 -apple-system,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text)}
header{display:flex;align-items:center;gap:16px;padding:14px 22px;background:var(--panel);
border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5;flex-wrap:wrap}
header h1{font-size:17px;margin:0;letter-spacing:.3px}
header h1 b{color:var(--accent)}
select,button,input{font:inherit;color:var(--text);background:var(--panel2);border:1px solid var(--line);
border-radius:8px;padding:7px 12px;outline:none}
button{cursor:pointer}
button:hover{border-color:var(--accent)}
button.primary{background:var(--accent);color:#08130d;border:none;font-weight:600}
nav{display:flex;gap:6px;flex-wrap:wrap}
nav button{background:transparent;border:none;color:var(--muted);padding:8px 14px;border-radius:8px}
nav button.active{background:var(--panel2);color:var(--text)}
main{max-width:1180px;margin:22px auto;padding:0 22px}
.grid{display:grid;gap:14px}
.cards{grid-template-columns:repeat(auto-fit,minmax(180px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px}
.card .num{font-size:26px;font-weight:700}
.card .delta{font-size:13px;margin-left:6px}
.card .label{color:var(--muted);font-size:13px;margin-top:2px}
.up{color:var(--accent)} .down{color:var(--bad)} .muted{color:var(--muted)}
h2{font-size:15px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;margin:26px 0 10px}
table{width:100%;border-collapse:collapse;background:var(--panel);border-radius:var(--radius);overflow:hidden}
th,td{padding:10px 14px;text-align:left;border-bottom:1px solid var(--line);font-size:14px}
th{color:var(--muted);font-weight:500;font-size:12.5px;text-transform:uppercase;letter-spacing:.6px}
tr:last-child td{border-bottom:none}
tr.click{cursor:pointer} tr.click:hover td{background:var(--panel2)}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12.5px;border:1px solid var(--line)}
.badge.ok{color:var(--accent);border-color:var(--accent)}
.badge.warn{color:var(--warn);border-color:var(--warn)}
.badge.bad{color:var(--bad);border-color:var(--bad)}
.bar{height:10px;border-radius:4px;background:var(--accent);min-width:2px;display:inline-block;vertical-align:middle}
.cmds{grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}
.cmd{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:14px;cursor:pointer}
.cmd:hover{border-color:var(--accent)}
.cmd .t{font-weight:600}.cmd .h{color:var(--muted);font-size:13px;margin-top:4px}
.cmd .g{font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:.5px}
pre{background:#0a0c10;border:1px solid var(--line);border-radius:var(--radius);padding:14px;
overflow:auto;font-size:13px;max-height:420px;white-space:pre-wrap}
#login{max-width:360px;margin:14vh auto;text-align:center}
#login input{width:100%;margin:10px 0}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.spin{display:inline-block;width:14px;height:14px;border:2px solid var(--muted);border-top-color:var(--accent);
border-radius:50%;animation:r 0.8s linear infinite;vertical-align:middle}
@keyframes r{to{transform:rotate(360deg)}}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
.list li{margin:4px 0}
.hidden{display:none}
footer{color:var(--muted);text-align:center;font-size:12.5px;padding:26px 0}
</style></head><body>

<div id="login" class="hidden">
  <h1>SEO <b style="color:var(--accent)">Cycle</b></h1>
  <p class="muted">Введите пароль дашборда</p>
  <input id="pw" type="password" placeholder="Пароль" autofocus>
  <button class="primary" onclick="doLogin()">Войти</button>
  <p id="loginerr" class="down"></p>
</div>

<div id="app" class="hidden">
<header>
  <h1>SEO <b>Cycle</b> <span class="muted" id="ver"></span></h1>
  <select id="project" onchange="onProject()"></select>
  <nav id="tabs"></nav>
  <span style="flex:1"></span>
  <button onclick="refresh()">Обновить</button>
</header>
<main id="content"><p class="muted">Загрузка…</p></main>
<footer>Платные запуски, публикация и ads-apply — только через approvals и CLI. Секреты в интерфейс не попадают.</footer>
</div>

<script>
const TABS=[["overview","Портфель"],["project","Проект"],["approvals","Approvals"],
            ["commands","Команды"],["reports","Отчёты"],["access","Доступы"]];
let token=localStorage.getItem("seoCycleToken")||"";
let projects=[],currentProject="",tab="overview",cache={};

const qs=new URLSearchParams(location.search);
if(qs.get("token")){token=qs.get("token");localStorage.setItem("seoCycleToken",token);
  history.replaceState(null,"",location.pathname);}

function esc(s){return String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
async function api(path,opts={}){
  opts.headers=Object.assign({"X-Auth-Token":token},opts.headers||{});
  if(opts.body){opts.method="POST";opts.body=JSON.stringify(opts.body);
    opts.headers["Content-Type"]="application/json";}
  const r=await fetch(path,opts);
  if(r.status===401){showLogin();throw new Error("unauthorized");}
  return r.json();
}
function showLogin(){document.getElementById("app").classList.add("hidden");
  document.getElementById("login").classList.remove("hidden");}
async function doLogin(){
  const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({password:document.getElementById("pw").value})});
  const d=await r.json();
  if(d.token){token=d.token;localStorage.setItem("seoCycleToken",token);boot();}
  else document.getElementById("loginerr").textContent="Неверный пароль";
}
document.addEventListener("keydown",e=>{if(e.key==="Enter"&&!document.getElementById("login").classList.contains("hidden"))doLogin()});

async function boot(){
  const ping=await (await fetch("/api/ping")).json();
  document.getElementById("ver").textContent="v"+ping.version;
  if(!token&&!ping.needs_password){
    const r=await (await fetch("/api/login",{method:"POST",
      headers:{"Content-Type":"application/json"},body:"{}"})).json();
    if(r.token){token=r.token;localStorage.setItem("seoCycleToken",token);}
  }
  try{projects=await api("/api/projects");}catch(e){return;}
  document.getElementById("login").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");
  const sel=document.getElementById("project");
  sel.innerHTML=projects.map(p=>`<option value="${esc(p.path)}">${esc(p.name)}</option>`).join("");
  currentProject=projects.length?projects[0].path:"";
  document.getElementById("tabs").innerHTML=TABS.map(([id,label])=>
    `<button id="tab-${id}" onclick="setTab('${id}')">${label}</button>`).join("");
  setTab("overview");
}
function setTab(id){tab=id;
  TABS.forEach(([t])=>document.getElementById("tab-"+t).classList.toggle("active",t===id));
  render();}
function onProject(){currentProject=document.getElementById("project").value;cache={};render();}
function refresh(){cache={};render();}
function content(html){document.getElementById("content").innerHTML=html;}
function spin(msg){content(`<p class="muted"><span class="spin"></span> ${esc(msg||"Загрузка…")}</p>`)}

function fmtDelta(v,invert){if(v===undefined||v===null)return"";
  const good=invert?v<0:v>0;const cls=v===0?"muted":(good?"up":"down");
  return `<span class="delta ${cls}">${v>0?"+":""}${v}</span>`;}
function daysSince(d){const t=new Date(d+"T00:00:00").getTime();
  return isNaN(t)?null:Math.max(0,Math.floor((Date.now()-t)/86400000));}
function freshBadge(d){const age=daysSince(d);
  if(age===null)return `<span class="badge bad">нет среза</span>`;
  if(age<=2)return `<span class="badge ok">свежий</span>`;
  const cls=age>7?"bad":"warn";
  return `<span class="badge ${cls}">срезу ${age} дн.</span>`;}

async function render(){
  if(tab==="overview")return renderOverview();
  if(tab==="project")return renderProject();
  if(tab==="approvals")return renderApprovals();
  if(tab==="commands")return renderCommands();
  if(tab==="reports")return renderReports();
  if(tab==="access")return renderAccess();
}

async function summary(){
  const key="sum:"+currentProject;
  if(!cache[key]){spin("Собираю данные проекта (journey, позиции, оценки)…");
    cache[key]=await api("/api/summary?project="+encodeURIComponent(currentProject));}
  return cache[key];
}

async function renderOverview(){
  if(!cache.portfolio){spin("Считаю портфель по всем проектам…");
    cache.portfolio=await api("/api/portfolio");}
  const p=cache.portfolio;
  if(p.error){content(`<p class="down">${esc(p.error)}</p>`);return;}
  const t=p.totals;
  let html=`<div class="grid cards">
    <div class="card"><div class="num">${t.projects}</div><div class="label">проектов с данными</div></div>
    <div class="card"><div class="num">${t.top10}${fmtDelta(t.delta_top10)}</div><div class="label">запросов в топ-10</div></div>
    <div class="card"><div class="num">${t.top3}</div><div class="label">в топ-3</div></div>
    <div class="card"><div class="num">${t.clicks}${fmtDelta(t.delta_clicks)}</div><div class="label">кликов за срез</div></div>
    <div class="card"><div class="num">${t.findings_resolved}</div><div class="label">ошибок устранено циклами</div></div>
  </div><h2>Проекты</h2><table><tr><th>Проект</th><th>Срез</th><th>Топ-3</th><th>Топ-10</th><th>Клики</th><th>Δ топ-10</th><th>Статус</th></tr>`;
  for(const r of p.projects){
    if(r.status!=="ok"){html+=`<tr><td>${esc(r.project||"?")}</td><td colspan="5" class="muted">${esc(r.status||"нет данных")}</td><td></td></tr>`;continue;}
    const d=(r.delta_vs_previous||{}).top10;
    html+=`<tr class="click" onclick="openProject('${esc(r.project)}')"><td>${esc(r.project)}</td>
      <td class="muted">${esc(r.latest.date)}</td><td>${r.latest.top3}</td><td><b>${r.latest.top10}</b></td>
      <td>${r.latest.clicks}</td><td>${fmtDelta(d)||"—"}</td>
      <td>${freshBadge(r.latest.date)}</td></tr>`;}
  html+=`</table>`;
  content(html);
}
function openProject(name){
  const p=projects.find(x=>x.name===name);
  if(p){currentProject=p.path;document.getElementById("project").value=p.path;}
  setTab("project");
}

async function renderProject(){
  const s=await summary();
  const j=s.journey||{},pr=s.progress||{},sc=s.scorecards||{};
  let html="";
  if(j.error){html+=`<p class="muted">journey: ${esc(j.error)}</p>`;}
  else{
    const cur=j.current_stage||{};
    html+=`<div class="grid cards">
      <div class="card"><div class="num">${j.journey_score??"—"}/10</div><div class="label">journey score</div></div>
      <div class="card"><div class="num" style="font-size:17px">${esc(cur.title||"цикл завершён")}</div><div class="label">текущая стадия · статус: ${esc(j.status)}</div></div>
      <div class="card"><div class="num">${(j.missing_for_next_step||[]).length}</div><div class="label">блокеров до следующего шага</div></div>
    </div>`;
    const plan=(j.action_plan||[]).slice(0,3);
    if(plan.length){html+=`<h2>Следующие шаги</h2><ul class="list">`+plan.map(a=>
      `<li><b>${esc(a.action)}</b> <span class="muted">→ ${esc(a.command)}</span></li>`).join("")+`</ul>`;}
  }
  if(pr.error||pr.status!=="ok"){html+=`<h2>Позиции</h2><p class="muted">${esc(pr.error||pr.status||"нет данных")} — запустите db-sync и снапшоты мониторинга</p>`;}
  else{
    const l=pr.latest,d=pr.delta_vs_previous||{};
    html+=`<h2>Позиции (${esc(pr.engine)}, срез ${esc(l.date)}) ${freshBadge(l.date)}</h2><div class="grid cards">
      <div class="card"><div class="num">${l.top3}${fmtDelta(d.top3)}</div><div class="label">топ-3</div></div>
      <div class="card"><div class="num">${l.top10}${fmtDelta(d.top10)}</div><div class="label">топ-10</div></div>
      <div class="card"><div class="num">${l.top30}${fmtDelta(d.top30)}</div><div class="label">топ-30</div></div>
      <div class="card"><div class="num">${l.avg_position??"—"}${fmtDelta(d.avg_position,true)}</div><div class="label">средняя позиция</div></div>
      <div class="card"><div class="num">${l.clicks}${fmtDelta(d.clicks)}</div><div class="label">клики</div></div>
    </div>`;
    const snaps=pr.snapshots||[];
    if(snaps.length>1){const max=Math.max(...snaps.map(s=>s.top10),1);
      html+=`<h2>Топ-10 по срезам</h2><table>`+snaps.map(s=>
        `<tr><td class="muted" style="width:110px">${esc(s.date)}</td>
         <td><span class="bar" style="width:${Math.round(s.top10/max*70)}%"></span> ${s.top10}</td></tr>`).join("")+`</table>`;}
    const mv=pr.movers||{};
    if((mv.improved||[]).length||(mv.declined||[]).length){
      html+=`<h2>Движение запросов</h2><div class="grid" style="grid-template-columns:1fr 1fr"><div>`;
      html+=(mv.improved||[]).slice(0,7).map(m=>`<div>↑ <b>${esc(m.query)}</b> <span class="muted">${m.from}→${m.to}</span></div>`).join("")||"<span class='muted'>роста нет</span>";
      html+=`</div><div>`;
      html+=(mv.declined||[]).slice(0,7).map(m=>`<div class="down">↓ ${esc(m.query)} <span class="muted">${m.from}→${m.to}</span></div>`).join("")||"<span class='muted'>просадок нет</span>";
      html+=`</div></div>`;}
    const lp=pr.loops||{};
    if(lp.loops){html+=`<p class="muted">Циклы качества: ${lp.loops} прогонов, устранено findings: <b class="up">${lp.findings_resolved}</b>, открыто: ${lp.findings_open}</p>`;}
  }
  const entries=Object.values(sc.error?{}:sc).sort((a,b)=>(b.at||"").localeCompare(a.at||""));
  if(entries.length){
    html+=`<h2>Самооценки инструментов</h2><table><tr><th>Оценка</th><th>Инструмент</th><th>Статус</th><th>Когда</th><th>Не хватает</th></tr>`;
    for(const e of entries.slice(0,10)){
      const cls=e.score>=8?"ok":(e.score>=5?"warn":"bad");
      html+=`<tr><td><span class="badge ${cls}">${e.score}/10</span></td><td>${esc(e.tool)}</td>
        <td class="muted">${esc(e.status)}</td><td class="muted">${esc((e.at||"").slice(0,16))}</td>
        <td class="muted">${esc((e.missing||[]).slice(0,2).join("; ")||"—")}</td></tr>`;}
    html+=`</table>`;}
  content(html||"<p class='muted'>Нет данных</p>");
}

async function renderApprovals(){
  const s=await summary();
  const tickets=((s.dashboard||{}).approvals)||[];
  const pending=tickets.filter(t=>t.status==="pending");
  let html=`<h2>Ждут решения (${pending.length})</h2>`;
  if(!pending.length)html+=`<p class="muted">Pending-тикетов нет ✅</p>`;
  else{html+=`<table><tr><th>Тикет</th><th>Тип</th><th>Создан</th><th></th></tr>`;
    for(const t of pending){
      html+=`<tr><td><b>${esc(t.title||t.id)}</b><div class="muted">${esc(t.id)}</div></td>
        <td>${esc(t.type)}</td><td class="muted">${esc(t.created)}</td>
        <td class="row"><button class="primary" onclick="ticket('${esc(t.id)}','approve')">Одобрить</button>
        <button onclick="ticket('${esc(t.id)}','reject')">Отклонить</button></td></tr>`;}
    html+=`</table>`;}
  const done=tickets.filter(t=>t.status!=="pending").slice(-8).reverse();
  if(done.length){html+=`<h2>Недавние решения</h2><ul class="list">`+done.map(t=>
    `<li><span class="badge ${t.status==="approved"?"ok":"bad"}">${esc(t.status)}</span> ${esc(t.title||t.id)} <span class="muted">${esc(t.created)}</span></li>`).join("")+`</ul>`;}
  html+=`<p class="muted">Тикеты создаются инструментами (ads-драфты, эскалации циклов, KPI) — здесь только человеческое решение.</p>`;
  content(html);
}
async function ticket(id,action){
  spin((action==="approve"?"Одобряю":"Отклоняю")+" "+id+"…");
  const r=await api("/api/ticket",{body:{project:currentProject,id,action}});
  delete cache["sum:"+currentProject];
  if(!r.ok)alert("Ошибка: "+(r.stderr||r.rc));
  renderApprovals();
}

async function renderCommands(){
  if(!cache.commands)cache.commands=await api("/api/commands");
  const groups={};
  for(const c of cache.commands)(groups[c.group]=groups[c.group]||[]).push(c);
  let html="";
  for(const [g,items] of Object.entries(groups)){
    html+=`<h2>${esc(g)}</h2><div class="grid cmds">`+items.map(c=>
      `<div class="cmd" onclick="runCmd('${c.id}')"><div class="g">${esc(g)}</div>
       <div class="t">${esc(c.label)}</div><div class="h">${esc(c.hint)}</div></div>`).join("")+`</div>`;}
  html+=`<h2>Вывод</h2><pre id="out" class="muted">Нажмите на команду — вывод появится здесь.</pre>`;
  content(html);
}
async function runCmd(id){
  const out=document.getElementById("out");
  out.innerHTML=`<span class="spin"></span> Выполняю ${esc(id)}…`;
  const r=await api("/api/run",{body:{project:currentProject,command:id}});
  cache={};
  out.textContent=(r.ok?"✓ ":"✗ rc="+r.rc+"\n")+(r.stdout||"")+(r.stderr?"\n--- stderr ---\n"+r.stderr:"");
}

async function renderReports(){
  spin("Ищу отчёты…");
  const files=await api("/api/reports?project="+encodeURIComponent(currentProject));
  if(files.error){content(`<p class="down">${esc(files.error)}</p>`);return;}
  if(!files.length){content("<p class='muted'>Отчётов пока нет — сгенерируйте на вкладке «Команды» (отчёт клиенту, прогресс, дашборд).</p>");return;}
  let html=`<h2>Отчёты проекта</h2><table><tr><th>Файл</th><th>Обновлён</th><th>Размер</th></tr>`;
  for(const f of files){
    const href=`/files?project=${encodeURIComponent(currentProject)}&file=${encodeURIComponent(f.file)}&token=${token}`;
    html+=`<tr><td><a href="${href}" target="_blank">${esc(f.file)}</a></td>
      <td class="muted">${new Date(f.mtime*1000).toLocaleString("ru")}</td>
      <td class="muted">${(f.size/1024).toFixed(1)} КБ</td></tr>`;}
  html+=`</table>`;
  content(html);
}

async function renderAccess(){
  spin("Проверяю доступы…");
  const a=await api("/api/auth-status?project="+encodeURIComponent(currentProject));
  if(a.error){content(`<p class="down">${esc(a.error)}</p>`);return;}
  let html=`<h2>Провайдеры</h2><table><tr><th>Провайдер</th><th>Статус</th><th>Переменные (источник)</th></tr>`;
  const badges={ready:"ok",partial:"warn",not_configured:"bad"};
  for(const [alias,d] of Object.entries(a)){
    const vars=(d.vars||[]).map(v=>{
      const src=v.source?`<span class="up">${v.source}</span>`:`<span class="muted">—</span>`;
      return `${esc(v.var)}${v.required?"":" <span class='muted'>(опц.)</span>"}: ${src}`;}).join("<br>");
    html+=`<tr><td><b>${esc(alias)}</b><div class="muted">${esc(d.title)}</div></td>
      <td><span class="badge ${badges[d.state]||""}">${esc(d.state)}</span></td><td>${vars}</td></tr>`;}
  html+=`</table><p class="muted">Настройка: <code>seo-cycle auth login &lt;provider&gt;</code> (проект) или с <code>--global</code> (всё агентство). Значения секретов сюда не передаются.</p>`;
  content(html);
}

boot();
</script>
</body></html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
