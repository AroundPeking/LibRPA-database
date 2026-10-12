import test from "node:test";
import assert from "node:assert/strict";
import { bandGap, archivedBandGap, paperGap, boundFiles, publicPath, fileName, downloadName, setRelation, methodNames, inputStage } from "../database/records.mjs";
import { renderFiles } from "../database/files.mjs";
import { renderMaterial } from "../database/details.mjs";
import { readFileSync } from "node:fs";

test("partial stage controls stay explicitly incomplete and retain redaction provenance", () => {
  const path = "data/calculations/2d/MoTe2/mote2-table-gw/results/stage_input_receipt.json";
  const record = { id: "mote2-table-gw", material: "MoTe2", dimension: "2d", status: "gw_diagnostic", summary: {}, source: { stage_input_receipt: path }, files: { inputs: [{ path: "data/calculations/2d/MoTe2/mote2-table-gw/inputs/recovered/stage/librpa.in", sha256: "a".repeat(64), original_sha256: "b".repeat(64), transformation: "private server path redacted; not a rerun bundle" }] }, archive_completeness: { status: "incomplete", issues: ["software missing"] } };
  const html = renderMaterial(record, []);
  assert.match(html, /Partial stage inputs · not a complete rerun bundle/);
  assert.match(html, /View stage-input receipt/);
  assert.match(html, /Upload incomplete · CI blocked/);
  assert.match(html, /Original SHA-256/);
  assert.match(html, new RegExp("b".repeat(64)));
  assert.doesNotMatch(html, /Upload complete · archive checks passed/);
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
    for (const method of ["DFT", "EXX", "GW"]) {
      const value = bandGap(record, method);
      if (value !== null) assert.ok(headline.includes(value.toFixed(paperGap(record, method)?.precision ?? 3)), `${record.id} ${method}`);
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
  record.status = "path_diagnostic";
  assert.equal(bandGap(record), 2.674);
  assert.equal(archivedBandGap(record), null);
  assert.equal(paperGap(record).value, 2.674);
  assert.match(renderMaterial(record, []), /Restricted path · not an accepted fundamental gap/);
  record.paper_values.values.DFT.value = Infinity;
  assert.equal(bandGap(record, "DFT"), 0.60168);
  record.paper_values.values.DFT.value = 1.80171;
  record.files.results = [];
  assert.equal(paperGap(record, "DFT"), null);
  assert.equal(bandGap(record, "DFT"), 0.60168);
});

test("new hBN shows the cited 6.94183 headline without accepting the restricted archive", () => {
  const record = JSON.parse(readFileSync(new URL("../data/calculations/2d/hBN/hbn-tzdp10-fgext-20261008/record.json", import.meta.url)));
  assert.equal(record.status, "path_diagnostic");
  assert.equal(bandGap(record), 6.94183);
  assert.equal(bandGap(record, "DFT"), 4.68813);
  assert.equal(archivedBandGap(record), null);
  const html = renderMaterial(record, []);
  const headline = html.slice(html.indexOf('class="result-strip"'), html.indexOf('class="detail-layout"'));
  assert.match(headline, /GW band gap/);
  assert.doesNotMatch(headline, /paper-reported/);
  assert.match(headline, /6\.94183/);
  assert.match(headline, /Restricted path · not an accepted fundamental gap/);
  assert.doesNotMatch(headline, /Restricted result|6\.68084/);
  assert.match(html, /GW raw-band-5 frontier path gap/);
  assert.match(html, /PBE valley-order gate FAILED/);
  assert.match(html, /numerical sorting uses that value/);
  const old = JSON.parse(readFileSync(new URL("../data/calculations/2d/hBN/hbn-table-gw/record.json", import.meta.url)));
  assert.equal(old.paper_values, undefined);
  assert.equal(bandGap(old), 6.68084);
  delete record.paper_values;
  assert.equal(bandGap(record), null);
  assert.match(renderMaterial(record, []), /Restricted result/);
});

test("all figure metadata attachments remain available", () => {
  const record = JSON.parse(readFileSync(new URL("../data/calculations/3d/Si/si-paper-all_kpath/record.json", import.meta.url)));
  const html = renderMaterial(record, []);
  assert.match(html, /Figure source &amp; metadata/);
  assert.match(html, /band_comparison\.json/);
});

test("Source commits keeps software identity while completeness issues and gates move to Overview", () => {
  const record = {
    id: "ui-check", material: "Si", dimension: "3d", summary: { gates: ["SCF evidence pending"] },
    missing: ["Original input unavailable"],
    archive_completeness: { status: "incomplete", issues: ["Missing <INPUT>"] },
    software: { abacus: { commit: "a".repeat(40) }, librpa: { commit: "b".repeat(40) } },
  };
  const html = renderMaterial(record, []);
  const overview = html.slice(html.indexOf('id="record-overview"'), html.indexOf('id="record-structure"'));
  const commits = html.slice(html.indexOf('id="record-evidence"'));
  assert.match(overview, /Archive completeness/);
  assert.match(overview, /Upload incomplete · CI blocked/);
  assert.match(overview, /Missing &lt;INPUT&gt;/);
  assert.match(overview, /Original input unavailable/);
  assert.match(overview, /SCF evidence pending/);
  assert.match(commits, /<h2>Source commits<\/h2>/);
  assert.match(commits, new RegExp("a".repeat(40)));
  assert.match(commits, new RegExp("b".repeat(40)));
  assert.doesNotMatch(commits, /Original input unavailable|SCF evidence pending/);
  assert.doesNotMatch(html, /Provenance &(?:amp;)? limitations/);
});

test("method diagnostics remain visible without inventing an ordinary gap", () => {
  const record = { id: "diagnostic", material: "GeTe", dimension: "2d", properties: [],
    method_diagnostics: [{ method: "EXX", status: "rejected", message: "Pathology <raw spectrum>",
      full_raw_path_gap_ev: -1002817.14856, frozen_window_path_gap_ev: -70.88803 }] };
  assert.equal(bandGap(record, "EXX"), null);
  const html = renderMaterial(record, []);
  assert.match(html, /Method diagnostics · not an accepted gap/);
  assert.match(html, /Pathology &lt;raw spectrum&gt;/);
  assert.match(html, /-1002817\.14856/);
  assert.match(html, /-70\.88803/);
  assert.doesNotMatch(html, /Pathology <raw spectrum>/);
});

test("unknown archive completeness is never claimed complete", () => {
  const record = { id: "unknown", material: "Si", dimension: "3d" };
  assert.match(renderMaterial(record, []), /Upload completeness not recorded/);
  assert.doesNotMatch(renderMaterial(record, []), /Upload complete · archive checks passed/);
  record.archive_completeness = { status: "complete", issues: [] };
  assert.match(renderMaterial(record, []), /Upload complete · archive checks passed/);
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
  assert.match(html, /Original archived figures · 1/);
  assert.match(html, /download="original\.png"/);
  assert.match(html, /figure\.json/);
  assert.match(html, /href="\.\.\/references\/plotting\.md"/);
  assert.match(html, /reusable band-figure script/);
  assert.match(html, /Each method uses its own occupied path VBM/);
  assert.match(html, /full extent of the already-selected curves, without adding bands/);
  record.files.figures[0].display_priority = "secondary";
  const fallback = renderMaterial(record, []);
  assert.match(fallback, /primary\.svg/);
  assert.match(fallback, /original\.png/);
  assert.doesNotMatch(fallback, /class="original-figures"/);
});

test("archived diagnostic figures are labelled without implying acceptance", () => {
  const record = { id: "diagnostic-figure", material: "GeTe", dimension: "2d", files: { figures: [
    { path: "data/case/exx.png", scientific_status: "archived_diagnostic" },
  ] } };
  const html = renderMaterial(record, []);
  assert.match(html, /Archived diagnostic · not an accepted result/);
  assert.match(html, /download="exx\.png"/);
  assert.doesNotMatch(html, /Upload complete · archive checks passed/);
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
  assert.match(app, /archived k-path is not the global fundamental gap/);
  assert.match(app, /database values are in eV/);
  assert.doesNotMatch(app, /Paper-reported · Table|Original path values and differences are retained/);
});

test("database branding is front-end neutral and supports ABACUS and FHI-aims workflows", () => {
  const index = readFileSync(new URL("../database/index.html", import.meta.url), "utf8");
  const app = readFileSync(new URL("../database/app.js", import.meta.url), "utf8");
  assert.match(index, /<span>LibRPA<small>MATERIALS DATABASE<\/small><\/span>/);
  assert.match(index, /ABACUS and FHI-aims workflows/);
  assert.doesNotMatch(index, /ABACUS <b>\+<\/b> LibRPA|Materials database · ABACUS/);
  assert.doesNotMatch(app, / · ABACUS \+ LibRPA/);
});

test("header and favicon share a small editable SVG brand mark", () => {
  const index = readFileSync(new URL("../database/index.html", import.meta.url), "utf8");
  const logo = readFileSync(new URL("../database/logo.svg", import.meta.url), "utf8");
  const css = readFileSync(new URL("../database/style.css", import.meta.url), "utf8");
  assert.match(index, /rel="icon"[^>]*href="logo\.svg"/);
  assert.match(index, /class="brand-mark"[^>]*src="logo\.svg"[^>]*alt=""[^>]*aria-hidden="true"/);
  assert.doesNotMatch(index, /data:image\/svg\+xml/);
  assert.match(logo, /viewBox="0 0 48 48"/);
  for (const id of ["lattice", "conduction-band", "valence-band"]) assert.match(logo, new RegExp(`id="${id}"`));
  assert.doesNotMatch(logo, /<text\b|<image\b|<script\b/);
  assert.match(css, /\.brand-mark \{[^}]*width: 48px; height: 48px/);
  assert.match(css, /\.brand-mark \{[^}]*width: 32px; height: 32px/);
});

test("short and unknown software identifiers are kept without claiming full commits", () => {
  const record = { id: "partial-commit", material: "Si", dimension: "3d", software: { abacus: { commit: "123abcd", source_url: "https://github.com/example/code" }, librpa: { commit: "unknown" } } };
  const html = renderMaterial(record, []);
  const commits = html.slice(html.indexOf('id="record-evidence"'));
  assert.match(commits, /123abcd/);
  assert.match(commits, /unknown/);
  assert.equal((commits.match(/Full commit not recorded/g) || []).length, 2);
  assert.doesNotMatch(commits, /\/commit\/123abcd/);
  assert.match(html, /ABACUS: full source commit not recorded\./);
});

test("figure downloads honor aliases and invalid figure paths never become links", () => {
  const record = { id: "figure-paths", material: "Si", dimension: "3d", files: { figures: [
    { path: "data/case/figure.svg", download_name: "Si_PBE_GW.svg" },
    { path: "../private.svg" },
  ] } };
  const html = renderMaterial(record, []);
  assert.match(html, /download="Si_PBE_GW\.svg"/);
  assert.match(html, /Invalid archive path; figure link disabled/);
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

test("file rows preserve path and hash, expose view/download and label unknown originals", () => {
  const html = renderFiles([{ path: "data/hash.orb", sha256: "abc123", display_name: "Si_NAO_abc.orb", download_name: "Si_NAO_abc.orb", name_source: "descriptive_alias", role: "nao", size_bytes: 100 }]);
  assert.match(html, /data-preview="data\/hash.orb"/);
  assert.match(html, /download="Si_NAO_abc.orb"/);
  assert.match(html, /original filename not recorded/);
  assert.match(html, /abc123/);
  assert.doesNotMatch(html, />payload</);
  assert.match(renderFiles([{ path: "data/x", label: "<script>bad</script>" }]), /&lt;script&gt;/);
});

test("nested input archive names retain stage labels", () => {
  assert.equal(inputStage({ path: "data/case/inputs/calculation__pbe_path__STRU" }), "calculation / pbe_path");
});

test("methods can come from contributed properties without inventing a figure", () => {
  assert.deepEqual(methodNames({ properties: [{ category: "electronic", method: "G0W0", status: "reported" }] }), ["GW"]);
});
