#!/usr/bin/env node
/**
 * Browser runner for WriterZen exports.
 *
 * This file intentionally contains only UI heuristics and download handling.
 * It does not accept, store or print passwords. Login is handled by the
 * persistent browser profile opened by writerzen-browser-collect.py.
 */

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const nodeModulesDir = process.env.WRITERZEN_PLAYWRIGHT_NODE_MODULES || "";
let playwright;
if (nodeModulesDir) {
  playwright = require(path.join(nodeModulesDir, "playwright-core"));
} else {
  try {
    playwright = require("playwright-core");
  } catch {
    playwright = require("playwright");
  }
}
const { chromium } = playwright;

const REPORT_PATHS = {
  topic_discovery: ["/topic-discovery", "/topic-discovery/home", "/"],
  keyword_explorer: ["/keyword-explorer", "/keyword-explorer/home", "/"],
  keyword_planner: ["/keyword-planner", "/keyword-planner/home", "/"],
  domain_focus: ["/domain-focus", "/domain-focus/home", "/"],
};

const REPORT_LABELS = {
  topic_discovery: [/topic discovery/i, /topics?/i],
  keyword_explorer: [/keyword explorer/i, /keyword lookup/i, /keywords?/i],
  keyword_planner: [/keyword planner/i, /planner/i, /cluster/i],
  domain_focus: [/domain focus/i, /domain/i, /competitor/i],
};

function parseArgs(argv) {
  const out = { reports: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    const next = argv[i + 1];
    if (key === "--report") {
      out.reports.push(next);
      i += 1;
    } else if (key.startsWith("--")) {
      const name = key.slice(2).replaceAll("-", "_");
      if (next && !next.startsWith("--")) {
        out[name] = next;
        i += 1;
      } else {
        out[name] = true;
      }
    }
  }
  return out;
}

function slug(value) {
  return String(value || "writerzen")
    .toLowerCase()
    .replace(/https?:\/\//g, "")
    .replace(/[^a-z0-9а-яё]+/gi, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || "writerzen";
}

function absUrl(base, maybePath) {
  return new URL(maybePath, base).toString();
}

async function clickFirst(page, locators, timeout = 3000) {
  for (const locator of locators) {
    try {
      const target = locator.first();
      await target.waitFor({ state: "visible", timeout });
      await target.click({ timeout });
      return true;
    } catch {
      // Try the next locator.
    }
  }
  return false;
}

async function fillSeed(page, seed, timeout = 2500) {
  const locators = [
    page.getByPlaceholder(/keyword|topic|domain|seed|enter|search|запрос|ключ|тема|домен/i),
    page.locator("input[type='search']"),
    page.locator("textarea"),
    page.locator("input[type='text']"),
  ];
  for (const locator of locators) {
    try {
      const target = locator.first();
      await target.waitFor({ state: "visible", timeout });
      await target.fill(seed, { timeout });
      return true;
    } catch {
      // Try the next input.
    }
  }
  return false;
}

async function startReport(page, timeout = 2500) {
  return clickFirst(
    page,
    [
      page.getByRole("button", { name: /search|explore|analy[sz]e|lookup|start|generate|create|continue|next|run|найти|искать|создать|запустить/i }),
      page.getByText(/search|explore|analy[sz]e|lookup|start|generate|create|continue|next|run|найти|искать|создать|запустить/i),
    ],
    timeout,
  );
}

async function openCreateFlow(page, report, timeout = 2500) {
  const labels = [
    /new report|new keyword|new topic|new list|new project|create report|create keyword|create topic|add keyword|add topic/i,
    /start new|run new|lookup new|fresh report|create/i,
    /новый|создать|добавить|запустить новый|новый отч[её]т/i,
  ];
  for (const label of labels) {
    const ok = await clickFirst(
      page,
      [
        page.getByRole("button", { name: label }),
        page.getByRole("link", { name: label }),
        page.getByText(label),
      ],
      timeout,
    );
    if (ok) return true;
  }

  // Some WriterZen screens expose report cards instead of a single create button.
  const reportLabels = REPORT_LABELS[report] || [];
  for (const label of reportLabels) {
    const ok = await clickFirst(
      page,
      [
        page.getByRole("button", { name: label }),
        page.getByRole("link", { name: label }),
        page.getByText(label),
      ],
      timeout,
    );
    if (ok) return true;
  }
  return false;
}

async function clickReportNav(page, report, timeout = 2500) {
  const labels = REPORT_LABELS[report] || [];
  for (const label of labels) {
    const ok = await clickFirst(
      page,
      [
        page.getByRole("link", { name: label }),
        page.getByRole("button", { name: label }),
        page.getByText(label),
      ],
      timeout,
    );
    if (ok) return true;
  }
  return false;
}

async function exportReport(page, timeoutMs) {
  const preferredFormat = String(process.env.WRITERZEN_EXPORT_FORMAT || "").toLowerCase();
  const exportLocators = [
    page.getByRole("button", { name: /export|download|csv|xlsx|excel|выгруз|скач|экспорт/i }),
    page.getByRole("link", { name: /export|download|csv|xlsx|excel|выгруз|скач|экспорт/i }),
    page.getByText(/export|download|csv|xlsx|excel|выгруз|скач|экспорт/i),
  ];
  const downloadPromise = page.waitForEvent("download", { timeout: timeoutMs }).catch(() => null);
  const clicked = await clickFirst(page, exportLocators, 5000);
  if (!clicked) return { status: "export_button_not_found", download: null };
  const download = await downloadPromise;
  if (download) return { status: "downloaded", download };

  // Some UIs first open an export menu; try CSV/XLSX menu items once.
  const menuDownloadPromise = page.waitForEvent("download", { timeout: timeoutMs }).catch(() => null);
  const preferredPattern = preferredFormat === "xlsx" || preferredFormat === "excel"
    ? /xlsx|excel|download|скач/i
    : /csv|download|скач/i;
  const menuClicked = await clickFirst(
    page,
    [
      page.getByRole("menuitem", { name: preferredPattern }),
      page.getByRole("button", { name: preferredPattern }),
      page.getByText(preferredPattern),
      page.getByRole("menuitem", { name: /csv|xlsx|excel|download|скач/i }),
      page.getByRole("button", { name: /csv|xlsx|excel|download|скач/i }),
      page.getByText(/csv|xlsx|excel|download|скач/i),
    ],
    5000,
  );
  if (!menuClicked) return { status: "download_not_started", download: null };
  const menuDownload = await menuDownloadPromise;
  return menuDownload ? { status: "downloaded", download: menuDownload } : { status: "download_not_started", download: null };
}

async function ensureLogin(page, loginTimeoutMs) {
  const passwordInput = page.locator("input[type='password']").first();
  const loginVisible = await passwordInput.isVisible({ timeout: 1500 }).catch(() => false);
  const url = page.url();
  if (!loginVisible && !/login|signin|auth/i.test(url)) {
    return { logged_in: true, waited_for_login: false };
  }
  if (!loginTimeoutMs) {
    return { logged_in: false, waited_for_login: false };
  }
  await page.waitForFunction(
    () => !document.querySelector("input[type='password']") && !/login|signin|auth/i.test(location.href),
    null,
    { timeout: loginTimeoutMs },
  ).catch(() => null);
  const stillPassword = await passwordInput.isVisible({ timeout: 1000 }).catch(() => false);
  return { logged_in: !stillPassword, waited_for_login: true };
}

async function runReport(page, args, report) {
  const baseUrl = args.login_url || "https://app.writerzen.net/";
  const seed = report === "domain_focus" && args.domain ? args.domain : args.topic;
  const timeoutMs = Number(args.timeout_seconds || 90) * 1000;
  const loginTimeoutMs = Number(args.login_timeout_seconds || 600) * 1000;
  const paths = REPORT_PATHS[report] || ["/"];
  const result = {
    report,
    seed,
    status: "started",
    url_attempts: [],
    actions: [],
    downloads: [],
  };

  await page.goto(absUrl(baseUrl, paths[0]), { waitUntil: "domcontentloaded", timeout: timeoutMs }).catch(async () => {
    await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: timeoutMs });
  });
  result.url_attempts.push(page.url());
  const login = await ensureLogin(page, loginTimeoutMs);
  result.login = login;
  if (!login.logged_in) {
    result.status = "login_required";
    return result;
  }

  if (!(await clickReportNav(page, report))) {
    for (const candidate of paths) {
      const url = absUrl(baseUrl, candidate);
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs }).catch(() => null);
      result.url_attempts.push(page.url());
      if (await fillSeed(page, seed)) break;
    }
  }

  if (args.force_new_report) {
    const created = await openCreateFlow(page, report);
    result.actions.push(created ? "force_new_report_clicked" : "force_new_report_button_not_found");
  }

  const seedFilled = await fillSeed(page, seed);
  if (!seedFilled && !args.skip_create_missing) {
    const created = await openCreateFlow(page, report);
    result.actions.push(created ? "create_missing_clicked" : "create_missing_button_not_found");
  }
  const seedFilledAfterCreate = seedFilled || (await fillSeed(page, seed));
  result.actions.push(seedFilledAfterCreate ? "seed_filled" : "seed_input_not_found");
  if (seedFilledAfterCreate) {
    const started = await startReport(page);
    result.actions.push(started ? "report_started" : "start_button_not_found");
  }

  await page.waitForLoadState("networkidle", { timeout: Math.min(timeoutMs, 45000) }).catch(() => null);
  await page.waitForTimeout(Number(args.result_wait_seconds || 15) * 1000);

  const exported = await exportReport(page, timeoutMs);
  result.actions.push(exported.status);
  if (exported.download) {
    const suggested = exported.download.suggestedFilename();
    const filename = `writerzen-${report}-${slug(seed)}-${Date.now()}-${suggested}`;
    const target = path.join(args.import_dir, filename);
    await exported.download.saveAs(target);
    result.downloads.push(target);
    result.status = "downloaded";
    return result;
  }

  const fallbackSeconds = Number(args.manual_fallback_seconds || 0);
  if (fallbackSeconds > 0) {
    result.actions.push(`manual_fallback_wait_${fallbackSeconds}s`);
    const manual = await page.waitForEvent("download", { timeout: fallbackSeconds * 1000 }).catch(() => null);
    if (manual) {
      const suggested = manual.suggestedFilename();
      const filename = `writerzen-${report}-${slug(seed)}-${Date.now()}-${suggested}`;
      const target = path.join(args.import_dir, filename);
      await manual.saveAs(target);
      result.downloads.push(target);
      result.status = "downloaded_manual_fallback";
      return result;
    }
  }

  result.status = "download_not_captured";
  return result;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.topic) throw new Error("--topic is required");
  if (!args.profile_dir) throw new Error("--profile-dir is required");
  if (!args.import_dir) throw new Error("--import-dir is required");
  if (!args.result_file) throw new Error("--result-file is required");
  fs.mkdirSync(args.profile_dir, { recursive: true });
  fs.mkdirSync(args.import_dir, { recursive: true });

  const launchOptions = {
    headless: Boolean(args.headless),
    acceptDownloads: true,
    viewport: { width: 1440, height: 1000 },
  };
  if (args.browser_channel && args.browser_channel !== "auto") {
    launchOptions.channel = args.browser_channel;
  }
  const context = await chromium.launchPersistentContext(args.profile_dir, launchOptions);
  const page = context.pages()[0] || (await context.newPage());
  page.setDefaultTimeout(Number(args.timeout_seconds || 90) * 1000);

  const report = {
    provider: "writerzen",
    status: "started",
    topic: args.topic,
    domain: args.domain || "",
    reports_requested: args.reports,
    profile_dir: args.profile_dir,
    import_dir: args.import_dir,
    stores_password: false,
    results: [],
    downloads: [],
  };

  try {
    await page.goto(args.login_url || "https://app.writerzen.net/", { waitUntil: "domcontentloaded", timeout: Number(args.timeout_seconds || 90) * 1000 });
    await ensureLogin(page, Number(args.login_timeout_seconds || 600) * 1000);
    for (const reportName of args.reports) {
      const item = await runReport(page, args, reportName);
      report.results.push(item);
      report.downloads.push(...item.downloads);
    }
    report.status = report.downloads.length ? "downloaded" : "no_downloads";
  } finally {
    if (!args.keep_open) {
      await context.close();
    }
  }
  fs.writeFileSync(args.result_file, JSON.stringify(report, null, 2), "utf8");
}

main().catch((error) => {
  const resultFileIndex = process.argv.indexOf("--result-file");
  const resultFile = resultFileIndex >= 0 ? process.argv[resultFileIndex + 1] : null;
  const payload = {
    provider: "writerzen",
    status: "browser_error",
    stores_password: false,
    error: String(error && error.stack ? error.stack : error),
  };
  if (resultFile) {
    fs.writeFileSync(resultFile, JSON.stringify(payload, null, 2), "utf8");
  }
  console.error(payload.error);
  process.exit(1);
});
