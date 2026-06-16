#!/usr/bin/env node
// Download/capture a Google Search Console Pages issue export through the UI.
// The user must already be logged in through the persistent browser profile.

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

async function clickFirstVisible(page, patterns, timeout = 3000) {
  for (const pattern of patterns) {
    const locator = page.getByText(pattern).first();
    try {
      await locator.waitFor({ state: "visible", timeout });
      await locator.click({ timeout: 5000 });
      return String(pattern);
    } catch {
      // Try next pattern.
    }
  }
  return "";
}

function pagesUrl(siteUrl) {
  const params = new URLSearchParams({ resource_id: siteUrl });
  return `https://search.google.com/search-console/index?${params.toString()}`;
}

const resultFile = argValue("--result-file");
const siteUrl = argValue("--site-url");
const issueUrl = argValue("--issue-url") || pagesUrl(siteUrl);
const profileDir = argValue("--profile-dir", path.join(process.env.HOME || ".", ".codex/browser-profiles/gsc"));
const importDir = argValue("--import-dir");
const browserChannel = argValue("--browser-channel", "chrome");
const timeoutSeconds = Number(argValue("--timeout-seconds", "90"));
const manualFallbackSeconds = Number(argValue("--manual-fallback-seconds", "0"));
const headless = hasFlag("--headless");
const keepOpen = hasFlag("--keep-open");

const result = {
  status: "started",
  site_url: siteUrl,
  issue_url: issueUrl,
  downloads: [],
  actions: [],
  stores_password: false,
};

let context;
try {
  fs.mkdirSync(profileDir, { recursive: true });
  fs.mkdirSync(importDir, { recursive: true });
  context = await chromium.launchPersistentContext(profileDir, {
    channel: browserChannel === "auto" ? undefined : browserChannel,
    headless,
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
  });
  const page = context.pages()[0] || (await context.newPage());
  page.setDefaultTimeout(timeoutSeconds * 1000);
  await page.goto(issueUrl, { waitUntil: "domcontentloaded", timeout: timeoutSeconds * 1000 });
  await page.waitForTimeout(6000);

  const downloadPromise = page.waitForEvent("download", { timeout: Math.max(10, manualFallbackSeconds || 20) * 1000 }).catch(() => null);
  const exportClicked = await clickFirstVisible(page, [/export/i, /экспорт/i, /скачать/i], 5000);
  if (exportClicked) result.actions.push(`export:${exportClicked}`);
  await page.waitForTimeout(1500);
  const csvClicked = await clickFirstVisible(page, [/csv/i, /comma/i, /скачать csv/i], 3000);
  if (csvClicked) result.actions.push(`csv:${csvClicked}`);

  const download = await downloadPromise;
  if (download) {
    const suggested = download.suggestedFilename();
    const safeName = `${new Date().toISOString().replace(/[:.]/g, "-")}-${suggested || "gsc-indexing-export.csv"}`;
    const target = path.join(importDir, safeName);
    await download.saveAs(target);
    result.downloads.push(target);
  }

  if (!result.downloads.length && manualFallbackSeconds > 0) {
    result.actions.push(`manual_wait:${manualFallbackSeconds}s`);
    const manualDownload = await page.waitForEvent("download", { timeout: manualFallbackSeconds * 1000 }).catch(() => null);
    if (manualDownload) {
      const suggested = manualDownload.suggestedFilename();
      const safeName = `${new Date().toISOString().replace(/[:.]/g, "-")}-${suggested || "gsc-indexing-export.csv"}`;
      const target = path.join(importDir, safeName);
      await manualDownload.saveAs(target);
      result.downloads.push(target);
    }
  }

  result.status = result.downloads.length ? "downloaded" : "no_download";
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
