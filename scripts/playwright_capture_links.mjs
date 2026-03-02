#!/usr/bin/env node

import fs from "node:fs";

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const key = a.slice(2);
      const val = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : "true";
      out[key] = val;
    }
  }
  return out;
}

const args = parseArgs(process.argv);
const inputPath = args.input || "reports/latest.json";
const outputPath = args.output || "docs/automation/playwright-latest.json";
const limit = Number.parseInt(args.limit || "25", 10);

let playwright;
try {
  playwright = await import("playwright");
} catch {
  console.error("Playwright package not installed. Install with: npm i -D playwright && npx playwright install chromium");
  process.exit(2);
}

const raw = fs.readFileSync(inputPath, "utf8");
const intel = JSON.parse(raw);

const links = [];
for (const d of intel.drugs || []) {
  for (const n of d.googleNews || []) {
    if (n.link) {
      links.push({
        drug: d.name,
        title: n.title || "Untitled",
        source: n.source || "",
        link: n.link,
      });
    }
  }
}

const dedup = [];
const seen = new Set();
for (const item of links) {
  const key = item.link;
  if (seen.has(key)) continue;
  seen.add(key);
  dedup.push(item);
  if (dedup.length >= limit) break;
}

const browser = await playwright.chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

const captures = [];
for (const item of dedup) {
  const result = {
    ...item,
    fetchedAtUTC: new Date().toISOString(),
    finalUrl: null,
    pageTitle: null,
    ok: false,
    error: null,
  };

  try {
    await page.goto(item.link, { waitUntil: "domcontentloaded", timeout: 30000 });
    result.finalUrl = page.url();
    result.pageTitle = await page.title();
    result.ok = true;
  } catch (err) {
    result.error = String(err);
  }

  captures.push(result);
}

await browser.close();

const payload = {
  generatedAtUTC: new Date().toISOString(),
  inputPath,
  totalLinks: dedup.length,
  captures,
};

fs.writeFileSync(outputPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
console.log(`Wrote ${outputPath}`);
