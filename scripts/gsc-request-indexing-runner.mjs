#!/usr/bin/env node
// Browser helper for Search Console URL Inspection "Request indexing".
// Credentials are never passed through CLI args. The user logs in through the
// persistent browser profile used by Playwright.

import fs from "node:fs";
import path from "node:path";

const nodeModules = process.env.GSC_PLAYWRIGHT_NODE_MODULES;
if (nodeModules) {
  process.env.NODE_PATH = nodeModules;
  const Module = await import("node:module");
  Module.default._initPaths();
}

const { chromium } = await import("playwright-core");

function argValue(name, fallback = "") {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) return fallback;
  return process.argv[index + 1];
}

function hasFlag(name) {
  return process.argv.includes(name);
}

function readTargets(file) {
  if (!file) return [];
  const payload = JSON.parse(fs.readFileSync(file, "utf8"));
  return Array.isArray(payload.targets) ? payload.targets : [];
}

function inspectUrl(siteUrl, url) {
  const params = new URLSearchParams({
    resource_id: siteUrl,
    id: url,
  });
  return `https://search.google.com/search-console/inspect?${params.toString()}`;
}

async function clickFirstVisible(page, patterns, timeout = 2500) {
  for (const pattern of patterns) {
    const locator = page.getByText(pattern).first();
    try {
      await locator.waitFor({ state: "visible", timeout });
      await locator.click({ timeout: 5000 });
      return String(pattern);
    } catch {
      // Try next text pattern.
    }
  }
  return "";
}

async function requestIndexing(page, options) {
  const actions = [];
  const requestPatterns = [
    /request indexing/i,
    /запросить индексирование/i,
    /запросить индекс/i,
  ];
  const livePatterns = [
    /test live url/i,
    /проверить url на сайте/i,
    /проверить действующую страницу/i,
  ];
  const confirmPatterns = [
    /got it/i,
    /^ok$/i,
    /close/i,
    /закрыть/i,
    /готово/i,
  ];

  let clicked = await clickFirstVisible(page, requestPatterns, 4000);
  if (clicked) {
    actions.push(`request:${clicked}`);
  } else if (options.liveTestFirst) {
    clicked = await clickFirstVisible(page, livePatterns, 4000);
    if (clicked) {
      actions.push(`live_test:${clicked}`);
      await page.waitForTimeout(options.liveTestWaitMs);
      clicked = await clickFirstVisible(page, requestPatterns, 10000);
      if (clicked) actions.push(`request_after_live:${clicked}`);
    }
  }

  const confirmed = await clickFirstVisible(page, confirmPatterns, 2500);
  if (confirmed) actions.push(`confirm:${confirmed}`);

  const pageText = (await page.locator("body").innerText({ timeout: 5000 }).catch(() => "")).toLowerCase();
  const quotaHit = /quota|лимит|too many|повторите позже|try again later/.test(pageText);
  const alreadySubmitted = /indexing requested|индексирование запрошено|request submitted|запрос отправлен/.test(pageText);
  return {
    actions,
    quota_hit: quotaHit,
    status: actions.some((item) => item.startsWith("request")) || alreadySubmitted ? "submitted_or_requested" : quotaHit ? "quota_hit" : "request_button_not_found",
  };
}

const inputFile = argValue("--input-file");
const resultFile = argValue("--result-file");
const profileDir = argValue("--profile-dir", path.join(process.env.HOME || ".", ".codex/browser-profiles/gsc"));
const siteUrl = argValue("--site-url");
const browserChannel = argValue("--browser-channel", "chrome");
const timeoutSeconds = Number(argValue("--timeout-seconds", "90"));
const liveTestWaitSeconds = Number(argValue("--live-test-wait-seconds", "90"));
const autoClick = hasFlag("--auto-click");
const liveTestFirst = !hasFlag("--skip-live-test");
const headless = hasFlag("--headless");
const keepOpen = hasFlag("--keep-open");
const targets = readTargets(inputFile);

const result = {
  status: "started",
  site_url: siteUrl,
  auto_click: autoClick,
  stores_password: false,
  targets_total: targets.length,
  results: [],
};

let context;
try {
  fs.mkdirSync(profileDir, { recursive: true });
  context = await chromium.launchPersistentContext(profileDir, {
    channel: browserChannel === "auto" ? undefined : browserChannel,
    headless,
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
  });
  const page = context.pages()[0] || (await context.newPage());
  page.setDefaultTimeout(timeoutSeconds * 1000);

  for (const target of targets) {
    const url = target.url;
    const inspectionUrl = inspectUrl(siteUrl, url);
    const row = {
      url,
      priority: target.priority || "",
      priority_score: target.priority_score || 0,
      status: "opened",
      inspection_url: inspectionUrl,
      actions: [],
    };
    try {
      await page.goto(inspectionUrl, { waitUntil: "domcontentloaded", timeout: timeoutSeconds * 1000 });
      await page.waitForTimeout(6000);
      if (autoClick) {
        const submit = await requestIndexing(page, {
          liveTestFirst,
          liveTestWaitMs: liveTestWaitSeconds * 1000,
        });
        row.status = submit.status;
        row.actions = submit.actions;
        row.quota_hit = submit.quota_hit;
      } else {
        row.status = "manual_action_required";
      }
    } catch (error) {
      row.status = "browser_error";
      row.error = String(error).slice(0, 500);
    }
    result.results.push(row);
    if (row.quota_hit) break;
  }
  result.status = autoClick ? "finished" : "manual_action_required";
  if (keepOpen) {
    await page.waitForTimeout(24 * 60 * 60 * 1000);
  }
} catch (error) {
  result.status = "failed";
  result.error = String(error).slice(0, 1000);
} finally {
  if (context && !keepOpen) {
    await context.close().catch(() => {});
  }
  if (resultFile) {
    fs.mkdirSync(path.dirname(resultFile), { recursive: true });
    fs.writeFileSync(resultFile, JSON.stringify(result, null, 2), "utf8");
  }
  process.stdout.write(JSON.stringify(result, null, 2));
}

process.exit(result.status === "failed" ? 1 : 0);
