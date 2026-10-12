// Optional real-browser regression. Requires Playwright in the caller's environment.
// CATALOG_URL may point at the local build or a deployed GitHub Pages subpath.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

async function main() {
  const base = new URL(process.env.CATALOG_URL || "http://127.0.0.1:8765/database/");
  const archive = new URL("../", base);
  const output = process.env.SCREENSHOT_DIR;
  if (output) assert.ok(fs.statSync(output).isDirectory(), "SCREENSHOT_DIR must exist");
  const browser = await chromium.launch({ headless: true });
  const errors = [];
  let checks = 0;
  const check = (value, description) => { assert.ok(value, description); checks += 1; };
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, colorScheme: "dark" });
    const page = await context.newPage();
    page.on("pageerror", error => errors.push(error.message));
    const response = await context.request.get(new URL("data.json", base).href);
    check(response.ok(), "catalog HTTP success");
    const data = await response.json();
    const calculations = data.calculations;
    const inputs = calculations.flatMap(record => record.files?.inputs || []);
    check(calculations.length > 0 && data.basis_sets.length > 0, "nonempty real archive");
    const go = async hash => {
      await page.goto(base.href + hash, { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.querySelector("#catalog").getAttribute("aria-busy") === "false" || document.querySelector("#detail-view h1"));
    };
    const screenshot = async name => { if (output) await page.screenshot({ path: path.join(output, name), fullPage: false }); };
    await go("");
    await page.waitForSelector(".material-row");
    check(await page.locator("#catalog img").count() === 0, "no list figure previews");
    check(await page.locator("#status-filter-control").isHidden(), "basis-only filter is hidden");
    check((await page.locator("#result-count").innerText()).includes(`${calculations.length} of ${calculations.length}`), "inventory count");
    await screenshot("materials-desktop.png");
    await page.getByRole("button", { name: "Next page", exact: true }).click();
    check((await page.locator(".pagination").innerText()).includes("Page 2"), "pagination");
    await page.locator("#search").fill("MoS₂");
    check(await page.locator(".material-row").count() > 0, "Unicode formula search");
    await page.locator("#search").fill("Si");
    check((await page.locator("#result-count").innerText()).startsWith("2 of"), "element search excludes unrelated substrings");
    await page.getByRole("link", { name: "Si", exact: true }).click();
    await page.waitForSelector("#record-inputs");
    check(await page.locator("#record-inputs .file-row").count() === 8, "Si has eight actual archived inputs");
    await page.locator("#record-bands img").scrollIntoViewIfNeeded();
    await page.locator("#record-bands img").evaluate(img => img.decode());
    check(await page.locator("#record-bands img").evaluate(img => img.complete && img.naturalWidth > 0), "real band figure loads");
    await screenshot("silicon-bands.png");
    await page.getByRole("button", { name: "View inputs (8)", exact: true }).click();
    await page.locator("#record-inputs .file-row").first().getByRole("button", { name: "View", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#file-preview pre").textContent.includes("INPUT_PARAMETERS"));
    check(await page.locator("#file-preview").isVisible(), "input preview dialog");
    await screenshot("input-preview.png");
    await page.keyboard.press("Escape");
    check(await page.locator("#file-preview").isHidden(), "Escape closes preview");
    const downloadPromise = page.waitForEvent("download");
    await page.locator("#record-inputs .file-row").first().getByRole("link", { name: /Download/ }).click();
    const download = await downloadPromise;
    check(download.suggestedFilename() === "INPUT", "native input download retains name");
    await page.locator(".section-nav [data-section='record-basis']").click();
    check(await page.locator("#record-basis .file-info > strong").allTextContents().then(names => names.includes("Si_ONCV_PBE-1.0.upf")), "exact basis name shown");
    check(await page.locator("#record-basis a[download='Si_ONCV_PBE-1.0.upf']").count() === 1, "exact basis download alias");
    await screenshot("silicon-input-basis.png");
    await page.locator(".section-nav [data-section='record-properties']").click();
    await page.getByRole("tab", { name: "Topology", exact: true }).click();
    check((await page.locator("#property-panel").innerText()).includes("No results reported"), "no fictional topology result");
    await page.keyboard.press("ArrowRight");
    check(await page.getByRole("tab", { name: "Optical", exact: true }).getAttribute("aria-selected") === "true", "keyboard property navigation");
    await page.locator(".breadcrumb a").click();
    check(await page.locator("#search").inputValue() === "Si", "back link preserves search");
    await go("#/material/mos2-table-gw");
    check((await page.locator("#record-inputs").innerText()).includes("Inputs not archived"), "missing inputs explicit");
    check(await page.locator("#record-inputs a[download]").count() === 0, "no synthetic missing-input download");
    await go("#/material/hbn-tzdp10-fgext-20261008");
    check((await page.locator(".result-primary").innerText()).includes("Restricted result"), "frontier path result is not an ordinary GW gap");
    check((await page.locator("#record-overview").innerText()).includes("6.94183"), "original restricted numerical result retained");
    await go("#/basis");
    check(await page.locator(".dimension-filter").isHidden(), "dimension filter hidden in basis mode");
    check(await page.locator("#status-filter-control").isVisible(), "publication filter visible in basis mode");
    const unnamed = data.basis_sets.find(set => set.files.some(file => file.name_source === "descriptive_alias" && file.role === "nao"));
    check(Boolean(unnamed), "real missing-original-name fixture exists");
    await go(`#/basis/${encodeURIComponent(unnamed.id)}`);
    check((await page.locator("#basis-assets").innerText()).includes("original filename not recorded"), "unknown original filename is disclosed");
    check(await page.locator("#basis-assets .file-info > strong").allTextContents().then(names => names.every(name => name !== "payload")), "no payload placeholders displayed");
    await screenshot("basis-files.png");
    for (const file of inputs) {
      const fetched = await context.request.get(new URL(file.path, archive).href);
      check(fetched.ok(), `input is downloadable: ${file.path}`);
      check(createHash("sha256").update(await fetched.body()).digest("hex") === file.sha256, `input content hash: ${file.path}`);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await go("");
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "mobile document has no horizontal overflow");
    check(await page.locator(".table-wrap").evaluate(el => el.scrollWidth > el.clientWidth), "mobile table remains independently scrollable");
    await screenshot("materials-mobile.png");
    await go("#/material/si-paper-all_kpath");
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "mobile detail has no horizontal overflow");
    await screenshot("silicon-mobile.png");
    await go("#/material/not-a-record");
    check((await page.locator("#detail-view").innerText()).includes("Record not found"), "unknown ID handled");
    await go("#/material/%E0%A4%A");
    check((await page.locator("#detail-view").innerText()).includes("Record not found"), "malformed URL handled");
    const failure = await context.newPage();
    await failure.route("**/data.json", route => route.fulfill({ status: 503, body: "Unavailable" }));
    await failure.goto(base.href, { waitUntil: "domcontentloaded" });
    await failure.waitForSelector("#load-error:not([hidden])");
    check((await failure.locator("#load-error").innerText()).includes("503"), "catalog network errors shown honestly");
    check(errors.length === 0, `browser errors: ${errors.join("; ")}`);
    console.log(JSON.stringify({ passed: true, checks, calculations: calculations.length, basis_sets: data.basis_sets.length, input_files_verified: inputs.length, browser_errors: errors }, null, 2));
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error.stack); process.exitCode = 1; });
