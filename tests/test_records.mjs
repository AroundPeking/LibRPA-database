import test from "node:test";
import assert from "node:assert/strict";
import { bandGap, boundFiles, publicPath, fileName, downloadName, setRelation, methodNames, inputStage } from "../database/records.mjs";
import { renderFiles } from "../database/files.mjs";
import { renderMaterial } from "../database/details.mjs";
import { readFileSync } from "node:fs";

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

test("restricted hBN frontier gap is retained with scope but never used as ordinary GW gap", () => {
  const record = JSON.parse(readFileSync(new URL("../data/calculations/2d/hBN/hbn-tzdp10-fgext-20261008/record.json", import.meta.url)));
  assert.equal(bandGap(record), null);
  const html = renderMaterial(record, []);
  assert.match(html, /Restricted result/);
  assert.match(html, /6\.94183/);
  assert.match(html, /GW raw-band-5 frontier path gap/);
  assert.match(html, /PBE valley-order gate FAILED/);
});

test("all figure metadata attachments remain available", () => {
  const record = JSON.parse(readFileSync(new URL("../data/calculations/3d/Si/si-paper-all_kpath/record.json", import.meta.url)));
  const html = renderMaterial(record, []);
  assert.match(html, /Figure source &amp; metadata/);
  assert.match(html, /band_comparison\.json/);
});

test("Commit号 keeps software identity while completeness issues and gates move to Overview", () => {
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
  assert.match(commits, /<h2>Commit号<\/h2>/);
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
  assert.match(html, /Each method uses its own occupied path VBM and energy window/);
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
  assert.match(app, /archived k-path, not the global fundamental gap/);
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
