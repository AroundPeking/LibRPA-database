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
  const { parseRadial, radialSvg } = await import("../database/radial.mjs");
  const output = process.env.SCREENSHOT_DIR;
  if (output) assert.ok(fs.statSync(output).isDirectory(), "SCREENSHOT_DIR must exist");
  const launchOptions = { headless: true };
  if (process.env.CHROMIUM_EXECUTABLE_PATH) launchOptions.executablePath = process.env.CHROMIUM_EXECUTABLE_PATH;
  const browser = await chromium.launch(launchOptions);
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
      await page.waitForFunction(() => document.querySelector("#catalog").getAttribute("aria-busy") === "false" || document.querySelector("#detail-view h1") || !document.querySelector("#landing-view").hidden);
    };
    const screenshot = async name => { if (output) await page.screenshot({ path: path.join(output, name), fullPage: false }); };
    await go("");
    await page.waitForSelector("#landing-view:not([hidden])");
    await page.waitForSelector("#landing-stats strong");
    check(await page.locator("#landing-view").isVisible(), "根路由进入封面页而非直接数据列表");
    check(await page.locator("#home-view").isHidden(), "封面页隐藏目录外壳");
    await page.waitForFunction(() => getComputedStyle(document.querySelector(".site-header")).visibility === "hidden", null, { timeout: 5000 });
    check(await page.evaluate(() => document.body.classList.contains("cover-mode") && getComputedStyle(document.querySelector(".site-header")).visibility === "hidden"), "封面模式隐去顶栏，聚焦徽章");
    const coverBox = await page.locator(".cover").boundingBox();
    check(Math.abs((coverBox.x + coverBox.width / 2) - 1440 / 2) < 4 && coverBox.height >= 1049, "封面占满整个视口且水平居中");
    const landingEmblem = page.locator(".landing-emblem");
    await landingEmblem.evaluate(img => img.decode());
    check(await landingEmblem.evaluate(img => img.complete && img.naturalWidth === 540), "封面大徽章（方案A渲染全内容）以全分辨率加载");
    const emblemBox = await landingEmblem.boundingBox();
    check(Math.abs((emblemBox.x + emblemBox.width / 2) - 1440 / 2) < 40 && Math.abs((emblemBox.y + emblemBox.height / 2) - 1050 / 2) < 160, "徽章位于屏幕正中心（视觉焦点）");
    const landingEmblemUrl = await landingEmblem.evaluate(img => img.src);
    check(new URL(landingEmblemUrl).pathname === new URL("logo-emblem.png", base).pathname, "封面徽章解析到部署子路径");
    check(await landingEmblem.evaluate(img => { const tile = getComputedStyle(img.parentElement); return tile.backgroundColor === "rgb(255, 255, 255)" && tile.borderRadius !== "0px" && tile.padding !== "0px"; }), "封面徽章坐在白色圆角瓷砖上（预览同款展示）");
    check(await page.locator(".cover-orbit").evaluate(orbit => { const anims = orbit.getAnimations(); return anims.length === 1 && anims[0].playbackRate === 1 && getComputedStyle(orbit).borderRadius === "50%"; }), "徽章外圈极化星环由 WAAPI 驱动常速旋转（RPA 轨道动画）");
    check(await page.locator(".cover-stack").evaluate(stack => getComputedStyle(stack).animationName === "cover-rise"), "封面内容有入场动画");
    const landingText = await page.locator("#landing-view").innerText();
    check(!/Public preview|strict archive validation|evidence issues|Website publication is not scientific acceptance|Archive only|CI blocked/i.test(landingText), "封面与介绍区不暴露内部审计或草稿文案");
    check(!/[\u3400-\u9fff]/.test(landingText), "封面与介绍区全部英文");
    const landingStatValues = await page.locator("#landing-stats strong").allTextContents();
    check(landingStatValues.length === 4, "落地统计四项");
    check(landingStatValues[0] === `${calculations.length}`, "落地统计的计算记录数与目录一致");
    const landingCoverage = await page.locator("#landing-coverage").innerText();
    check(landingCoverage.includes("3D") && landingCoverage.includes("2D") && landingCoverage.includes("spin"), "落地覆盖行列出维度与自旋构成");
    check(await page.locator('.cover-actions a[href="#/materials"]').count() === 1 && await page.locator(".cover-links a").count() === 2, "封面主入口与两个次级入口齐备");
    check(await page.locator('[data-nav="materials"]').getAttribute("href") === "#/materials", "Materials 导航指向列表路由");
    check(await page.locator(".landing-methods .method-tag").count() === 5, "方法图例五枚标签（PBE/EXX/GW/SOC/SPIN）");
    check(await page.locator(".cover-actions .primary-button").evaluate(button => button.getBoundingClientRect().top < innerHeight), "桌面封面主按钮在首屏内");
    await page.mouse.move(360, 300, { steps: 4 });
    await page.waitForTimeout(350);
    check(await page.locator(".cover-stage-wrap").evaluate(node => getComputedStyle(node).transform !== "none"), "鼠标视差：舞台整体随指针微移");
    check(await page.locator(".cover-orbit").evaluate(node => getComputedStyle(node).translate !== "none"), "鼠标视差：星环反向漂移形成景深");
    check(await page.locator(".cover-emblem").evaluate(node => getComputedStyle(node).transform !== "none"), "鼠标视差：徽章随指针 3D 微倾");
    await page.hover(".cover-emblem");
    await page.waitForTimeout(450);
    check(await page.locator(".cover-orbit").evaluate(node => node.getAnimations()[0]?.playbackRate > 3), "悬停徽章时星环平滑加速");
    await screenshot("landing-cover.png");
    await page.click(".cover-emblem");
    await page.waitForSelector(".cover-fly-clone");
    await page.waitForSelector(".material-row");
    await page.waitForSelector(".cover-fly-clone", { state: "detached" });
    check(await page.locator("#landing-view").isHidden(), "点击徽章触发飞向品牌位的过场动画后进入目录（无整页刷新）");
    check(await page.evaluate(() => !document.body.classList.contains("cover-mode") && getComputedStyle(document.querySelector(".site-header")).visibility === "visible"), "进入目录后顶栏回归");
    await page.click(".brand");
    await page.waitForSelector("#landing-view:not([hidden])");
    check(await page.locator("#home-view").isHidden() && await page.evaluate(() => document.body.classList.contains("cover-mode")), "点击品牌徽标返回封面");
    await page.click("#cover-scroll");
    await page.waitForFunction(() => !document.body.classList.contains("cover-mode"), null, { timeout: 5000 });
    check(await page.evaluate(() => !document.body.classList.contains("cover-mode") && getComputedStyle(document.querySelector(".site-header")).visibility === "visible"), "下滚离开封面后顶栏滑回");
    check(await page.locator("#landing-stats").evaluate(node => node.getBoundingClientRect().top < window.innerHeight), "下滚提示把介绍统计带进视口");
    await page.fill("#landing-search-input", "Si");
    await page.press("#landing-search-input", "Enter");
    await page.waitForSelector(".material-row");
    check((await page.locator("#result-count").innerText()).includes("matching"), "落地搜索提交后路由进入过滤后的目录");
    await go("#/materials");
    await page.waitForSelector(".material-row");
    const reducedContext = await browser.newContext({ viewport: { width: 1440, height: 1050 }, colorScheme: "dark", reducedMotion: "reduce" });
    const reducedPage = await reducedContext.newPage();
    reducedPage.on("pageerror", error => errors.push(error.message));
    await reducedPage.goto(base.href, { waitUntil: "domcontentloaded" });
    await reducedPage.waitForSelector("#landing-stats strong");
    check(await reducedPage.locator(".cover-orbit").evaluate(node => node.getAnimations().length === 0), "减少动态偏好下星环静止");
    await reducedPage.click(".cover-emblem");
    await reducedPage.waitForSelector(".material-row");
    check(await reducedPage.locator(".cover-fly-clone").count() === 0, "减少动态偏好下直接进入目录，无飞行过场");
    await reducedContext.close();
    const homeText = await page.locator("body").innerText();
    check(await page.locator("#archive-status").count() === 0, "正式网站不展示内部完整性状态横幅");
    check(!/Public preview|strict archive validation|evidence issues|Website publication is not scientific acceptance|Archive only|CI blocked/i.test(homeText), "首页不暴露内部审计或草稿状态文案");
    check(await page.locator('a[href="missing-evidence.html"]').count() === 0, "网站导航不公开缺项审计页面");
    check(!/[\u3400-\u9fff]/.test(await page.locator("body").innerText()), "首页全部英文");
    check(await page.locator("#catalog img").count() === 0, "no list figure previews");
    check(await page.locator("#status-filter-control").isHidden(), "basis-only filter is hidden");
    check((await page.locator("#result-count").innerText()).includes(`${calculations.length} of ${calculations.length}`), "inventory count");
    const logo = page.locator(".brand-mark");
    await logo.evaluate(img => img.decode());
    check(await logo.evaluate(img => img.complete && img.naturalWidth === 320), "Plan A render brand mark loads");
    check(await logo.getAttribute("aria-hidden") === "true" && await logo.getAttribute("alt") === "", "brand mark is decorative");
    check(await logo.evaluate(img => getComputedStyle(img).backgroundColor === "rgb(255, 255, 255)" && getComputedStyle(img).borderRadius !== "0px"), "brand mark sits on a rounded white tile like the showcase stage");
    check((await page.locator(".brand span").innerText()).includes("MATERIALS DATABASE"), "brand text sits beside the emblem mark");
    const logoUrl = await logo.evaluate(img => img.src);
    check(new URL(logoUrl).pathname === new URL("logo-mark.png", base).pathname, "brand mark resolves at deployed catalog subpath");
    check(await page.locator("link[rel='icon']").evaluate(link => new URL(link.href).pathname) === new URL("favicon.svg", base).pathname, "favicon is the vector icon at the catalog subpath");
    check(await page.locator("link[rel='apple-touch-icon']").evaluate(link => new URL(link.href).pathname) === new URL("apple-touch-icon.png", base).pathname, "apple-touch-icon is linked at the catalog subpath");
    check(await page.locator("#search").evaluate(input => input.getBoundingClientRect().bottom <= innerHeight), "desktop search is visible in first viewport");
    await screenshot("materials-desktop.png");
    for (const expected of [
      { id: "c512-gamma-g0w0-20260519", states: "6656", atoms: "512", gap: "6.09949", wall: "18:42:46", nodes: "4", mpi: "4", omp: "96" },
      { id: "c1024-gamma-g0w0-20260521", states: "13312", atoms: "1024", gap: "6.22160", wall: "16:50:12", nodes: "18", mpi: "36", omp: "48" },
    ]) {
      const record = calculations.find(item => item.id === expected.id);
      check(record?.record_type === "large_system_gw", `${expected.id} is a large-system GW record`);
      await go(`#/material/${expected.id}`);
      const text = await page.locator("#detail-view").innerText();
      check(text.includes("Sampled Γ G0W0 gap") && text.includes(expected.gap), `${expected.id} shows the sampled Γ result`);
      check(text.includes(`${expected.states}`) && text.includes(`${expected.atoms}`), `${expected.id} shows QP-state and atom counts`);
      check(text.includes(expected.wall) && text.includes(`Nodes\n${expected.nodes}`) && text.includes(`MPI ranks\n${expected.mpi}`) && text.includes(`OpenMP threads / rank\n${expected.omp}`), `${expected.id} shows immutable runtime resources`);
      check(await page.locator("#record-bands").count() === 0 && await page.locator("#record-results img").count() === 0, `${expected.id} does not fabricate a band section or figure`);
      check(/^[0-9a-f]{64}$/.test(record.software?.abacus?.executable_sha256 || "") && /^[0-9a-f]{64}$/.test(record.software?.librpa?.executable_sha256 || ""), `${expected.id} exposes executable identities`);
    }
    const c2048 = calculations.find(item => item.id === "c2048-reader-v1-20260607");
    check(c2048?.record_type === "reader_conversion", "C2048 remains a reader-conversion provenance record");
    check(c2048?.associated_gw_run?.job_id === "20959369" && c2048.associated_gw_run.scheduler_state === "COMPLETED", "C2048 links the completed historical GW audit");
    await go("#/material/c2048-reader-v1-20260607");
    const c2048Text = await page.locator("#detail-view").innerText();
    check(c2048Text.includes("Reader-v1 conversion with linked GW completion audit") && c2048Text.includes("Reader-v1 states\n26624") && c2048Text.includes("Matrix rows\n26624") && c2048Text.includes("Matrix columns\n26624"), "C2048 preserves conversion scope and matrix dimensions below the gap headline");
    check(c2048Text.includes("Sampled Γ PBE gap") && c2048Text.includes("4.28728") && c2048Text.includes("5.74313") && c2048Text.includes("Γ gaps verified"), "C2048 shows verified sampled Gamma gaps from the complete QP output");
    check(c2048Text.includes("0.585339 Ha") && c2048Text.includes("Fermi energy, not a gap"), "C2048 labels the retained energy as Fermi energy rather than a gap");
    check(c2048Text.includes("frontier states") && c2048Text.includes("13:17:56"), "C2048 explains the frontier states and retained runtime");
    check(!/fundamental gap|315\.02863/.test(c2048Text), "C2048 exposes no fabricated gap or unrelated high-energy state");
    check(await page.locator("#record-bands, #record-results").count() === 0, "C2048 does not expose a fabricated band or QP-table section");
    await go("#/materials");
    await page.getByRole("button", { name: "Next page", exact: true }).click();
    check((await page.locator(".pagination").innerText()).includes("Page 2"), "pagination");
    await page.locator("#search").fill("MoS₂");
    check(await page.locator(".material-row").count() > 0, "Unicode formula search");
    await page.locator("#search").fill("MoS₂ WS₂");
    check((await page.locator("#result-count").innerText()).startsWith("1 of"), "formula search narrows to the heterostructure record only");
    await page.locator("#search").fill("gaas-abacus-gw-soc-32freq");
    check((await page.locator("#result-count").innerText()).startsWith("1 of"), "record id search isolates one record");
    check(await page.locator(".material-row .method-soc").count() === 1, "materials list shows the SOC label on the GaAs SOC record");
    check((await page.locator(".material-row .method-dft").first().innerText()) === "PBE", "materials list shows the recorded functional instead of generic DFT");
    await page.locator("#search").fill("nio-aims-gw-int");
    check((await page.locator("#result-count").innerText()).startsWith("1 of"), "record id search isolates the aims NiO record");
    check((await page.locator(".material-row .method-dft").first().innerText()) === "PBE", "input-declared functional lights the chip without a PBE-labeled property");
    await page.locator("#search").fill("gaas-abacus-gw-soc-32freq");
    await go("#/material/gaas-abacus-gw-soc-32freq");
    await page.waitForSelector(".detail-tags");
    check(await page.locator(".detail-tags .method-soc").count() === 1, "detail page shows the SOC label");
    check(await page.locator(".detail-tags .method-dft").count() === 1 && (await page.locator(".detail-tags .method-dft").innerText()) === "PBE", "detail page method chip carries the functional name");
    await go("#/materials");
    await page.locator("#search").fill("nio-aims-gw-int");
    check((await page.locator("#result-count").innerText()).startsWith("1 of"), "NiO record id search isolates one record");
    check(await page.locator(".material-row .method-spin").count() === 1, "materials list shows the SPIN label on the NiO record");
    check(await page.locator(".material-row .method-soc").count() === 0, "NiO is spin-polarized without SOC");
    await go("#/material/nio-aims-gw-int");
    await page.waitForSelector(".detail-tags");
    check(await page.locator(".detail-tags .method-spin").count() === 1, "detail page shows the SPIN label");
    await go("#/materials");
    await page.locator("#search").fill("Si");
    await go("#/material/si-paper-all_kpath");
    await page.waitForSelector("#record-inputs");
    check(await page.locator("#record-inputs .file-row").count() === 8, "Si has eight actual archived inputs");    const firstBandFigure = page.locator("#record-bands > .section-body > .figure-grid img").first();
    await firstBandFigure.scrollIntoViewIfNeeded();
    await firstBandFigure.evaluate(img => img.decode());
    check(await firstBandFigure.evaluate(img => img.complete && img.naturalWidth > 0), "real band figure loads");
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
    check((await page.locator("#property-panel").innerText()).includes("No values recorded"), "no fictional topology result");
    await page.keyboard.press("ArrowRight");
    check(await page.getByRole("tab", { name: "Optical", exact: true }).getAttribute("aria-selected") === "true", "keyboard property navigation");
    await page.locator(".breadcrumb a").click();
    check(await page.locator("#search").inputValue() === "Si", "back link preserves search");
    const previewAndDownload = async (row, file, expectedName, description) => {
      const fetched = await context.request.get(new URL(file.path, archive).href);
      check(fetched.ok(), `${description}：文件可读取`);
      const bytes = await fetched.body();
      check(createHash("sha256").update(bytes).digest("hex") === file.sha256, `${description}：归档哈希一致`);
      await row.getByRole("button", { name: "View", exact: true }).click();
      const prefix = bytes.subarray(0, 128).toString("utf8");
      await page.waitForFunction(expected => document.querySelector("#file-preview pre").textContent.startsWith(expected), prefix);
      check(await page.locator("#file-preview .preview-path").textContent() === file.path, `${description}：预览对应真实路径`);
      await page.keyboard.press("Escape");
      await page.locator("#file-preview").waitFor({ state: "hidden" });
      let downloaded = null;
      for (let attempt = 1; attempt <= 3 && !downloaded; attempt++) {
        console.error("[smoke] download:", description, attempt > 1 ? `(retry ${attempt})` : "");
        const pendingDownload = page.waitForEvent("download", { timeout: attempt === 3 ? 60000 : 20000 });
        await row.getByRole("link", { name: /Download/ }).click();
        try { downloaded = await pendingDownload; }
        catch (error) { if (attempt === 3) throw error; }
      }
      check(downloaded.suggestedFilename() === expectedName, `${description}：下载保留计算文件名`);
      const saved = await downloaded.path();
      check(saved && createHash("sha256").update(fs.readFileSync(saved)).digest("hex") === file.sha256, `${description}：原生下载字节一致`);
    };
    for (const id of ["mos2-table-gw", "wse2-table-gw"]) {
      const record = calculations.find(item => item.id === id);
      check(Boolean(record), `${id}：真实记录存在`);
      check(record.files.inputs.length === 8, `${id}：八份控制文件已进入catalog`);
      await go(`#/material/${encodeURIComponent(id)}`);
      check(await page.locator("[data-nav='materials']").getAttribute("aria-current") === "page", `${id}：直接详情路由标记Materials`);
      const rows = page.locator("#record-inputs .file-row");
      check(await rows.count() === 8, `${id}：八份控制文件显示`);
      for (const [index, file] of record.files.inputs.entries()) {
        await previewAndDownload(rows.nth(index), file, path.basename(file.path), `${id} / ${path.basename(file.path)}`);
      }
      await page.locator(".section-nav [data-section='record-basis']").click();
      check(record.species.length === 2 && record.species.every(species => species.set_id), `${id}：两物种均有exact binding`);
      check(await page.locator("#record-basis .binding-card .file-row").count() === 6, `${id}：六份exact基组角色文件显示`);
      for (const [index, species] of record.species.entries()) {
        const set = data.basis_sets.find(item => item.id === species.set_id);
        check(Boolean(set), `${id} / ${species.element}：exact set存在`);
        const payloads = set.files.filter(file => ["pp", "nao", "abf", "for_aux"].includes(file.role));
        check(payloads.length === 3 && ["pp", "nao", "abf"].every(role => payloads.filter(file => file.role === role).length === 1), `${id} / ${species.element}：PP、NAO、ABF各一份`);
        const binding = page.locator("#record-basis .binding-card").nth(index);
        for (const [fileIndex, file] of payloads.entries()) {
          const expectedName = species.asset_aliases[file.role];
          check(Boolean(expectedName), `${id} / ${species.element} / ${file.role}：计算原名存在`);
          check(await binding.locator(".file-info > strong").nth(fileIndex).textContent() === expectedName, `${id} / ${species.element} / ${file.role}：exact原名显示`);
          await previewAndDownload(binding.locator(".file-row").nth(fileIndex), file, expectedName, `${id} / ${species.element} / ${file.role}`);
        }
      }
    }
    for (const material of ["GeTe", "SnSe"]) {
      const record = calculations.find(item => item.dimension === "2d" && item.material === material);
      check(Boolean(record), `${material}：真实二维诊断记录存在`);
      check(Array.isArray(record.method_diagnostics), `${material}：方法诊断使用列表合同`);
      const diagnostic = record.method_diagnostics.find(item => item.method === "EXX");
      check(diagnostic && diagnostic.full_raw_path_gap_ev < 0 && diagnostic.frozen_window_path_gap_ev < 0, `${material}：全raw与冻结窗异常分别保留`);
      check(!record.properties.some(item => /^(?:band_gap|sampled_path_gap(?:_ev)?|path_gap(?:_ev)?)$/.test(item.key) && item.method === "EXX" && item.status !== "failed"), `${material}：EXX异常不伪造普通gap`);
      await go(`#/material/${encodeURIComponent(record.id)}`);
      const overview = await page.locator("#record-overview").innerText();
      check(!overview.includes(String(diagnostic.full_raw_path_gap_ev)) && !overview.includes(String(diagnostic.frozen_window_path_gap_ev)) && !overview.includes("not an accepted"), `${material}：内部异常诊断不出现在正式页面`);
      check((await page.locator(".result-strip > div").nth(1).innerText()).includes("—"), `${material}：结果条EXX不显示未定义gap`);
      await screenshot(`${material.toLowerCase()}-exx-diagnostic.png`);
    }
    const partialRecords = calculations.filter(record => record.source?.stage_input_receipt);
    check(partialRecords.length === 9, "nine recovered cases remain explicitly partial");
    let partialInputsVerified = 0;
    for (const record of partialRecords) {
      check(record.archive_completeness?.status === "incomplete", `${record.id}: controls do not promote upload completeness`);
      check(record.species.length === 0 || Boolean(record.source?.producer_assets_receipt) || /^[0-9a-f]{64}$/.test(record.source?.approval_candidate_sha256 || ""), `${record.id}: any recovered basis binding requires producer asset evidence or an approved hash-bound production audit`);
      await go(`#/material/${encodeURIComponent(record.id)}`);
      await page.locator(".section-nav [data-section='record-inputs']").click();
      const panel = page.locator("#record-inputs");
      check((await panel.innerText()).includes("Stage-resolved calculation inputs"), `${record.id}: stage-resolved input description visible`);
      const receiptLink = panel.getByRole("link", { name: "View stage-input receipt ↗", exact: true });
      check(await receiptLink.getAttribute("href") === `../${record.source.stage_input_receipt}`, `${record.id}: receipt link targets this case`);
      const receiptResponse = await context.request.get(new URL(record.source.stage_input_receipt, archive).href);
      check(receiptResponse.ok(), `${record.id}: actual receipt downloadable`);
      const receiptBytes = await receiptResponse.body();
      const receiptItem = record.files.results.find(file => file.path === record.source.stage_input_receipt);
      check(createHash("sha256").update(receiptBytes).digest("hex") === receiptItem.sha256, `${record.id}: receipt SHA verified`);
      const receipt = JSON.parse(receiptBytes.toString("utf8"));
      check(receipt.case_id === record.id && receipt.full_runtime_handoff_verified === false && receipt.runtime_asset_seal_verified === false && receipt.scientific_acceptance_reassessed === false && receipt.automatic_import_candidate_promoted === false, `${record.id}: receipt preserves evidence boundaries`);
      const rows = panel.locator(".file-row");
      check(await rows.count() === record.files.inputs.length && receipt.control_count === record.files.inputs.length, `${record.id}: receipt/catalog/UI input counts agree`);
      check((await panel.innerText()).includes("File transformations are recorded"), `${record.id}: transformation provenance note visible`);
      for (const [index, file] of record.files.inputs.entries()) {
        const row = rows.nth(index);
        await previewAndDownload(row, file, path.basename(file.path), `${record.id} / ${file.stage_id} / ${path.basename(file.path)}`);
        if (file.transformation !== "none") {
          check(!/[0-9a-f]{40,}/i.test(await row.innerText()), `${record.id}: redacted input row exposes no digest`);
          check(file.original_sha256 !== file.sha256, `${record.id}: redacted bytes have distinct SHA`);
        }
        partialInputsVerified += 1;
      }
    }
    check(partialInputsVerified === 89, "89 partial controls previewed and natively downloaded byte-for-byte");
    const withoutInputs = calculations.find(record => record.record_type !== "reader_conversion" && !(record.files?.inputs || []).length);
    if (withoutInputs) {
      await go(`#/material/${encodeURIComponent(withoutInputs.id)}`);
      check((await page.locator("#record-inputs").innerText()).includes("Calculation results"), "无输入记录使用正式中性说明");
      check(await page.locator("#record-inputs a[download]").count() === 0, "缺输入记录没有合成下载");
    } else {
      check(calculations.filter(record => record.record_type !== "reader_conversion").every(record => (record.files?.inputs || []).length > 0), "全部科学计算记录均有归档输入；转换凭据单独处理");
    }
    const audited = calculations.find(record => record.archive_completeness?.status === "incomplete");
    check(Boolean(audited), "内部审计样例存在");
    await go(`#/material/${encodeURIComponent(audited.id)}`);
    const formalText = await page.locator("#detail-view").innerText();
    check(!/Archive completeness|Upload incomplete|CI blocked|evidence issues|Missing evidence|Full commit not recorded/i.test(formalText), "内部审计字段不出现在正式详情页");
    check(await page.locator("#record-evidence > summary h2").textContent() === "Software & logs", "软件与日志使用正式分区名称");
    await page.locator(".section-nav [data-section='record-evidence']").click();
    const softwareEntries = page.locator("#record-evidence .software-entry");
    check(await softwareEntries.count() === 2, "两软件入口均保留");
    for (const [index, name] of ["abacus", "librpa"].entries()) {
      const commit = audited.software?.[name]?.commit;
      const text = await softwareEntries.nth(index).innerText();
      if (commit) check(text.includes(commit), `${name}：已记录软件标识保持`);
      check(!text.includes("Full commit not recorded"), `${name}：不显示内部缺项警告`);
    }
    const alp = calculations.find(record => record.id === "alp-paper-k8_shrink_wing");
    check(Boolean(alp), "AlP真实样例存在");
    const alpGaps = alp.properties.filter(property => property.key === "band_gap");
    for (const [method, value] of [["PBE", 1.60680], ["EXX", 7.39451]]) {
      const property = alpGaps.find(item => item.method === method);
      check(property && Math.abs(property.value - value) < 1e-8, `AlP ${method}：catalog精确gap保留`);
    }
    await go(`#/material/${encodeURIComponent(alp.id)}`);
    check((await page.locator(".result-strip > div").nth(0).innerText()).includes("1.607"), "AlP PBE gap在结果条显示");
    check((await page.locator(".result-strip > div").nth(1).innerText()).includes("7.395"), "AlP EXX gap在结果条显示");
    await page.locator(".section-nav [data-section='record-properties']").click();
    for (const [method, value] of [["PBE", 1.60680], ["EXX", 7.39451]]) {
      const row = page.locator("#property-panel tbody tr").filter({ has: page.getByRole("cell", { name: method, exact: true }) });
      check(Math.abs(Number(await row.locator(".property-value").innerText()) - value) < 1e-8, `AlP ${method}：属性表保留原始数值精度`);
    }
    const primaryFiles = alp.files.figures.filter(file => file.display_priority === "primary" && /\.(svg|png|jpe?g|webp)$/i.test(file.path));
    const originals = alp.files.figures.filter(file => file.display_priority !== "primary" && /\.(svg|png|jpe?g|webp)$/i.test(file.path));
    check(primaryFiles.length > 0 && originals.length > 0, "AlP主图与原图样例均存在");
    await page.locator(".section-nav [data-section='record-bands']").click();
    const primaryImages = page.locator("#record-bands > .section-body > .figure-grid img");
    for (let index = 0; index < await primaryImages.count(); index += 1) {
      await primaryImages.nth(index).scrollIntoViewIfNeeded();
      await primaryImages.nth(index).evaluate(img => img.decode());
      check(await primaryImages.nth(index).evaluate(img => img.complete && img.naturalWidth > 0), `AlP方法主图${index + 1}：真实SVG加载`);
    }
    await screenshot("alp-primary-bands.png");
    const imageSources = await primaryImages.evaluateAll(images => images.map(img => img.src));
    check(imageSources.length === primaryFiles.length && primaryFiles.every(file => imageSources.includes(new URL(file.path, archive).href)), "主网格仅显示primary新图");
    const originalPanel = page.locator("#record-bands .original-figures");
    check(await originalPanel.evaluate(details => !details.open), "原始图默认折叠");
    check(await originalPanel.locator("img").count() === originals.length, "原始图全部保留在折叠面板");
    await originalPanel.locator("summary").click();
    const originalImage = originalPanel.locator("img").first();
    await originalImage.scrollIntoViewIfNeeded();
    await originalImage.evaluate(img => img.decode());
    check(await originalImage.isVisible() && await originalImage.evaluate(img => img.naturalWidth > 0), "原图可展开且真实图像加载");
    const bandDownloadUrls = await page.locator("#record-bands a[download]").evaluateAll(links => links.map(link => link.href));
    check(alp.files.figures.every(file => bandDownloadUrls.includes(new URL(file.path, archive).href)), "新图、原图与所有sidecar均可下载");
    check((await page.locator("#record-bands > .section-body > .definition-note").innerText()).includes("recorded k-path"), "路径结果保留其定义与范围说明");
    const hbn = calculations.find(record => record.id === "hbn-tzdp10-fgext-20261008");
    check(hbn?.status === undefined && /raw-band/i.test(hbn?.summary?.observable || ""), "replacement hBN carries no record-level status and keeps its restricted path observable");
    await go("#/material/hbn-tzdp10-fgext-20261008");
    check(!/[\u3400-\u9fff]/.test(await page.locator("#detail-view").innerText()), "新hBN完整详情为英文且保留原始论文证据");
    const hbnHeadline = await page.locator(".result-primary").innerText();
    check(hbnHeadline.includes("GW band gap") && hbnHeadline.includes("6.94183 eV") && !hbnHeadline.includes("paper-reported"), "replacement hBN shows one database headline value without a repeated paper label");
    const reference = page.locator("#record-overview .reference-source");
    check(await reference.evaluate(details => !details.open), "reference evidence is collapsed by default");
    check(await reference.locator("table").count() === 0, "no repeated paper/archive value comparison table");
    await reference.locator("summary").click();
    check(await reference.locator("a").first().isVisible(), "source extract remains accessible after expansion");
    check(hbnHeadline.includes("Path-resolved value"), "paper headline keeps the path-resolved scope beside its number");
    check(!hbnHeadline.includes("Restricted result") && !hbnHeadline.includes("6.68084"), "replacement hBN does not hide its paper value or borrow the old value");
    check((await page.locator(".result-strip > div").nth(0).innerText()).includes("4.68813"), "replacement hBN shows its own cited KS value");
    check((await page.locator(".result-strip > div").nth(1).innerText()).includes("11.020"), "replacement hBN shows its own archived EXX value");
    check((await page.locator("#record-overview").innerText()).includes("6.94183"), "original restricted numerical result retained");
    check(await page.locator("#record-inputs .file-row").count() === 21, "replacement hBN has its 21 real inputs");
    const hbnFigures = hbn.files.figures.filter(file => file.display_priority === "primary");
    check(hbnFigures.length === 3, "replacement hBN has three traceable primary figures");
    await page.locator(".section-nav [data-section='record-bands']").click();
    for (const image of await page.locator("#record-bands > .section-body > .figure-grid img").all()) {
      await image.scrollIntoViewIfNeeded();
      await image.evaluate(img => img.decode());
      check(await image.evaluate(img => img.complete && img.naturalWidth > 0), "replacement hBN primary SVG loads");
    }
    for (const file of [...hbn.files.results.filter(file => /(?:KS|EXX|GW)_band_spin_1\.dat$/.test(file.path)), ...hbnFigures, ...hbn.files.figures.filter(file => /hbn_frontier_audit\.json$/.test(file.path))]) {
      const fetched = await context.request.get(new URL(file.path, archive).href);
      check(fetched.ok(), `replacement hBN evidence downloadable: ${file.path}`);
      check(createHash("sha256").update(await fetched.body()).digest("hex") === file.sha256, `replacement hBN evidence hash: ${file.path}`);
    }
    await screenshot("hbn-primary-bands.png");
    await go("#/materials");
    await page.locator("#search").fill("hBN");
    const replacementRow = page.locator(".material-row").filter({ has: page.locator("a[href='#/material/hbn-tzdp10-fgext-20261008']") });
    check((await replacementRow.innerText()).includes("6.942") && (await replacementRow.innerText()).includes("Path-resolved"), "replacement hBN list shows rounded paper number with path scope");
    check((await page.locator("#sort").innerText()).includes("Primary result"), "sorting label covers task-aware primary results");
    await go("#/basis");
    check(await page.locator(".dimension-filter").isHidden(), "dimension filter hidden in basis mode");
    check(await page.locator("#status-filter-control").count() === 0, "publication filter removed from basis mode");
    const unnamed = data.basis_sets.find(set => set.files.some(file => file.name_source === "descriptive_alias" && file.role === "nao"));
    check(Boolean(unnamed), "real missing-original-name fixture exists");
    await go(`#/basis/${encodeURIComponent(unnamed.id)}`);
    check((await page.locator("#basis-assets").innerText()).includes("Descriptive filename"), "descriptive filename is labelled");
    check(await page.locator("#basis-assets .file-info > strong").allTextContents().then(names => names.every(name => name !== "payload")), "no payload placeholders displayed");
    await screenshot("basis-files.png");
    check(await page.locator("[data-nav='basis']").getAttribute("aria-current") === "page", "直接basis详情路由标记Basis library");
    const radialSet = data.basis_sets.find(set => set.element === "Al" && set.files.some(file => file.role === "nao" && file.sha256 === "8d7e5a192b52a13b21df4cc2999fad022fb1e0de4b6d080c857b65b6085c4785"));
    check(Boolean(radialSet), "Al：真实多 l 物理 NAO 样例存在");
    let radialFilesVerified = 0;
    let radialChannelsVerified = 0;
    const verifyRadialFile = async (set, role, automaticallyLoaded = false) => {
      const file = set.files.find(item => item.role === role);
      check(Boolean(file), `${set.element} / ${role}：真实径向文件存在`);
      const fetched = await context.request.get(new URL(file.path, archive).href);
      check(fetched.ok(), `${set.element} / ${role}：原文件可读取`);
      const bytes = await fetched.body();
      check(createHash("sha256").update(bytes).digest("hex") === file.sha256, `${set.element} / ${role}：原文件 SHA-256 一致`);
      const radial = parseRadial(bytes.toString("utf8"), { allowHeaderMismatch: true });
      const filePanel = page.locator(`#basis-radial .radial-file[data-radial-path=${JSON.stringify(file.path)}]`);
      if (!automaticallyLoaded) {
        check(await filePanel.evaluate(details => !details.open), `${set.element} / ${role}：辅助文件不冒充自动加载的物理 NAO`);
        check(await filePanel.locator(".radial-card").count() === 0, `${set.element} / ${role}：加载前没有合成图`);
        await filePanel.locator(":scope > summary").click();
        await filePanel.locator("[data-radial-load]").click();
      }
      await filePanel.locator(".radial-status").filter({ hasText: "Verified ·" }).waitFor({ timeout: 60000 });
      check(await filePanel.evaluate(details => details.open), `${set.element} / ${role}：径向文件面板展开`);
      const status = await filePanel.locator(".radial-status").innerText();
      check(status.includes(`header element ${radial.element}`) && status.includes(`mesh ${radial.mesh}`) && status.includes(`dr ${radial.dr} bohr`), `${set.element} / ${role}：原头元素与原网格披露`);
      check(!/[0-9a-f]{64}/i.test(await filePanel.innerText()), `${set.element} / ${role}：径向面板不公开摘要哈希`);
      const groups = [...new Set(radial.channels.map(channel => channel.l))];
      const cards = filePanel.locator(".radial-card");
      check(await cards.count() === groups.length, `${set.element} / ${role}：每个有原通道的 l 独立一张卡片`);
      check(await cards.locator("svg").count() === groups.length, `${set.element} / ${role}：每个 l 恰好一幅 SVG，没有叠加不同 l`);
      for (const l of groups) {
        const channels = radial.channels.filter(channel => channel.l === l);
        const card = filePanel.locator(`.radial-card[data-radial-l='${l}']`);
        const expectedNs = channels.map(channel => channel.n);
        check((await card.locator("h3").innerText()).includes(`l=${l}`), `${set.element} / ${role} / l=${l}：卡片角动量准确`);
        const shown = await card.locator("path[data-channel]").evaluateAll(paths => paths.map(path => ({ n: Number(path.dataset.channel), title: path.querySelector("title").textContent, samples: (path.getAttribute("d").match(/[ML]/g) || []).length })));
        check(JSON.stringify(shown.map(item => item.n)) === JSON.stringify(expectedNs), `${set.element} / ${role} / l=${l}：全部原 N 保留且不重编号`);
        check(shown.every(item => item.samples === radial.mesh && item.title === `l=${l}, original N=${item.n}`), `${set.element} / ${role} / l=${l}：保留每个原样本且没有其他 l 曲线`);
        const toggles = card.locator("input[data-radial-n]");
        check(await toggles.count() === channels.length && await toggles.evaluateAll(inputs => inputs.every(input => input.checked)), `${set.element} / ${role} / l=${l}：同 l 每个 N 独立开关且默认全部显示`);
        check(await card.locator(".radial-metrics tbody tr").count() === channels.length, `${set.element} / ${role} / l=${l}：逐原 N 端点诊断，无验收阈值`);
      }
      radialFilesVerified += 1;
      radialChannelsVerified += radial.channels.length;
      return { file, radial, filePanel };
    };
    await go(`#/basis/${encodeURIComponent(radialSet.id)}`);
    const physical = await verifyRadialFile(radialSet, "nao", true);
    check(physical.radial.channels.length === 8 && new Set(physical.radial.channels.map(channel => channel.l)).size === 3, "Al：八个原径向函数分成三幅 l 图，NAO 无需点击自动加载");
    check(!(await physical.filePanel.locator(".radial-status").innerText()).includes("Header metadata note"), "Al：正常原轨道没有额外元数据说明");
    const firstRadial = physical.filePanel.locator(".radial-card[data-radial-l='0']");
    const otherRadial = physical.filePanel.locator(".radial-card[data-radial-l='1']");
    const otherSvg = await otherRadial.locator("svg").evaluate(svg => svg.outerHTML);
    const originalPaths = await firstRadial.locator("path[data-channel]").evaluateAll(paths => paths.map(path => path.getAttribute("d")));
    const expectedPaths = svg => [...svg.matchAll(/<path data-channel="\d+" d="([^"]+)"/g)].map(match => match[1]);
    check(JSON.stringify(originalPaths) === JSON.stringify(expectedPaths(radialSvg(physical.radial, 0))), "Al l=0：显示真实原 R(r)，没有平滑、重归一化或减少网格点");
    await firstRadial.locator("input[data-radial-n='1']").uncheck();
    check(await firstRadial.locator("path[data-channel='1']").count() === 0 && await firstRadial.locator("path[data-channel]").count() === 2, "Al l=0：关闭 N=1 只隐藏指定原函数");
    check(await otherRadial.locator("svg").evaluate(svg => svg.outerHTML) === otherSvg, "Al：N 开关不改变其他 l 图");
    await firstRadial.locator("input[data-radial-n='1']").check();
    check(JSON.stringify(await firstRadial.locator("path[data-channel]").evaluateAll(paths => paths.map(path => path.getAttribute("d")))) === JSON.stringify(originalPaths), "Al l=0：重新开启 N 恢复完全相同原样本路径");
    await firstRadial.getByRole("combobox", { name: "Plot mode for l=0", exact: true }).selectOption("derivative");
    check((await firstRadial.locator("svg").getAttribute("aria-label")).includes("finite difference"), "Al l=0：导数标明有限差分而非 producer 原存导数");
    await firstRadial.locator("input[data-radial-tail]").check();
    const derivativeTail = await firstRadial.locator("path[data-channel]").evaluateAll(paths => paths.map(path => path.getAttribute("d")));
    check(JSON.stringify(derivativeTail) === JSON.stringify(expectedPaths(radialSvg(physical.radial, 0, { mode: "derivative", tail: true }))), "Al l=0：导数尾部严格来自原网格的有限差分和最后 20% 范围");
    check((await firstRadial.locator("svg").textContent()).includes("last 20% of original grid"), "Al l=0：尾部缩放范围明确披露");
    check(await otherRadial.locator("svg").evaluate(svg => svg.outerHTML) === otherSvg, "Al：导数及尾部模式不改变其他 l 图");
    const radialSvgMarkup = await firstRadial.locator("svg").evaluate(svg => svg.outerHTML);
    const radialDownloadPromise = page.waitForEvent("download");
    await firstRadial.getByRole("button", { name: "Download this SVG", exact: true }).click();
    const radialDownload = await radialDownloadPromise;
    check(radialDownload.suggestedFilename() === `radial-${physical.file.sha256.slice(0, 12)}-l0.svg`, "Al：SVG 原生下载名含原 SHA 和独立 l");
    const radialDownloadPath = await radialDownload.path();
    check(radialDownloadPath && fs.readFileSync(radialDownloadPath, "utf8") === radialSvgMarkup, "Al：原生 SVG 下载与当前选择、导数及尾部图完全一致");
    await firstRadial.getByRole("combobox", { name: "Plot mode for l=0", exact: true }).selectOption("raw");
    await firstRadial.locator("input[data-radial-tail]").uncheck();
    await screenshot("radial-al-desktop.png");
    for (const [element, headerElement] of [["F", "O"], ["Li", "Ne"]]) {
      const set = data.basis_sets.find(item => item.element === element && item.files.some(file => file.role === "abf"));
      check(Boolean(set), `${element}：真实异常 ABF 样例存在`);
      await go(`#/basis/${encodeURIComponent(set.id)}`);
      await verifyRadialFile(set, "nao", true);
      const auxiliary = await verifyRadialFile(set, "abf");
      check(auxiliary.radial.element === headerElement && auxiliary.radial.header_mismatch && auxiliary.radial.channels.length === 800, `${element} ABF：原头 ${headerElement} 和 800 通道异常原样保留`);
      const warning = auxiliary.filePanel.locator(".radial-status");
      const warningText = await warning.innerText();
      check(await warning.evaluate(status => status.classList.contains("name-warning")) && warningText.includes("Header metadata note: the source element differs from the catalog element") && warningText.includes("Header metadata note: declared angular counts"), `${element} ABF：元素及通道数差异以正式元数据说明呈现`);
      check(warningText.includes(JSON.stringify(auxiliary.radial.counts)) && warningText.includes(JSON.stringify(auxiliary.radial.actual_counts)) && warningText.includes("Plots include every source block and retain the recorded header"), `${element} ABF：声明和实际 counts 分别披露并保留全部源数据`);
      check(await auxiliary.filePanel.locator("path[data-channel='99']").count() === 8, `${element} ABF：每个 l 的原 N=99 均保留，不按错误原头截断`);
      check(await auxiliary.filePanel.locator("svg").evaluateAll((svgs, originalElement) => svgs.every(svg => svg.getAttribute("aria-label").startsWith(`${originalElement} l=`)), auxiliary.radial.element), `${element} ABF：图像标签沿用原头元素，不冒充 catalog 元素`);
      await screenshot(`radial-${element.toLowerCase()}-abf-diagnostic.png`);
    }
    const shaFailure = await context.newPage();
    shaFailure.on("pageerror", error => errors.push(error.message));
    const invalidCatalog = structuredClone(data);
    invalidCatalog.basis_sets.find(set => set.id === radialSet.id).files.find(file => file.path === physical.file.path).sha256 = "0".repeat(64);
    await shaFailure.route("**/data.json", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(invalidCatalog) }));
    await shaFailure.goto(base.href + `#/basis/${encodeURIComponent(radialSet.id)}`, { waitUntil: "domcontentloaded" });
    const rejectedRadial = shaFailure.locator(".radial-file[open]").filter({ has: shaFailure.locator("[data-radial-load]") });
    await rejectedRadial.locator(".radial-status").filter({ hasText: "Radial plots unavailable" }).waitFor();
    check((await rejectedRadial.locator(".radial-status").innerText()).includes("Plots are displayed only after source integrity is confirmed"), "错误 SHA：仅在源完整性确认后绘图");
    check(await rejectedRadial.locator(".radial-card, svg, [data-radial-download]").count() === 0, "错误 SHA：没有任何可下载或可误读的曲线");
    check(await rejectedRadial.locator("[data-radial-load]").isEnabled(), "错误 SHA：失败后按钮恢复可重试");
    await shaFailure.close();
    for (const file of inputs) {
      const fetched = await context.request.get(new URL(file.path, archive).href);
      check(fetched.ok(), `input is downloadable: ${file.path}`);
      check(createHash("sha256").update(await fetched.body()).digest("hex") === file.sha256, `input content hash: ${file.path}`);
    }
    const frontierRecords = calculations.filter(record => record.files.figures.some(file => /\/band_frontier_metadata\.json$/.test(file.path)));
    check(frontierRecords.length > 0, "真实frontier方法sidecar存在");
    let primaryMethodsVerified = 0;
    for (const record of frontierRecords) {
      const metadataFile = record.files.figures.find(file => /\/band_frontier_metadata\.json$/.test(file.path));
      const metadataUrl = new URL(metadataFile.path, archive);
      const fetched = await context.request.get(metadataUrl.href);
      check(fetched.ok(), `${record.id}：frontier sidecar可读取`);
      const metadataBytes = await fetched.body();
      check(createHash("sha256").update(metadataBytes).digest("hex") === metadataFile.sha256, `${record.id}：sidecar哈希一致`);
      const metadata = JSON.parse(metadataBytes.toString("utf8"));
      check(metadata.calculation_id === record.id, `${record.id}：sidecar属于同一计算`);
      check(metadata.comparison_mode === "single method, own occupied sampled-path VBM reference", `${record.id}：各方法使用自己的VBM reference`);
      const figureUrls = record.files.figures.map(file => new URL(file.path, archive).href);
      for (const [method, analysis] of Object.entries(metadata.methods)) {
        check(analysis.raw_selected_occupied_bands.length === 3 && analysis.raw_selected_empty_bands.length === 4, `${record.id} / ${method}：固定三占据四空带窗口`);
        check(analysis.mapping_one_based.length > 0, `${record.id} / ${method}：raw-band映射保留`);
        const svgUrl = new URL(`${method.toLowerCase()}_frontier.svg`, metadataUrl).href;
        check(analysis.figure_status === "renderable", `${record.id} / ${method}：完成的分析一律可展示`);
        check(figureUrls.includes(svgUrl), `${record.id} / ${method}：方法frontier图均被记录引用`);
        primaryMethodsVerified += 1;
        const primary = record.files.figures.find(file => new URL(file.path, archive).href === svgUrl);
        check(primary?.display_priority === "primary", `${record.id} / ${method}：有效新图有primary引用`);
        const figureResponse = await context.request.get(svgUrl);
        check(figureResponse.ok(), `${record.id} / ${method}：重新绘制的单方法图HTTP可访问`);
        const figureBytes = await figureResponse.body();
        check(createHash("sha256").update(figureBytes).digest("hex") === primary.sha256, `${record.id} / ${method}：网页图字节匹配脚本生成图SHA`);
        const figureText = figureBytes.toString("utf8");
        check(figureText.includes('fill="white"') && figureText.includes('font-family="Times New Roman, DejaVu Serif, serif"') && figureText.includes('E − E'), `${record.id} / ${method}：白底衬线与独立VBM统一风格`);
        check(figureText.includes(`${method}-rank-`) && figureText.includes(`${method}-VBM-`) && figureText.includes(`${method}-CBM-`), `${record.id} / ${method}：原窗口绘图和空心边缘标记`);
        const gap = analysis.selected_window_path_gap_ev;
        check(Number.isFinite(gap) && gap > 0, `${record.id} / ${method}：near-gap窗口有正的selected gap`);
        const selectedValues = analysis.display_energies_ev.flat();
        const minimum = Math.min(...selectedValues), maximum = Math.max(...selectedValues);
        const padding = Math.max(0.5, 0.05 * (maximum - minimum));
        const expectedLimits = [Math.min(-Math.max(2.5, 0.5 * gap), minimum - padding), Math.max(gap + Math.max(3, 0.5 * gap), maximum + padding)];
        check(Array.isArray(analysis.y_limits_ev) && analysis.y_limits_ev.length === 2 && expectedLimits.every((value, index) => Math.abs(analysis.y_limits_ev[index] - value) < 1e-8), `${record.id} / ${method}：现有已选能带全貌的独立y范围`);
        check(analysis.viewport.cut_states.length === 0 && analysis.y_limits_ev[0] < minimum && analysis.y_limits_ev[1] > maximum, `${record.id} / ${method}：占据和非占据已选态完整展示，没有额外能带`);
        check(analysis.viewport.selected_raw_window_frozen_before_sorting === true, `${record.id} / ${method}：展示窗口在排序前冻结`);
        if (record.id === "alp-paper-k8_shrink_wing" && method === "EXX") {
          check(analysis.y_limits_ev[0] <= -3.697255 && analysis.y_limits_ev[1] >= 11.091765, "AlP EXX保留旧近隙范围且完整显示原已选曲线");
          check(metadata.methods.KS.y_limits_ev[1] !== analysis.y_limits_ev[1], "AlP EXX不复用PBE y范围");
        }
      }
    }
    check(primaryMethodsVerified === 194, "194个有效新图的方法viewport已逐项验证");
    const alas = calculations.find(record => record.id === "alas-paper-paper");
    await go("#/material/alas-paper-paper");
    check(!/[\u3400-\u9fff]/.test(await page.locator("#detail-view").innerText()), "AlAs详情全部英文");
    const alasImage = page.locator("#record-bands > .section-body > .figure-grid img[src$='/ks_frontier.svg']");
    await alasImage.scrollIntoViewIfNeeded();
    await alasImage.evaluate(image => image.decode());
    await screenshot("alas-full-selected-bands.png");
    const cao = calculations.find(record => record.material === "CaO" && record.dimension === "3d");
    check(Boolean(cao), "CaO真实样例存在");
    const caoGwFigure = cao.files.figures.find(file => file.display_priority === "primary" && /\/gw_frontier\.svg$/.test(file.path));
    check(Boolean(caoGwFigure), "CaO GW固定低空带窗口新图保留");
    await go(`#/material/${encodeURIComponent(cao.id)}`);
    const caoImage = page.locator("#record-bands > .section-body > .figure-grid img[src$='/gw_frontier.svg']");
    await caoImage.scrollIntoViewIfNeeded();
    await caoImage.evaluate(img => img.decode());
    check(await caoImage.evaluate(img => img.naturalWidth > 0), "CaO GW真实新图加载");
    await screenshot("cao-gw-bands.png");
    await page.setViewportSize({ width: 320, height: 844 });
    await go("");
    await page.waitForSelector("#landing-stats strong");
    check(await page.locator("#landing-view").isVisible(), "320px 根路由仍是封面页");
    check(await page.evaluate(() => document.body.classList.contains("cover-mode")), "移动端同样进入封面聚焦模式");
    const mobileEmblem = page.locator(".landing-emblem");
    await mobileEmblem.evaluate(img => img.decode());
    check(await mobileEmblem.evaluate(img => img.complete && img.naturalWidth === 540), "移动端封面徽章加载");
    check(await mobileEmblem.evaluate(img => img.getBoundingClientRect().width <= 200), "移动端徽章缩进封面尺寸");
    check(await mobileEmblem.evaluate(img => Math.abs((img.getBoundingClientRect().x + img.getBoundingClientRect().width / 2) - innerWidth / 2) < 40), "移动端徽章水平居中");
    check(await page.locator(".cover-actions .primary-button").evaluate(button => button.getBoundingClientRect().top < 900), "移动端封面主按钮一屏内可达");
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "320px 封面无横向溢出");
    await screenshot("landing-mobile.png");
    await go("#/materials");
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "320px mobile document has no horizontal overflow");
    check(await page.locator(".material-row").first().evaluate(row => getComputedStyle(row).display === "grid"), "320px material catalog uses semantic cards");
    check(await page.locator("#search").evaluate(input => input.getBoundingClientRect().bottom <= 900), "移动搜索保持一屏内可达（v2 主题首屏 860px）");
    check(await page.evaluate(() => getComputedStyle(document.body).fontSize === "16px"), "移动正文保持16px");
    check(await page.locator(".material-row .primary-result strong").first().evaluate(cell => Number.parseFloat(getComputedStyle(cell).fontSize) >= 15), "320px卡片主结果保持可读字号");
    check(await page.locator(".brand-mark").evaluate(img => img.getBoundingClientRect().height === 36 && img.complete && img.naturalWidth === 320), "移动36px logo正确加载");
    const filterToggle = page.locator("#filter-toggle");
    check(await filterToggle.isVisible() && await filterToggle.getAttribute("aria-expanded") === "false", "移动filter-toggle默认折叠");
    check(await page.locator("#element-filter").isHidden(), "折叠筛选不占首屏");
    await filterToggle.click();
    check(await filterToggle.getAttribute("aria-expanded") === "true" && await page.locator("#element-filter").isVisible(), "移动筛选可展开且aria同步");
    check(await filterToggle.evaluate(button => button.getBoundingClientRect().height >= 44), "移动筛选触控目标至少44px");
    await page.locator("input[name='dimension'][value='2d']").check();
    check(await page.locator(".material-row .dimension-tag").allTextContents().then(values => values.length > 0 && values.every(value => value === "2D")), "移动展开筛选实际过滤二维数据");
    await page.locator("#reset-filters").click();
    await filterToggle.click();
    check(await filterToggle.getAttribute("aria-expanded") === "false" && await page.locator("#element-filter").isHidden(), "移动筛选可再次折叠");
    await screenshot("materials-mobile.png");
    await go("#/basis");
    check(await filterToggle.getAttribute("aria-expanded") === "false", "移动basis筛选初始折叠");
    await filterToggle.click();
    check(await page.locator("#status-filter-control").count() === 0 && await page.locator(".dimension-filter").isHidden(), "移动basis展开不再有publication筛选且不显示dimension");
    await filterToggle.click();
    await go(`#/basis/${encodeURIComponent(radialSet.id)}`);
    const mobilePhysical = await verifyRadialFile(radialSet, "nao", true);
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "移动 NAO：多 l 径向详情没有页面横向溢出");
    check(await mobilePhysical.filePanel.locator(".radial-chart").evaluateAll(charts => charts.every(chart => chart.getBoundingClientRect().right <= innerWidth && chart.scrollWidth >= chart.clientWidth)), "移动 NAO：每个 l 图的滚动容器在视口内，保留可独立横向查看的原图");
    const mobileRadial = mobilePhysical.filePanel.locator(".radial-card[data-radial-l='0']");
    await mobileRadial.getByRole("combobox", { name: "Plot mode for l=0", exact: true }).selectOption("derivative");
    await mobileRadial.locator("input[data-radial-tail]").check();
    await mobileRadial.locator(".radial-metrics summary").click();
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "移动 NAO：导数、尾部与端点表展开后仍无页面横向溢出");
    await mobileRadial.scrollIntoViewIfNeeded();
    await screenshot("radial-al-mobile.png");
    for (const element of ["F", "Li"]) {
      const set = data.basis_sets.find(item => item.element === element && item.files.some(file => file.role === "abf"));
      await go(`#/basis/${encodeURIComponent(set.id)}`);
      const auxiliary = await verifyRadialFile(set, "abf");
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `移动 ${element} ABF：800 原通道及完整 SHA 没有页面横向溢出`);
      const first = auxiliary.filePanel.locator(".radial-card").first();
      await first.locator(".radial-metrics summary").click();
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `移动 ${element} ABF：原 N 诊断表展开后无页面横向溢出`);
      check((await auxiliary.filePanel.locator(".radial-status").innerText()).includes("Plots include every source block and retain the recorded header"), `移动 ${element} ABF：元数据差异说明仍明确显示`);
    }
    await go("#/material/si-paper-all_kpath");
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "mobile detail has no horizontal overflow");
    await screenshot("silicon-mobile.png");
    await go("#/material/mos2_ws2-table-gw");
    await page.locator(".section-nav [data-section='record-inputs']").click();
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "mobile partial input detail has no horizontal overflow");
    check((await page.locator("#record-inputs").innerText()).includes("Stage-resolved calculation inputs"), "mobile stage-resolved input description visible");
    await screenshot("partial-inputs-mobile.png");
    await go("#/material/not-a-record");
    check((await page.locator("#detail-view").innerText()).includes("Record not found"), "unknown ID handled");
    await go("#/material/%E0%A4%A");
    check((await page.locator("#detail-view").innerText()).includes("Record not found"), "malformed URL handled");
    const failure = await context.newPage();
    failure.on("pageerror", error => errors.push(error.message));
    await failure.route("**/data.json", route => route.fulfill({ status: 503, body: "Unavailable" }));
    await failure.goto(base.href, { waitUntil: "domcontentloaded" });
    await failure.waitForSelector("#load-error:not([hidden])");
    check((await failure.locator("#load-error").innerText()).includes("503"), "catalog network errors shown honestly");
    check(errors.length === 0, `browser errors: ${errors.join("; ")}`);
    console.log(JSON.stringify({ passed: true, checks, calculations: calculations.length, basis_sets: data.basis_sets.length, input_files_verified: inputs.length, radial_files_verified: radialFilesVerified, radial_channels_verified: radialChannelsVerified, browser_errors: errors }, null, 2));
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error.stack); process.exitCode = 1; });
