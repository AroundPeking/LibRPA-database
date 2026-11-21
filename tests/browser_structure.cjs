// Optional browser regression: NODE_PATH must resolve Playwright, as in browser_smoke.cjs.
// Serve a build at CATALOG_URL (default http://127.0.0.1:8765/database/).
// External structure responses use byte-exact archived MgO fixtures; no archive access is needed.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { createHash } = require("node:crypto");

async function main() {
  const base = process.env.CATALOG_URL || "http://127.0.0.1:8765/database/";
  const bytes = readFileSync(path.join(__dirname, "fixtures/structures/mgo.STRU"));
  const aimsBytes = readFileSync(path.join(__dirname, "fixtures/structures/mgo.geometry.in"));
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH } : {}) });
  let checks = 0;
  const check = (value, message) => { assert.ok(value, message); checks++; };
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, reducedMotion: "reduce" });
    const page = await context.newPage(), errors = [];
    page.on("pageerror", error => errors.push(error.message));
    let corrupt = false, primaryFails = false;
    await context.route(/https:\/\/(huggingface\.co|hf-mirror\.com)\//, async route => {
      if (primaryFails && route.request().url().startsWith("https://huggingface.co/")) return route.abort();
      if (route.request().url().endsWith("/STRU")) return route.fulfill({ body: corrupt ? "corrupt structure" : bytes, headers: { "access-control-allow-origin": "*" } });
      if (route.request().url().endsWith("/geometry.in")) return route.fulfill({ body: aimsBytes, headers: { "access-control-allow-origin": "*" } });
      return route.abort();
    });
    const open = async () => {
      await page.goto(`${base}#/material/mgo-paper-fix_gap`);
      await page.locator("#record-structure > summary").click();
      await page.waitForSelector(".structure-canvas svg");
    };
    await open();
    check(await page.locator(".structure-canvas svg").count() === 2, "both scenes render");
    check(await page.locator(".structure-status").isHidden(), "successful load has no status banner");
    check(await page.locator("[data-structure-source]").count() === 0, "no structure selector");
    check(await page.locator("#record-structure .file-row").boundingBox().then(async file => (await page.locator(".structure-preview").boundingBox()).y >= file.y + file.height), "preview follows its download row");
    check(await page.locator('[data-structure-panel="bz"] svg path[fill-opacity]').count() === 14, "FCC zone has 14 faces");
    check(await page.locator('[data-structure-panel="bz"] [data-special-point]').evaluateAll(nodes=>nodes.map(n=>n.dataset.specialPoint).join(",")) === "Γ,X,W,K,L,U", "FCC special points are labeled");
    check(await page.locator(".structure-metrics").textContent().then(s=>s.includes("2 atoms per input cell")), "actual atom count");
    const cell = page.locator('[data-structure-panel="cell"] .structure-canvas');
    const initial = await cell.innerHTML();
    await cell.focus(); await page.keyboard.press("ArrowRight");
    check(await cell.innerHTML() !== initial, "keyboard rotation");
    await page.getByRole("button", { name: "Reset Crystal structure view", exact: true }).click();
    check(await cell.innerHTML() === initial, "reset view");
    const box = await cell.boundingBox();
    await page.mouse.move(box.x+100, box.y+90); await page.mouse.down(); await page.mouse.move(box.x+170, box.y+120); await page.mouse.up();
    check(await cell.innerHTML() !== initial, "pointer rotation");
    check(await page.locator(".structure-preview select").count() === 0, "preview has no display selector");
    await page.getByRole("button", { name: "Zoom in First Brillouin zone", exact: true }).click();
    check(await page.locator('[data-structure-panel="bz"] svg').count() === 1, "zone zoom");
    await page.getByRole("button", { name: "Reset Crystal structure view", exact: true }).click();
    await page.getByRole("button", { name: "Reset First Brillouin zone view", exact: true }).click();
    await page.locator("#record-structure").scrollIntoViewIfNeeded();
    const screenshot = async name => {
      if (process.env.SCREENSHOT_DIR) await page.locator("#record-structure").screenshot({ path: path.join(process.env.SCREENSHOT_DIR, name), style: ".site-header,.site-footer,.skip-link{visibility:hidden!important}" });
    };
    await screenshot("structure-desktop.png");
    await page.locator("#theme-toggle").click();
    check(await page.locator(".structure-canvas svg").count() === 2, "theme switch preserves scenes");
    await screenshot("structure-dark.png");
    await page.setViewportSize({ width: 390, height: 844 });
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), "mobile has no horizontal overflow");
    const panels = await page.locator(".structure-plot").evaluateAll(nodes=>nodes.map(n=>n.getBoundingClientRect().toJSON()));
    check(panels[1].y >= panels[0].y+panels[0].height, "mobile panels stack");
    await screenshot("structure-mobile.png");
    corrupt = true;
    await page.reload();
    await page.locator("#record-structure > summary").click();
    await page.waitForFunction(()=>document.querySelector(".structure-status").textContent.includes("SHA-256 mismatch"));
    check(await page.locator(".structure-canvas svg").count() === 0, "bad bytes never render stale geometry");
    corrupt = false; primaryFails = true;
    await page.locator("[data-structure-retry]").click();
    await page.waitForSelector(".structure-canvas svg");
    check(await page.locator(".structure-canvas svg").count() === 2, "mirror fallback and retry");
    await page.goto(`${base}#/materials`); await open();
    check(await page.locator(".structure-canvas svg").count() === 2, "route re-entry");

    await page.goto(`${base}#/material/mgo-jctc-aims-gw`);
    await page.locator("#record-structure > summary").click();
    await page.waitForSelector(".structure-canvas svg");
    check(await page.locator(".structure-canvas svg").count() === 2 && await page.locator(".structure-metrics").textContent().then(s=>s.includes("2 atoms per input cell")), "archived FHI-aims geometry renders both scenes");
    check(await page.locator('[data-structure-panel="bz"] [data-special-point]').count() === 6, "FHI-aims FCC special points are labeled");
    if (process.env.SCREENSHOT_DIR) await page.locator("#record-structure").screenshot({ path: path.join(process.env.SCREENSHOT_DIR, "structure-fhi-aims.png"), style: ".site-header,.site-footer,.skip-link{visibility:hidden!important}" });

    // Each preview is bound to the downloadable file directly above it.
    const fixture = { path: "data/solid__STRU", sha256: createHash("sha256").update(bytes).digest("hex"), tier: "referenced", external_url: "https://hf-mirror.com/stage/STRU" };
    const aimsFixture = { path: "data/geometry.in", sha256: createHash("sha256").update(aimsBytes).digest("hex"), tier: "referenced", external_url: "https://hf-mirror.com/stage/geometry.in" };
    await page.evaluate(async ({ fixture, aimsFixture }) => {
      const { structurePreview, installStructurePreview } = await import("./structure.mjs");
      const { renderFiles } = await import("./files.mjs");
      const view=document.createElement("div");
      const record={files:{inputs:[fixture,aimsFixture]}};
      view.innerHTML=`<details id="record-structure">${record.files.inputs.map(file=>`<div class="structure-attachment">${renderFiles([file],{input:true})}${structurePreview(file)}</div>`).join("")}</details>`;
      document.querySelector("#detail-view").replaceWith(view);
      installStructurePreview(view,()=>record);
      view.querySelector("details").open=true;
    }, { fixture, aimsFixture });
    await page.waitForFunction(()=>document.querySelectorAll(".structure-canvas svg").length === 4);
    check(await page.locator(".structure-preview").count() === 2, "each downloadable file has its own preview");
    check(errors.length === 0, `no browser exceptions: ${errors.join(", ")}`);
    console.log(`${checks} structure browser checks passed (archived MgO fixture; desktop and mobile).`);
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
