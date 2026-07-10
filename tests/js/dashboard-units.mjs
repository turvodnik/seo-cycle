// Unit tests for the dashboard page script (no browser needed).
// Runs the extracted <script> in a stubbed DOM/fetch environment and asserts
// each render*() output against fixtures. Invoked by test_webapp_js_units.py:
//   node dashboard-units.mjs /path/to/extracted-page.js
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const scriptSource = readFileSync(process.argv[2], "utf8");

// --- DOM / browser stubs -----------------------------------------------
const elements = new Map();
function el(id) {
  if (!elements.has(id)) {
    elements.set(id, {
      id, innerHTML: "", textContent: "", value: "",
      classList: { add() {}, remove() {}, toggle() {} },
      style: {},
    });
  }
  return elements.get(id);
}
globalThis.document = { getElementById: el, addEventListener() {} };
globalThis.localStorage = {
  store: {},
  getItem(k) { return this.store[k] ?? null; },
  setItem(k, v) { this.store[k] = v; },
  removeItem(k) { delete this.store[k]; },
};
globalThis.location = { search: "", pathname: "/" };
globalThis.history = { replaceState() {} };
globalThis.alert = () => {};
// детерминированное «сегодня» для freshness-бейджей (фикстуры датированы 2026-07-04)
Date.now = () => new Date("2026-07-08T12:00:00").getTime();

// --- API fixtures ---------------------------------------------------------
const PROJECT = "/tmp/proj";
const FIXTURES = {
  "/api/ping": { ok: true, needs_password: false, version: "test" },
  "/api/login": { token: "unit-token" },
  "/api/projects": [{ name: "Юнит", path: PROJECT }],
  "/api/portfolio": {
    totals: { projects: 1, queries: 500, top3: 24, top10: 419, clicks: 111,
              delta_top10: 7, delta_clicks: 15, findings_resolved: 2 },
    projects: [{ status: "ok", project: "Юнит",
                 latest: { date: "2026-07-04", top3: 24, top10: 419, clicks: 111 },
                 delta_vs_previous: { top10: 7 } }],
  },
  "/api/summary": {
    journey: { journey_score: 7.5, status: "blocked",
               current_stage: { title: "Content draft" },
               missing_for_next_step: ["a", "b", "c"],
               action_plan: [{ action: "Написать драфт", command: "seo-cycle loop draft" }] },
    progress: { status: "ok", engine: "yandex",
                latest: { date: "2026-07-04", top3: 24, top10: 419, top30: 499,
                          avg_position: 7.8, clicks: 111 },
                delta_vs_previous: { top10: 7, clicks: 15 },
                snapshots: [{ date: "2026-06-27", top10: 400 }, { date: "2026-07-04", top10: 419 }],
                movers: { improved: [{ query: "вагонка", from: 12, to: 3 }],
                          declined: [], counts: { improved: 1, declined: 0, new: 0, lost: 0 } },
                loops: { loops: 3, findings_resolved: 5, findings_open: 0 } },
    scorecards: { "loop:draft": { tool: "loop:draft", score: 9.2, status: "done",
                                  at: "2026-07-04T12:00:00", missing: [] } },
    dashboard: { approvals: [
      { id: "abc123", type: "ads_campaign_draft", status: "pending",
        created: "2026-07-04", title: "Драфт кампаний" },
      { id: "old1", type: "loop_escalation", status: "approved", created: "2026-07-01", title: "Старый" },
    ] },
  },
  "/api/commands": [
    { id: "journey", label: "Статус проекта", group: "Обзор", hint: "hint1" },
    { id: "db-sync", label: "Обновить базу", group: "Данные", hint: "hint2" },
  ],
  "/api/reports": [
    { file: "seo/reports/position-progress.html", name: "position-progress.html",
      mtime: 1751600000, size: 20480 },
  ],
  "/api/auth-status": {
    yandex: { title: "Яндекс OAuth", state: "ready",
              vars: [{ var: "YANDEX_OAUTH_TOKEN", source: "project", required: true }] },
    gbp: { title: "GBP", state: "not_configured",
           vars: [{ var: "GBP_OAUTH_CLIENT_ID", source: null, required: true }] },
  },
  "/api/run": { ok: true, rc: 0, stdout: "выполнено", stderr: "" },
  "/api/ticket": { ok: true, rc: 0, stdout: "", stderr: "" },
};

globalThis.fetch = async (url) => {
  const path = String(url).split("?")[0];
  const body = FIXTURES[path];
  if (body === undefined) throw new Error(`no fixture for ${path}`);
  return { status: 200, json: async () => structuredClone(body) };
};

// --- Load the page script into the global scope -------------------------
(0, eval)(scriptSource); // sloppy-mode indirect eval: function decls become global
const g = (expr) => (0, eval)(expr);
await new Promise((r) => setTimeout(r, 30)); // let boot() settle

let passed = 0;
const check = (name, fn) => { fn(); passed += 1; console.log(`ok - ${name}`); };
const content = () => el("content").innerHTML;

// --- Pure helpers ---------------------------------------------------------
check("esc() escapes html", () => {
  assert.equal(g(`esc('<b>&"x')`), "&lt;b&gt;&amp;&quot;x");
});
check("fmtDelta() colors direction and inversion", () => {
  assert.match(g("fmtDelta(5)"), /up/);
  assert.match(g("fmtDelta(-3)"), /down/);
  assert.match(g("fmtDelta(-0.4, true)"), /up/); // меньшая позиция = лучше
  assert.equal(g("fmtDelta(null)"), "");
});
check("daysSince()/freshBadge() grade data age", () => {
  assert.equal(g(`daysSince("2026-07-04")`), 4);
  assert.match(g(`freshBadge("2026-07-08")`), /свежий/);
  assert.match(g(`freshBadge("2026-07-04")`), /warn/);
  assert.match(g(`freshBadge("2026-06-01")`), /bad/);
  assert.match(g(`freshBadge("мусор")`), /нет среза/);
});

// --- boot() side effects ---------------------------------------------------
check("boot() auto-logs-in and loads projects", () => {
  assert.equal(g("token"), "unit-token");
  assert.equal(g("projects.length"), 1);
  assert.equal(g("currentProject"), PROJECT);
});

// --- Renderers -------------------------------------------------------------
await g("renderOverview()");
check("renderOverview() shows totals, project row and freshness", () => {
  assert.match(content(), /проектов с данными/);
  assert.match(content(), /419/);
  assert.match(content(), /\+7/);
  assert.match(content(), /Юнит/);
  assert.match(content(), /срезу 4 дн\./); // freshness вместо вечного «ok»
});

g("cache={}");
await g("renderProject()");
check("renderProject() shows journey, positions, movers, scorecards", () => {
  assert.match(content(), /7\.5\/10/);
  assert.match(content(), /Content draft/);
  assert.match(content(), /419/);
  assert.match(content(), /вагонка/);
  assert.match(content(), /9\.2\/10/);
  assert.match(content(), /устранено findings: <b class="up">5<\/b>/);
});

await g("renderApprovals()");
check("renderApprovals() lists pending with action buttons", () => {
  assert.match(content(), /Драфт кампаний/);
  assert.match(content(), /Одобрить/);
  assert.match(content(), /Отклонить/);
  assert.match(content(), /Недавние решения/);
});

await g("renderCommands()");
check("renderCommands() groups commands and adds output pane", () => {
  assert.match(content(), /Статус проекта/);
  assert.match(content(), /Данные/);
  assert.match(content(), /id="out"/);
});

await g("runCmd('journey')");
check("runCmd() writes tool output into #out", () => {
  assert.match(el("out").textContent, /выполнено/);
});

await g("renderReports()");
check("renderReports() links files through /files with token", () => {
  assert.match(content(), /position-progress\.html/);
  assert.match(content(), /\/files\?project=/);
  assert.match(content(), /token=unit-token/);
});

await g("renderAccess()");
check("renderAccess() shows provider states and sources", () => {
  assert.match(content(), /ready/);
  assert.match(content(), /not_configured/);
  assert.match(content(), /YANDEX_OAUTH_TOKEN/);
});

console.log(`PASS ${passed} checks`);
