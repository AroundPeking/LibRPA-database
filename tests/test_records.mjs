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
