import test from "node:test";
import assert from "node:assert/strict";
import { bandGap, archivedBandGap, paperGap, boundFiles, publicPath, fileName, downloadName, setRelation, methodNames, methodTag, socTag, spinPolTag, inputStage, recordType, atomCount, primaryResult, performanceSummary, workflowFrontend, frontendLabel, structureFingerprint, sameStructureRecords, crossFrontendRecords } from "../database/records.mjs";
import { renderFiles } from "../database/files.mjs";
import { renderMaterial } from "../database/details.mjs";
import { gapOverview, renderGapOverview } from "../database/gaps.mjs";
import { readFileSync } from "node:fs";

test("stage-resolved controls retain redaction provenance without exposing internal QA status", () => {
  const path = "data/calculations/2d/MoTe2/mote2-table-gw/results/stage_input_receipt.json";
  const record = { id: "mote2-table-gw", material: "MoTe2", dimension: "2d", summary: {}, source: { stage_input_receipt: path }, files: { inputs: [{ path: "data/calculations/2d/MoTe2/mote2-table-gw/inputs/recovered/stage/librpa.in", sha256: "a".repeat(64), original_sha256: "b".repeat(64), transformation: "private server path redacted; not a rerun bundle" }] }, archive_completeness: { status: "incomplete", issues: ["software missing"] } };
  const html = renderMaterial(record, []);
  assert.match(html, /Stage-resolved calculation inputs/);
  assert.match(html, /View stage-input receipt/);
  assert.match(html, /File transformations are recorded/);
  assert.doesNotMatch(html, /Original SHA-256/);
  assert.doesNotMatch(html, new RegExp("b".repeat(64)));
  assert.doesNotMatch(html, /Upload incomplete|CI blocked|software missing|Archive completeness/);
});

test("all real material and basis pages render English without rewriting archived paper evidence", () => {
  const catalog = JSON.parse(readFileSync(new URL("../database/data.json", import.meta.url), "utf8"));
  const before = JSON.stringify(catalog);
  for (const record of catalog.calculations) {
    assert.doesNotMatch(renderMaterial(record, catalog.basis_sets), /[\u3400-\u9fff]/, record.id);
  }
  assert.equal(JSON.stringify(catalog), before);
});

test("all database headlines retain their values while references omit repeated numeric tables", () => {
  const catalog = JSON.parse(readFileSync(new URL("../database/data.json", import.meta.url), "utf8"));
  const before = JSON.stringify(catalog);
  for (const record of catalog.calculations) {
    const html = renderMaterial(record, catalog.basis_sets);
    const headline = html.slice(html.indexOf('class="result-strip"'), html.indexOf('class="detail-layout"'));
    assert.doesNotMatch(headline, /paper-reported/, record.id);
    if (recordType(record) === "large_system_gw") {
      const result = primaryResult(record);
      assert.ok(result && headline.includes(result.value.toFixed(5)), `${record.id} primary result`);
    } else {
      for (const method of ["DFT", "EXX", "GW"]) {
        const value = bandGap(record, method);
        if (value !== null) assert.ok(headline.includes(value.toFixed(paperGap(record, method)?.precision ?? 3)), `${record.id} ${method}`);
      }
    }
    if (paperGap(record, "DFT") || paperGap(record, "GW")) {
      const reference = html.slice(html.indexOf('<details class="reference-source">'), html.indexOf('</details>', html.indexOf('<details class="reference-source">')));
      assert.match(reference, /^<details class="reference-source"><summary>/, record.id);
      assert.doesNotMatch(reference, /<table|Archived \/ path value|Paper-reported values/, record.id);
      assert.match(reference, /Download source extract/, record.id);
    }
  }
  assert.equal(JSON.stringify(catalog), before);
});

test("properties drive gaps; arbitrary summary values never become GW gaps", () => {
  assert.equal(bandGap({ summary: { value: -4, unit: "Ha", observable: "RPA energy" } }), null);
  assert.equal(bandGap({ summary: { value: 1.3, unit: "eV", observable: "G0W0 gap" } }), 1.3);
  const record = { summary: { gw_gap_ev: 2 }, properties: [{ category: "electronic", key: "band_gap", method: "G0W0", value: 1.1, unit: "eV", status: "reported" }] };
  assert.equal(bandGap(record), 1.1);
  record.properties[0].status = "failed";
  assert.equal(bandGap(record), null);
  record.properties[0].status = "reported";
  record.properties.push({ ...record.properties[0], method: "GW" });
  assert.equal(bandGap(record), null);
});

test("evidence-backed sampled path properties populate gaps without hiding failures or ambiguity", () => {
  const property = { category: "electronic", key: "sampled_path_gap_ev", method: "PBE", value: 1.8, unit: "eV", status: "reported" };
  assert.equal(bandGap({ properties: [property] }, "DFT"), 1.8);
  assert.equal(bandGap({ properties: [{ ...property, method: "EXX", value: 7.1 }] }, "EXX"), 7.1);
  assert.equal(bandGap({ properties: [{ ...property, status: "failed" }] }, "DFT"), null);
  assert.equal(bandGap({ properties: [property, { ...property, key: "band_gap" }] }, "DFT"), null);
  assert.equal(bandGap({ properties: [{ ...property, key: "unrelated_value" }] }, "DFT"), null);
});

test("paper-reported values take priority without rewriting archived gaps or diagnostic scope", () => {
  const evidence = "data/calculations/2d/WS2/ws2/results/paper_reported_values.json";
  const record = { id: "ws2", material: "WS2", dimension: "2d", summary: {},
    files: { results: [{ path: evidence, sha256: "b".repeat(64) }] },
    properties: [{ category: "electronic", key: "sampled_path_gap_ev", method: "PBE", value: 0.60168, unit: "eV", status: "reported" }],
    paper_values: { schema_version: 1, evidence, source: { title: "Paper <test>", document_sha256: "a".repeat(64), pdf_page: 12, table: "I" },
      values: { DFT: { value: 1.80171, unit: "eV", precision: 5, column: "Eg(PBE)", scope: "Restricted <scope>; not a certification" }, GW: { value: 2.674, unit: "eV", precision: 3, column: "Eg(G0W0)" } }, notes: "EXX is archive-derived." },
  };
  assert.equal(bandGap(record, "DFT"), 1.80171);
  assert.equal(archivedBandGap(record, "DFT"), 0.60168);
  assert.equal(bandGap(record, "EXX"), null);
  const html = renderMaterial(record, []);
  assert.match(html, /Reference &amp; source evidence/);
  assert.match(html, /1\.80171/);
  const overview = html.slice(html.indexOf('id="record-overview"'), html.indexOf('id="record-structure"'));
  assert.doesNotMatch(overview, /0\.60168|Paper-reported values|Archived \/ path value|<table/);
  assert.doesNotMatch(html, /· paper-reported/);
  assert.equal((html.match(/1\.80171/g) || []).length, 1);
  assert.match(html, /<details class="reference-source"><summary>/);
  assert.match(html, /Paper &lt;test&gt;/);
  assert.match(html, /PDF p\. 12 · Table I/);
  assert.match(html, /Download source extract/);
  assert.match(html, /Source scope/);
  assert.match(html, /Restricted &lt;scope&gt;; not a certification/);
  assert.doesNotMatch(html, /Restricted <scope>/);
  record.summary.observable = "GW raw-band frontier path gap";
  assert.equal(bandGap(record), 2.674);
  assert.equal(archivedBandGap(record), null);
  assert.equal(paperGap(record).value, 2.674);
  assert.match(renderMaterial(record, []), /Path-resolved value/);
  record.paper_values.values.DFT.value = Infinity;
  assert.equal(bandGap(record, "DFT"), 0.60168);
  record.paper_values.values.DFT.value = 1.80171;
  record.files.results = [];
  assert.equal(paperGap(record, "DFT"), null);
  assert.equal(bandGap(record, "DFT"), 0.60168);
});

test("new hBN shows the cited 6.94183 path-resolved headline", () => {
  const record = JSON.parse(readFileSync(new URL("../data/calculations/2d/hBN/hbn-tzdp10-fgext-20261008/record.json", import.meta.url)));
  assert.equal(record.status, undefined);
  assert.match(record.summary?.observable || "", /raw-band/i);
  assert.equal(bandGap(record), 6.94183);
  assert.equal(bandGap(record, "DFT"), 4.68813);
  assert.equal(archivedBandGap(record), null);
  const html = renderMaterial(record, []);
  const headline = html.slice(html.indexOf('class="result-strip"'), html.indexOf('class="detail-layout"'));
  assert.match(headline, /GW band gap/);
  assert.doesNotMatch(headline, /paper-reported/);
  assert.match(headline, /6\.94183/);
  assert.match(headline, /Path-resolved value/);
  assert.doesNotMatch(headline, /Restricted result|not an accepted|6\.68084/);
  assert.match(html, /raw-band-5 frontier path observable/);
  assert.doesNotMatch(html, /FAILED|validation incomplete|CI blocked|evidence issues/);
  delete record.paper_values;
  assert.equal(bandGap(record), null);
  assert.match(renderMaterial(record, []), /Path-resolved/);
});

test("all figure metadata attachments remain available", () => {
  const record = JSON.parse(readFileSync(new URL("../data/calculations/3d/Si/si-paper-all_kpath/record.json", import.meta.url)));
  const html = renderMaterial(record, []);
  assert.match(html, /Figure source &amp; metadata/);
  assert.match(html, /band_comparison\.json/);
});

test("formal record pages keep software provenance while internal QA fields stay private", () => {
  const record = {
    id: "ui-check", material: "Si", dimension: "3d", summary: { gates: ["SCF evidence pending"] },
    missing: ["Original input unavailable"],
    archive_completeness: { status: "incomplete", issues: ["Missing <INPUT>"] },
    method_diagnostics: [{ method: "EXX", message: "Pathology <raw spectrum>", full_raw_path_gap_ev: -1002817.14856 }],
    software: { abacus: { commit: "a".repeat(40), source_url: "https://github.com/example/abacus" }, librpa: { commit: "b".repeat(40), source_url: "https://github.com/example/librpa" } },
  };
  const html = renderMaterial(record, []);
  const software = html.slice(html.indexOf('id="record-evidence"'));
  assert.match(software, /<h2>Software &amp; logs<\/h2>/);
  assert.match(software, /Source code ↗/);
  assert.doesNotMatch(software, /Executable SHA-256/);
  assert.doesNotMatch(html, /Archive completeness|Upload incomplete|CI blocked|Missing &lt;INPUT&gt;|Original input unavailable|SCF evidence pending|Pathology|evidence issues/);
});

test("archive completeness metadata does not alter the public record page", () => {
  const record = { id: "unknown", material: "Si", dimension: "3d" };
  const base = renderMaterial(record, []);
  record.archive_completeness = { status: "incomplete", issues: ["internal issue"] };
  const withAudit = renderMaterial(record, []);
  assert.doesNotMatch(base + withAudit, /Upload completeness|archive checks|internal issue/);
});

test("primary figures occupy the main grid while original figures and metadata remain downloadable", () => {
  const record = {
    id: "figures", material: "Si", dimension: "3d", files: {
      figures: [
        { path: "data/case/primary.svg", display_priority: "primary" },
        { path: "data/case/original.png", display_priority: "secondary" },
        { path: "data/case/figure.json" },
      ],
    },
  };
  const html = renderMaterial(record, []);
  const mainGrid = html.slice(html.indexOf('<div class="figure-grid">'), html.indexOf('<details class="original-figures">'));
  assert.match(mainGrid, /primary\.svg/);
  assert.doesNotMatch(mainGrid, /original\.png/);
  assert.match(html, /Additional source figures · 1/);
  assert.match(html, /download="original\.png"/);
  assert.match(html, /figure\.json/);
  assert.match(html, /href="\.\.\/references\/plotting\.md"/);
  assert.match(html, /reusable band-figure script/);
  assert.match(html, /Each method uses its own occupied path VBM/);
  assert.match(html, /full extent of the selected curves without adding bands/);
  record.files.figures[0].display_priority = "secondary";
  const fallback = renderMaterial(record, []);
  assert.match(fallback, /primary\.svg/);
  assert.match(fallback, /original\.png/);
  assert.doesNotMatch(fallback, /class="original-figures"/);
});

test("figures render without advisory markers", () => {
  const record = { id: "diagnostic-figure", material: "GeTe", dimension: "2d", files: { figures: [
    { path: "data/case/exx.png", scientific_status: "archived_diagnostic" },
  ] } };
  const html = renderMaterial(record, []);
  assert.doesNotMatch(html, /Diagnostic figure/);
  assert.match(html, /download="exx\.png"/);
  assert.doesNotMatch(html, /not an accepted|Upload complete|CI blocked/);
});

test("home typography and controls stay readable at mobile breakpoints", () => {
  const css = readFileSync(new URL("../database/style.css", import.meta.url), "utf8");
  const index = readFileSync(new URL("../database/index.html", import.meta.url), "utf8");
  const app = readFileSync(new URL("../database/app.js", import.meta.url), "utf8");
  assert.match(css, /body \{[^}]*font-size: 16px/);
  assert.match(css, /\.catalog-table tbody td \{[^}]*font-size: 14px/);
  assert.match(css, /\.software-entry code \{[^}]*font-size: 13px/);
  assert.doesNotMatch(css, /font(?:-size)?:\s*(?:[6-9]|10|11)px/);
  assert.match(css, /\.pagination button \{[^}]*height: 44px/);
  assert.match(css, /\.dialog-close \{[^}]*width: 44px; height: 44px/);
  assert.match(index, /class="intro-lattice"[^>]*aria-hidden="true"/);
  assert.match(index, /id="filter-toggle"[^>]*aria-expanded="false"/);
  assert.match(app, /Materials, with evidence\./);
  assert.match(app, /path-resolved and sampled-grid observables are not presented as global fundamental gaps/i);
  assert.match(app, /Primary results retain their recorded unit and scope/);
  assert.doesNotMatch(app, /Paper-reported · Table|Original path values and differences are retained/);
});

test("software filter narrows the calculation catalog by workflow frontend", () => {
  const index = readFileSync(new URL("../database/index.html", import.meta.url), "utf8");
  const app = readFileSync(new URL("../database/app.js", import.meta.url), "utf8");
  assert.match(index, /fieldset class="software-filter"/);
  assert.match(index, /name="software" value="all" checked/);
  assert.match(index, /name="software" value="abacus"/);
  assert.match(index, /name="software" value="fhi_aims"/);
  assert.match(app, /state\.software === "all" \|\| workflowFrontend\(record\) === state\.software/);
  assert.match(app, /\[\"sw\", state\.software, \"all\"\]/);
  assert.match(app, /\[\"all\", \"abacus\", \"fhi_aims\"\]\.includes\(params\.get\(\"sw\"\)\)/);
  assert.match(app, /\$\(\"\.software-filter\"\)\.hidden = basis/);
  assert.match(index, /Download catalog \(JSON\)/);
});

test("basis library catalogues ABACUS assets only, without publication labels", () => {
  const catalog = JSON.parse(readFileSync(new URL("../database/data.json", import.meta.url), "utf8"));
  const index = readFileSync(new URL("../database/index.html", import.meta.url), "utf8");
  const app = readFileSync(new URL("../database/app.js", import.meta.url), "utf8");
  const details = readFileSync(new URL("../database/details.mjs", import.meta.url), "utf8");
  assert.ok(catalog.basis_sets.length > 0);
  for (const set of catalog.basis_sets) {
    assert.ok(set.files.some(file => ["pp", "nao", "for_aux", "abf"].includes(file.role)), `${set.id} payload`);
    assert.ok(!set.files.some(file => file.role === "species_defaults"), `${set.id} species defaults leaked`);
    assert.equal(set.publication, undefined, `${set.id} publication leaked`);
  }
  for (const record of catalog.calculations) assert.equal(record.publication, undefined, `${record.id} publication leaked`);
  assert.doesNotMatch(app, /publication-tag|statusNames|status-filter/);
  assert.doesNotMatch(details, /publication-tag|Published set|Published basis set/);
  assert.doesNotMatch(index, /status-filter|PUBLICATION/);
  assert.match(app, /\["Element \/ family", "Assets", "Recorded scope", "Linked", ""\]/);
});

test("aims records show species-default binding notes without basis-library links", () => {
  const details = readFileSync(new URL("../database/details.mjs", import.meta.url), "utf8");
  assert.match(details, /FHI-aims species defaults/);
  assert.match(details, /intermediate_gw/);
  assert.match(details, /own classification/);
  assert.match(details, /archived control\.in/);
});

test("gap overview route, navigation, and table are wired end to end", () => {
  const index = readFileSync(new URL("../database/index.html", import.meta.url), "utf8");
  const app = readFileSync(new URL("../database/app.js", import.meta.url), "utf8");
  const css = readFileSync(new URL("../database/style.css", import.meta.url), "utf8");
  assert.match(index, /href="#\/gaps" data-nav="gaps">Gap overview</);
  assert.match(app, /hash\.split\("\?"\)\[0\] === "#\/gaps" \? "gaps"/);
  assert.match(app, /state\.mode === "gaps" \? "#\/gaps" : "#\/"/);
  assert.match(app, /renderGapOverview\(state\.calculations, state\.sort\)/);
  assert.match(app, /records list a gap value/);
  assert.match(css, /\.browser-layout:has\(>\.filter-panel\[hidden\]\)\{grid-template-columns:minmax\(0,1fr\)\}/);
  assert.match(css, /\.gw-line\{display:flex/);
  const table = renderGapOverview([
    { id: "si-band", material: "Si", dimension: "3d", properties: [{ category: "electronic", key: "band_gap", method: "PBE", value: 0.6, unit: "eV", status: "reported" }, { category: "electronic", key: "band_gap", method: "GW", value: 1.1, unit: "eV", status: "reported" }] },
    { id: "c-rpa", material: "C", dimension: "3d", record_type: "rpa_energy", properties: [{ key: "rpa_correlation_energy", value: -1, unit: "Ha", status: "reported" }] },
  ]);
  assert.match(table, /PBE \/ KS<\/th>/);
  assert.match(table, /EXX<\/th>/);
  assert.match(table, /GW<\/th>/);
  assert.match(table, /Si/);
  assert.match(table, /gap-bar/);
  assert.doesNotMatch(table, /c-rpa/);
  assert.equal(gapOverview({ id: "x", dimension: "3d", record_type: "rpa_energy", properties: [] }), null);
  const restricted = { id: "r", material: "R", dimension: "2d", summary: { observable: "GW raw-band frontier path gap" }, properties: [{ category: "electronic", key: "sampled_path_gap_ev", method: "PBE", value: 1.2, unit: "eV", status: "reported" }, { category: "electronic", key: "sampled_path_gap_ev", method: "GW", value: 6.5, unit: "eV", status: "reported" }] };
  assert.equal(gapOverview(restricted).scope, "path");
  const sampled = { id: "s", material: "S", dimension: "3d", record_type: "large_system_gw", properties: [{ key: "sampled_grid_gap_ev", category: "electronic", method: "PBE", value: 4.2, unit: "eV", status: "validated", definition: "Γ regular grid" }] };
  assert.deepEqual(gapOverview(sampled), { ks: 4.2, exx: null, gw: null, scope: "sampled" });
});

test("dark mode toggle is wired with persisted preference and token overrides", () => {
  const index = readFileSync(new URL("../database/index.html", import.meta.url), "utf8");
  const app = readFileSync(new URL("../database/app.js", import.meta.url), "utf8");
  const css = readFileSync(new URL("../database/style.css", import.meta.url), "utf8");
  assert.match(index, /id="theme-toggle"/);
  assert.match(index, /localStorage\.getItem\("theme"\)/);
  assert.match(app, /localStorage\.setItem\("theme", next\)/);
  assert.match(app, /document\.documentElement\.dataset\.theme === "dark" \? "light" : "dark"/);
  assert.match(css, /html\[data-theme="dark"\]\{/);
  assert.match(css, /--bg:#0d181d/);
  assert.match(css, /\.search-box\[hidden\],\.search-examples\[hidden\],\.filter-panel\[hidden\]\{display:none\}/);
  assert.match(detailsModule(), /decoding="async"/);
  assert.match(index, /Data schema/);
  assert.match(index, /href="\.\.\/references\/database\.md"/);
});

function detailsModule() {
  return readFileSync(new URL("../database/details.mjs", import.meta.url), "utf8");
}

test("database branding is front-end neutral and supports ABACUS and FHI-aims workflows", () => {
  const index = readFileSync(new URL("../database/index.html", import.meta.url), "utf8");
  const app = readFileSync(new URL("../database/app.js", import.meta.url), "utf8");
  assert.match(index, /class="brand"[^>]*aria-label="LibRPA materials database home"/);
  assert.match(index, /ABACUS and FHI-aims workflows/);
  assert.doesNotMatch(index, /ABACUS <b>\+<\/b> LibRPA|Materials database · ABACUS/);
  assert.doesNotMatch(app, / · ABACUS \+ LibRPA/);
});

test("header uses the themed navbar logo pair and vector icon links", () => {
  const index = readFileSync(new URL("../database/index.html", import.meta.url), "utf8");
  const css = readFileSync(new URL("../database/style.css", import.meta.url), "utf8");
  const icon = readFileSync(new URL("../database/favicon.svg", import.meta.url), "utf8");
  const light = readFileSync(new URL("../database/logo-navbar-light.svg", import.meta.url), "utf8");
  const dark = readFileSync(new URL("../database/logo-navbar-dark.svg", import.meta.url), "utf8");
  assert.doesNotMatch(index, /data:image\/svg\+xml/);
  assert.doesNotMatch(index, /logo\.svg/);
  assert.match(index, /rel="icon"[^>]*type="image\/svg\+xml"[^>]*href="favicon\.svg(?:\?v=[a-z0-9-]+)?"/);
  assert.match(index, /rel="alternate icon"[^>]*href="favicon-32x32\.png(?:\?v=[a-z0-9-]+)?"/);
  assert.match(index, /rel="apple-touch-icon"[^>]*href="apple-touch-icon\.png(?:\?v=[a-z0-9-]+)?"/);
  assert.match(index, /class="brand-logo brand-logo-light"[^>]*src="logo-navbar-light\.svg(?:\?v=[a-z0-9-]+)?"/);
  assert.match(index, /class="brand-logo brand-logo-dark"[^>]*src="logo-navbar-dark\.svg(?:\?v=[a-z0-9-]+)?"/);
  assert.match(icon, /viewBox="0 0 64 64"/);
  for (const navbar of [light, dark]) {
    assert.match(navbar, /viewBox="0 0 280 56"/);
    assert.doesNotMatch(navbar, /<script\b|<image\b|data:image|href="https?:/);
  }
  assert.doesNotMatch(icon, /<text\b|<image\b|<script\b/);
  assert.throws(() => readFileSync(new URL("../database/logo.svg", import.meta.url)), "old single mark retired");
  assert.match(css, /\.brand-logo \{[^}]*height: 40px/);
  assert.match(css, /html\[data-theme="dark"\] \.brand-logo-dark \{ display: block; \}/);
});

test("recorded software identifiers are displayed without internal missing-version warnings", () => {
  const record = { id: "partial-commit", material: "Si", dimension: "3d", software: { abacus: { commit: "123abcd", source_url: "https://github.com/example/code" }, librpa: { commit: "unknown" } } };
  const html = renderMaterial(record, []);
  const software = html.slice(html.indexOf('id="record-evidence"'));
  assert.match(software, /Calculation software/);
  assert.doesNotMatch(software, /123abcd/);
  assert.doesNotMatch(software, /Full commit not recorded|full source commit|\/commit\/123abcd/);
});

test("figure downloads honor aliases and invalid figure paths never become links", () => {
  const record = { id: "figure-paths", material: "Si", dimension: "3d", files: { figures: [
    { path: "data/case/figure.svg", download_name: "Si_PBE_GW.svg" },
    { path: "../private.svg" },
  ] } };
  const html = renderMaterial(record, []);
  assert.match(html, /download="Si_PBE_GW\.svg"/);
  assert.match(html, /Figure link unavailable/);
  assert.doesNotMatch(html, /(?:href|src)="null"/);
  assert.doesNotMatch(html, /(?:href|src)="[^\"]*private\.svg"/);
});

test("zero gap is retained and invalid/non-eV values are not displayed as eV", () => {
  assert.equal(bandGap({ summary: { gw_gap_ev: 0 } }), 0);
  assert.equal(bandGap({ summary: { gw_gap_ev: "unknown" } }), null);
  assert.equal(bandGap({ properties: [{ category: "electronic", key: "band_gap", method: "GW", unit: "Ha", value: 2 }] }), null);
});

test("archive URLs escape reserved characters and reject traversal", () => {
  assert.equal(publicPath("data/a #b?.orb"), "../data/a%20%23b%3F.orb");
  for (const value of ["../private", "/absolute", "https://host/a", "data/../bad", "data/a\\b"]) assert.equal(publicPath(value), null);
});

test("calculation aliases apply only to unambiguous exact asset roles", () => {
  const set = { files: [{ path: "data/abc.upf", role: "pp", sha256: "abc", label: "payload" }] };
  const [file] = boundFiles(set, { asset_aliases: { pp: "Si.upf" } });
  assert.equal(fileName(file), "Si.upf");
  assert.equal(downloadName(file), "Si.upf");
  assert.equal(file.path, "data/abc.upf");
  assert.equal(set.files[0].display_name, undefined);
  assert.equal(boundFiles(set, { asset_aliases: { pp: "../bad.upf" } })[0].display_name, undefined);
  set.files.push({ ...set.files[0], path: "data/other.upf" });
  assert.equal(boundFiles(set, { asset_aliases: { pp: "Si.upf" } })[0].display_name, undefined);
});

test("candidate links are not labelled as exact production bindings", () => {
  assert.equal(setRelation({ basis_candidates: [{ set_id: "candidate" }] }, "candidate"), "Candidate only");
  assert.equal(setRelation({ species: [{ set_id: "exact" }] }, "exact"), "Exact binding");
});

test("file rows expose view/download and label unknown originals without internal hashes", () => {
  const html = renderFiles([{ path: "data/hash.orb", sha256: "abc123", display_name: "Si_NAO_abc.orb", download_name: "Si_NAO_abc.orb", name_source: "descriptive_alias", role: "nao", size_bytes: 100 }]);
  assert.match(html, /data-preview="data\/hash.orb"/);
  assert.match(html, /download="Si_NAO_abc.orb"/);
  assert.match(html, /Descriptive filename/);
  assert.doesNotMatch(html, /abc123/);
  assert.doesNotMatch(html, />payload</);
  assert.match(renderFiles([{ path: "data/<script>bad</script>.orb" }]), /&lt;script&gt;/);
});

test("nested input archive names retain stage labels", () => {
  assert.equal(inputStage({ path: "data/case/inputs/calculation__pbe_path__STRU" }), "calculation / pbe_path");
});

test("methods can come from contributed properties without inventing a figure", () => {
  assert.deepEqual(methodNames({ properties: [{ category: "electronic", method: "G0W0", status: "reported" }] }), ["GW"]);
});

test("method chips show the recorded mean-field functional instead of generic DFT", () => {
  const pbe = { category: "electronic", method: "PBE", status: "reported" };
  assert.deepEqual(methodNames({ properties: [pbe, { category: "electronic", method: "G0W0", status: "reported" }] }), ["PBE", "GW"]);
  assert.deepEqual(methodNames({ properties: [{ ...pbe, status: "failed" }, { category: "electronic", method: "G0W0", status: "reported" }] }), ["GW"]);
  const lda = { category: "electronic", method: "LDA", status: "reported" };
  assert.deepEqual(methodNames({ properties: [lda, { category: "electronic", method: "G0W0", status: "reported" }] }), ["LDA", "GW"]);
  assert.deepEqual(methodNames({ properties: [pbe, lda, { category: "electronic", method: "G0W0", status: "reported" }] }), ["DFT", "GW"], "two functionals keep the generic label");
  assert.deepEqual(methodNames({ functional: "PBE", properties: [] }), ["PBE"], "a declared functional lights the chip without any property");
  assert.deepEqual(methodNames({ functional: "HSE", properties: [{ category: "electronic", method: "G0W0", status: "reported" }] }), ["HSE", "GW"]);
  assert.deepEqual(methodNames({ functional: "PBE", properties: [{ category: "electronic", method: "LDA", status: "reported" }] }), ["PBE"], "the archived declaration wins over a disagreeing property label");
  assert.deepEqual(methodNames({ functional: "PW91", properties: [{ category: "electronic", method: "G0W0", status: "reported" }] }), ["GW"], "unknown declared tokens are ignored");
  assert.deepEqual(methodNames({ properties: [{ category: "electronic", method: "EXX", status: "reported" }] }), ["EXX"], "the EXX branch must match the EXX pattern, not a literal");
  assert.equal(methodTag("PBE"), '<span class="method-tag method-dft">PBE</span>');
  assert.equal(methodTag("LDA"), '<span class="method-tag method-dft">LDA</span>');
  assert.equal(methodTag("EXX"), '<span class="method-tag method-exx">EXX</span>');
  assert.equal(methodTag("GW"), '<span class="method-tag method-gw">GW</span>');
});

test("large-system GW renders sampled-grid results and performance without inventing bands", () => {
  const result = "data/calculations/3d/C/c512/results/LibRPA.out";
  const log = "data/calculations/3d/C/c512/logs/slurm.out";
  const record = {
    id: "c512", material: "C", formula: "C512", dimension: "3d", record_type: "large_system_gw",
    workflow: { task: "g0w0_band", sampling: "regular_grid", sampling_label: "Γ point on the regular grid", band_path_available: false, k_point_count: 1 },
    computational_scale: { atom_count: 512, ao_count: 6656, state_count: 6656, occupied_states: 1024, unoccupied_states: 5632 },
    performance: { wall_time_seconds: 67366, nodes: 4, mpi_ranks: 4, omp_threads_per_rank: 96, evidence: [log] },
    auxiliary_basis: { mode: "pca_generated", threshold: 1e-4, evidence: ["data/calculations/3d/C/c512/inputs/INPUT"] },
    properties: [
      { key: "sampled_grid_gap_ev", category: "electronic", label: "Sampled Γ PBE gap", method: "PBE", value: 4.28347, unit: "eV", status: "validated", evidence: [result], definition: "Γ-point gap on the regular grid; not a global fundamental gap" },
      { key: "sampled_grid_gap_ev", category: "electronic", label: "Sampled Γ G0W0 gap", method: "G0W0", value: 6.09949, unit: "eV", status: "validated", evidence: [result], definition: "Γ-point gap on the regular grid; not a global fundamental gap" },
    ],
    files: { inputs: [{ path: "data/calculations/3d/C/c512/inputs/INPUT" }], results: [{ path: result, scientific_role: "qp_energy_table" }], logs: [{ path: log }], figures: [] },
    software: { abacus: { commit: null, identity_note: "Executable SHA-256 recorded" }, librpa: { commit: null, identity_note: "Executable SHA-256 recorded" } },
  };
  assert.equal(recordType(record), "large_system_gw");
  assert.equal(atomCount(record), 512);
  assert.deepEqual(primaryResult(record), { label: "Sampled Γ G0W0 gap", value: 6.09949, unit: "eV", scope: record.properties[1].definition });
  assert.deepEqual(performanceSummary(record).map(item => item.value), ["18:42:46", "4", "4", "96"]);
  const html = renderMaterial(record, []);
  assert.match(html, /Results &amp; evidence/);
  assert.match(html, /Computational scale &amp; performance/);
  assert.match(html, /512 atoms/);
  assert.match(html, /6656 QP states/);
  assert.match(html, /6\.09949/);
  assert.match(html, /18:42:46/);
  assert.match(html, /PCA with threshold 0\.0001/);
  assert.doesNotMatch(html, /Electronic bands|0 figures|plotting reference/);
});

test("reader conversion is clearly separated from RPA and GW results", () => {
  const receipt = "data/calculations/3d/C/c2048/results/reader_v1_conversion_receipt.json";
  const record = {
    id: "c2048", material: "C", formula: "C2048", dimension: "3d", record_type: "reader_conversion",
    workflow: { task: "reader_v1_conversion", scientific_result_available: false },
    computational_scale: { atom_count: 2048, matrix_rows: 26624, matrix_columns: 26624 },
    conversion: { elapsed_seconds: 1169, converter_sha256: "a".repeat(64), reader_header: [-12345679, 28, 1, 1, 26624, 26624], evidence: [receipt] },
    scientific_scope: { statement: "Reader-v1 eigenvector conversion only; no completed RPA or GW result is claimed." },
    summary: { observable: "Reader-v1 eigenvector conversion", value: 26624, unit: "matrix dimension" },
    properties: [], files: { inputs: [], results: [{ path: receipt, label: "Reader-v1 conversion receipt" }], logs: [], figures: [] },
  };
  assert.equal(recordType(record), "reader_conversion");
  assert.deepEqual(primaryResult(record), { label: "Reader-v1 matrix dimension", value: 26624, unit: "states", scope: "Conversion evidence only; no RPA/GW observable" });
  const html = renderMaterial(record, []);
  assert.match(html, /Reader-v1 conversion only/);
  assert.match(html, /2048/);
  assert.match(html, /26624 × 26624/);
  assert.match(html, /RPA result[\s\S]*Not claimed/);
  assert.match(html, /GW result[\s\S]*Not claimed/);
  assert.doesNotMatch(html, /Electronic bands|Sampled Γ G0W0 gap|fundamental gap/);
});

test("C2048 shows verified sampled Gamma gaps from the complete QP output", () => {
  const record = JSON.parse(readFileSync(new URL("../data/calculations/3d/C/c2048-reader-v1-20260607/record.json", import.meta.url)));
  assert.equal(recordType(record), "reader_conversion");
  assert.deepEqual(methodNames(record), ["PBE", "GW"]);
  const result = primaryResult(record);
  assert.equal(result.label, "Sampled Γ G0W0 gap");
  assert.equal(result.value, 5.74313);
  assert.equal(result.unit, "eV");
  const html = renderMaterial(record, []);
  assert.match(html, /4\.28728/);
  assert.match(html, /5\.74313/);
  assert.match(html, /Γ gaps verified/);
  assert.match(html, /frontier states.*present|frontier states.*verified/i);
  assert.match(html, /nonfinite|NaN|not.*satisfied/i);
  assert.match(html, /0\.585339 Ha[\s\S]*Fermi energy, not a gap/);
  assert.match(html, /20959369/);
  assert.match(html, /13:17:56/);
  assert.doesNotMatch(html, /Unavailable|fundamental gap|315\.02863/);
});

test("mobile calculation catalog uses semantic cards instead of an 850px table", () => {
  const css = readFileSync(new URL("../database/style.css", import.meta.url), "utf8");
  const app = readFileSync(new URL("../database/app.js", import.meta.url), "utf8");
  assert.match(css, /\.catalog-table:not\(\.basis-table\)\{display:block;min-width:0/);
  assert.match(css, /content:"Primary result"/);
  assert.match(app, /\["Material", "Software", "Scale", "Methods", "Primary result", "Inputs", ""\]/);
  assert.match(app, /<td><span class="record-type-tag">\$\{esc\(workflowLabel\(record\)\)\}<\/span><\/td>/);
  assert.match(app, /large-system GW results, and reader-format provenance/);
});

test("performance summary includes cluster and accelerator fields when present", () => {
  const record = { performance: { wall_time_seconds: 9298, nodes: 100, mpi_ranks: 100, omp_threads_per_rank: 30, cluster_label: "df_dcu", accelerators: 100, accelerator_label: "DCU" } };
  const summary = performanceSummary(record);
  const labels = summary.map(item => item.label);
  assert.ok(labels.includes("Cluster"));
  assert.ok(labels.includes("Accelerators"));
  assert.ok(labels.includes("Accelerator type"));
  const cluster = summary.find(item => item.label === "Cluster");
  assert.equal(cluster.value, "df_dcu");
  const accel = summary.find(item => item.label === "Accelerators");
  assert.equal(accel.value, "100");
  const accelType = summary.find(item => item.label === "Accelerator type");
  assert.equal(accelType.value, "DCU");
  const wall = summary.find(item => item.label === "Wall time");
  assert.match(wall.value, /2:34:58/);
});

test("performance summary omits empty cluster and accelerator fields", () => {
  const record = { performance: { wall_time_seconds: 67366, nodes: 4, mpi_ranks: 4, omp_threads_per_rank: 96 } };
  const summary = performanceSummary(record);
  const labels = summary.map(item => item.label);
  assert.ok(!labels.includes("Cluster"));
  assert.ok(!labels.includes("Accelerators"));
  assert.ok(!labels.includes("Accelerator type"));
});

test("workflow frontend defaults to abacus and resolves fhi_aims", () => {
  assert.equal(workflowFrontend({ workflow: { frontend: "fhi_aims" } }), "fhi_aims");
  assert.equal(workflowFrontend({ workflow: { frontend: "abacus" } }), "abacus");
  assert.equal(workflowFrontend({ workflow: {} }), "abacus");
  assert.equal(workflowFrontend({}), "abacus");
  assert.equal(frontendLabel({ workflow: { frontend: "fhi_aims" } }), "FHI-aims");
  assert.equal(frontendLabel({ workflow: { frontend: "abacus" } }), "ABACUS");
  assert.equal(frontendLabel({}), "ABACUS");
});

test("structure fingerprint extracts validated same-record identity hash", () => {
  const sha = "a".repeat(64);
  assert.equal(structureFingerprint({ structure_identity: { algorithm: "cell-sites-v1", sha256: sha } }), sha);
  assert.equal(structureFingerprint({ structure_identity: { algorithm: "other", sha256: sha } }), null);
  assert.equal(structureFingerprint({ structure_identity: { algorithm: "cell-sites-v1", sha256: "short" } }), null);
  assert.equal(structureFingerprint({}), null);
});

test("same-structure records are found by fingerprint and exclude self", () => {
  const sha = "f".repeat(64);
  const record = { id: "r1", structure_identity: { algorithm: "cell-sites-v1", sha256: sha } };
  const peer = { id: "r2", structure_identity: { algorithm: "cell-sites-v1", sha256: sha } };
  const other = { id: "r3", structure_identity: { algorithm: "cell-sites-v1", sha256: "e".repeat(64) } };
  const noIdentity = { id: "r4" };
  const peers = sameStructureRecords(record, [record, peer, other, noIdentity]);
  assert.equal(peers.length, 1);
  assert.equal(peers[0].id, "r2");
  assert.equal(sameStructureRecords(noIdentity, [record, peer]).length, 0);
});

test("cross-frontend records pair same material across frontends, excluding fingerprint-linked peers", () => {
  const sharedSha = "a".repeat(64);
  const record = { id: "si-paper", material: "Si", workflow: { frontend: "abacus" }, structure_identity: { algorithm: "cell-sites-v1", sha256: sharedSha } };
  const linkedPeer = { id: "si-jctc-exact", material: "Si", workflow: { frontend: "fhi_aims" }, structure_identity: { algorithm: "cell-sites-v1", sha256: sharedSha } };
  const relaxedPeer = { id: "si-jctc", material: "Si", workflow: { frontend: "fhi_aims" }, structure_identity: { algorithm: "cell-sites-v1", sha256: "b".repeat(64) } };
  const sameFrontend = { id: "si-paper-2", material: "Si", workflow: { frontend: "abacus" } };
  const otherMaterial = { id: "gaas-jctc", material: "GaAs", workflow: { frontend: "fhi_aims" } };
  const peers = crossFrontendRecords(record, [record, linkedPeer, relaxedPeer, sameFrontend, otherMaterial]);
  assert.equal(peers.length, 1);
  assert.equal(peers[0].id, "si-jctc");
  const reverse = crossFrontendRecords(relaxedPeer, [record, linkedPeer, relaxedPeer, sameFrontend, otherMaterial]);
  assert.deepEqual(reverse.map(peer => peer.id), ["si-paper", "si-paper-2"]);
});

test("detail page shows cross-frontend same-material comparison with a structure caveat", () => {
  const record = {
    id: "si-paper-all-kpath", material: "Si", formula: "Si", dimension: "3d",
    record_type: "band",
    workflow: { frontend: "abacus", task: "gw" },
    structure_identity: { algorithm: "cell-sites-v1", sha256: "a".repeat(64) },
    properties: [{ key: "band_gap", category: "electronic", method: "GW", unit: "eV", status: "reported", value: 1.2 }],
    files: {},
  };
  const peer = {
    id: "si-jctc-aims-gw", material: "Si", formula: "Si", dimension: "3d",
    record_type: "band",
    workflow: { frontend: "fhi_aims", task: "gw" },
    structure_identity: { algorithm: "cell-sites-v1", sha256: "b".repeat(64) },
    properties: [{ key: "band_gap", category: "electronic", method: "GW", unit: "eV", status: "reported", value: 1.24 }],
    files: {},
  };
  const html = renderMaterial(record, [], [record, peer]);
  assert.match(html, /Same material across frontends/);
  assert.match(html, /the FHI-aims frontend/);
  assert.match(html, /not identical-structure comparisons/);
  assert.match(html, /si-jctc-aims-gw · Band structure/);
  assert.doesNotMatch(html, /Same-structure calculations/);
  const aimsHtml = renderMaterial(peer, [], [record, peer]);
  assert.match(aimsHtml, /the ABACUS frontend/);
  assert.match(aimsHtml, /si-paper-all-kpath/);
});

test("detail page shows frontend tag and same-structure comparison when peers exist", () => {
  const sha = "d".repeat(64);
  const record = {
    id: "abacus-c2048", material: "C", formula: "C2048", dimension: "3d",
    workflow: { frontend: "abacus" },
    structure_identity: { algorithm: "cell-sites-v1", sha256: sha },
    properties: [], files: {},
  };
  const peer = {
    id: "aims-c2048", material: "C", formula: "C2048", dimension: "3d",
    record_type: "rpa_energy",
    workflow: { frontend: "fhi_aims", task: "rpa" },
    structure_identity: { algorithm: "cell-sites-v1", sha256: sha },
    properties: [{ key: "rpa_correlation_energy", value: -418.49, unit: "Ha", status: "reported" }],
    files: {},
  };
  const html = renderMaterial(record, [], [record, peer]);
  assert.match(html, /ABACUS \+ LibRPA/);
  assert.match(html, /Same-structure calculations/);
  assert.match(html, /aims-c2048/);
  assert.match(html, /FHI-aims \+ LibRPA/);
  assert.match(html, /-418\.49000/);
  assert.doesNotMatch(html, /Same material across frontends/);
});

test("rpa energy detail page renders results, scale, and performance instead of band sections", () => {
  const record = {
    id: "c-rpa", material: "C", formula: "C2048", dimension: "3d",
    record_type: "rpa_energy",
    workflow: { frontend: "abacus", task: "rpa" },
    computational_scale: { atom_count: 2048, ao_count: 26624 },
    performance: { cluster_label: "df_dcu", wall_time_seconds: 9298, nodes: 100, mpi_ranks: 100, omp_threads_per_rank: 30, accelerators: 100, accelerator_label: "DCU x1/node (100 total)" },
    auxiliary_basis: { mode: "pca_generated", threshold: 0.0001 },
    structure_identity: { algorithm: "cell-sites-v1", sha256: "d".repeat(64) },
    properties: [{ key: "rpa_correlation_energy", category: "energetic", label: "RPA correlation energy", method: "RPA", unit: "Ha", status: "reported", value: -418.489041942, evidence: ["data/calculations/3d/C/c-rpa/results/LibRPA.out"] }],
    files: { results: [{ path: "data/calculations/3d/C/c-rpa/results/LibRPA.out" }] },
  };
  const html = renderMaterial(record, [], [record]);
  assert.match(html, /RPA energy calculation/);
  assert.match(html, /Results &amp; evidence/);
  assert.match(html, /Computational scale &amp; performance/);
  assert.match(html, /2048 atoms/);
  assert.match(html, /2:34:58/);
  assert.match(html, /DCU x1\/node \(100 total\)/);
  assert.match(html, /-418\.489041942/);
  assert.match(html, /RPA energy/);
  assert.match(html, /PCA with threshold 0\.0001/);
  assert.doesNotMatch(html, /Electronic bands|plotting reference/);
});

test("detail page shows ABACUS tag by default and no comparison when alone", () => {
  const record = { id: "solo", material: "Si", dimension: "3d", workflow: {}, properties: [], files: {} };
  const html = renderMaterial(record, [], [record]);
  assert.match(html, /ABACUS \+ LibRPA/);
  assert.doesNotMatch(html, /Same-structure calculations/);
});

test("detail page software section uses dynamic frontend name", () => {
  const record = {
    id: "aims-test", material: "Si", dimension: "3d",
    workflow: { frontend: "fhi_aims" },
    software: { fhi_aims: { commit: "a".repeat(40) }, librpa: { commit: "b".repeat(40) } },
    properties: [], files: {},
  };
  const html = renderMaterial(record, [], []);
  assert.match(html, /<h3>FHI-aims<\/h3>/);
  assert.match(html, /<h3>LibRPA<\/h3>/);
  assert.doesNotMatch(html, /<h3>ABACUS<\/h3>/);
});

test("SOC label renders only for records whose catalog entry enables spin-orbit coupling", () => {
  assert.equal(socTag({ spin_orbit: true }), '<span class="method-tag method-soc">SOC</span>');
  assert.equal(socTag({ spin_orbit: false }), "");
  assert.equal(socTag({}), "");
  assert.equal(socTag(null), "");
  const socRecord = { id: "soc", material: "GaAs", dimension: "3d", workflow: {}, properties: [], files: {}, spin_orbit: true };
  assert.match(renderMaterial(socRecord, []), /method-soc">SOC/);
  const plainRecord = { id: "plain", material: "GaAs", dimension: "3d", workflow: {}, properties: [], files: {}, spin_orbit: false };
  assert.doesNotMatch(renderMaterial(plainRecord, []), /method-soc/);
});

test("SPIN label renders only for records whose catalog entry enables collinear two-channel spin", () => {
  assert.equal(spinPolTag({ spin_polarized: true }), '<span class="method-tag method-spin">SPIN</span>');
  assert.equal(spinPolTag({ spin_polarized: false }), "");
  assert.equal(spinPolTag({}), "");
  assert.equal(spinPolTag(null), "");
  const spinRecord = { id: "afm", material: "NiO", dimension: "3d", workflow: {}, properties: [], files: {}, spin_polarized: true };
  assert.match(renderMaterial(spinRecord, []), /method-spin">SPIN/);
  assert.doesNotMatch(renderMaterial(spinRecord, []), /method-soc/);
  const plainRecord = { id: "plain", material: "NiO", dimension: "3d", workflow: {}, properties: [], files: {}, spin_polarized: false };
  assert.doesNotMatch(renderMaterial(plainRecord, []), /method-spin/);
});

test("catalog spin-setting flags mark exactly the records with explicit input switches", () => {
  const catalog = JSON.parse(readFileSync(new URL("../database/data.json", import.meta.url), "utf8"));
  const socIds = catalog.calculations.filter(record => record.spin_orbit === true).map(record => record.id);
  assert.deepEqual(socIds, ["gaas-abacus-gw-soc-32freq"]);
  const spinIds = catalog.calculations.filter(record => record.spin_polarized === true).map(record => record.id);
  assert.deepEqual(spinIds, ["nio-aims-gw-int"]);
  for (const record of catalog.calculations) {
    const html = renderMaterial(record, catalog.basis_sets);
    if (record.spin_orbit === true) assert.match(html, /method-soc">SOC/, record.id);
    else assert.doesNotMatch(html, /method-soc/, record.id);
    if (record.spin_polarized === true) assert.match(html, /method-spin">SPIN/, record.id);
    else assert.doesNotMatch(html, /method-spin/, record.id);
  }
});

test("catalog method chips keep the method-dft class for every mean-field functional", () => {
  const catalog = JSON.parse(readFileSync(new URL("../database/data.json", import.meta.url), "utf8"));
  for (const record of catalog.calculations) {
    const html = renderMaterial(record, catalog.basis_sets);
    assert.doesNotMatch(html, /method-(?:pbe|lda|gga|pbesol|scan|hse)\b/, record.id);
    for (const text of [...html.matchAll(/method-tag method-dft">([^<]+)</g)].map(match => match[1])) {
      assert.ok(["DFT", "PBE", "LDA", "GGA", "PBEsol", "SCAN", "HSE"].includes(text), `${record.id}: unexpected chip text ${text}`);
    }
  }
  assert.equal(catalog.calculations.filter(record => record.functional === "PBE").length, 112);
  assert.equal(catalog.calculations.filter(record => methodNames(record).includes("PBE")).length, 113);
  assert.equal(catalog.calculations.filter(record => methodNames(record).includes("DFT")).length, 0);
  assert.equal(catalog.calculations.filter(record => methodNames(record).includes("EXX")).length, 84);
});
