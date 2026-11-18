import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { recordCitation, citationBox, copyCitation } from "../database/citation.mjs";
import { renderMaterial } from "../database/details.mjs";

const fixture = path => JSON.parse(readFileSync(new URL(`../data/calculations/${path}/record.json`, import.meta.url), "utf8"));
const record = { id: "trial_1", material: "A&B", dimension: "3d" };
const page = "https://aroundpeking.github.io/LibRPA-database/database/#/material/trial_1";

test("plain text and BibTeX identify the record independently of the paper", () => {
  const { text, bibtex } = recordCitation(record);
  assert.equal(text, `A&B — LibRPA Materials Database. Calculation record: trial_1. ${page}`);
  assert.ok(bibtex.includes(`url   = {${page}}`));
  assert.ok(bibtex.includes("A\\&B"));
  assert.ok(bibtex.includes("Calculation record: trial\\_1"));
  assert.doesNotMatch(bibtex, /\b(author|year|doi)\s*=/i);
  assert.doesNotMatch(citationBox(record), /&amp;amp;|Original sources/);
});

test("a visible header link identifies the citation view and a direct visit starts open", () => {
  const plain = renderMaterial(record, []);
  assert.match(plain, /href="#\/material\/trial_1\?cite=1"[^>]*>Cite this record/);
  assert.match(plain, /id="record-citation"><summary>/);
  assert.ok(plain.indexOf('id="record-citation"') < plain.indexOf('class="detail-layout"'));
  const html = renderMaterial(record, [], [], { cite: true });
  assert.match(html, /id="record-citation" open><summary>Cite this record/);
  assert.match(html, /aria-label="Plain text record citation"/);
  assert.match(html, /aria-label="BibTeX record citation"/);
});

test("published 3D values cite their paper, DOI, table/page and original archive, not a DOI for the record", () => {
  const r = fixture("3d/Si/si-paper-all_kpath");
  const html = citationBox(r);
  assert.ok(html.includes(r.paper_values.source.title));
  assert.ok(html.includes(`href="https://doi.org/${r.paper_values.source.doi}"`));
  assert.match(html, /Table IV, PDF p\. 16/);
  assert.ok(html.includes(`${r.source.repository}/tree/${r.source.archive_commit}/${r.source.archive_directory}`));
  const extract = r.files.results.find(f => f.path === r.paper_values.evidence);
  assert.ok(html.includes(`href="${extract.external_url}"`));
  assert.ok(!recordCitation(r).bibtex.includes(r.paper_values.source.doi));
});

test("2D table values retain the title and evidence even without a DOI", () => {
  const r = fixture("2d/MoS2/mos2-table-gw");
  const html = citationBox(r);
  assert.ok(html.includes(r.paper_values.source.title));
  assert.match(html, /Table I, PDF p\. 12/);
  assert.doesNotMatch(html, /doi\.org|DOI:/);
  assert.ok(html.includes(r.files.results.find(f => f.path === r.paper_values.evidence).external_url));
  const compact = { ...r, files: undefined };
  assert.doesNotMatch(citationBox(compact), /href="\.\.\/data\/.*paper_reported_values/);
});

test("submitted supporting data are identified by their own manuscript ID and archive, not promoted to a published paper", () => {
  const r = fixture("3d/Si/si-jctc-librpa-32");
  const html = citationBox(r);
  assert.ok(html.includes(r.publication.manuscript_id));
  assert.ok(html.includes(r.source.tar));
  assert.match(html, /submitted/);
  assert.doesNotMatch(html, /doi\.org|DOI:|published in/i);
});

test("cite measurements only for explicitly compatible computed observables", () => {
  const r = { ...record, structure_identity: { algorithm: "cell-sites-v1", sha256: "1".repeat(64) }, properties: ["PBE", "EXX"].map(method => ({ category: "electronic", key: "band_gap", method, definition: "Fixture electronic gap", status: "reported", value: 1, unit: "eV" })) };
  r.experimental_gap = { value: 1.1, unit: "eV", definition: "Synthetic gap definition", source: { citation: "Synthetic measurement", locator: "Fixture row A", url: "https://example.invalid/measurement" }, compatibility: { record_id: r.id, structure_sha256: r.structure_identity.sha256, structure_note: "Fixture match", methods: { ks: { compatible: true, observable: "property:band_gap:PBE", reason: "Fixture match" } } } };
  const html = citationBox(r);
  assert.match(html, /Experimental measurement \(matched to DFT \/ KS\)/);
  assert.ok(html.includes('href="https://example.invalid/measurement"'));
  assert.match(html, /Synthetic measurement/);
  assert.match(html, /Fixture row A/);
  assert.match(html, /Synthetic gap definition/);
  assert.ok(!recordCitation(r).text.includes("Synthetic measurement"));
  r.experimental_gap.compatibility.methods.ks.observable = "paper:DFT";
  assert.doesNotMatch(citationBox(r), /Synthetic measurement|Original sources/);
});

test("record JSON-LD is parseable, uses the same permalink and safely preserves raw title text", () => {
  const special = { ...record, material: "A </script> B" };
  const html = renderMaterial(special, []);
  const raw = html.match(/<script type="application\/ld\+json" data-jsonld>(.*?)<\/script>/s)[1];
  const data = JSON.parse(raw);
  assert.equal(data.name, `${special.material} — LibRPA Materials Database`);
  assert.equal(data.url, page);
  assert.equal(data.identifier, record.id);
  assert.equal(data.creator, undefined);
  assert.equal(data.datePublished, undefined);
});

function copyState() {
  return { area: { value: "the citation", isConnected: true, parentElement: { hidden: false }, focus() { this.focused = true; }, select() { this.selected = true; } }, status: { textContent: "" } };
}

test("clipboard confirmation waits for success; denied writes select for manual copy", async () => {
  const { area, status } = copyState();
  let done;
  const task = copyCitation(area, status, text => {
    assert.equal(text, area.value);
    return new Promise(resolve => { done = resolve; });
  });
  assert.doesNotMatch(status.textContent, /copied/i);
  done();
  await task;
  assert.equal(status.textContent, "Copied.");
  await copyCitation(area, status, async () => { throw new Error("Clipboard blocked"); });
  assert.equal(area.selected, true);
  assert.equal(area.focused, true);
  assert.doesNotMatch(status.textContent, /copied/i);
  assert.match(status.textContent, /Ctrl\+C/);
});
