import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { recordElements, formulaHtml, ELEMENT_SYMBOLS } from "../database/records.mjs";
import { ELEMENTS, ELEMENT_BY_SYMBOL, elementPosition, heatLevel, renderPeriodicTable } from "../database/ptable.mjs";
import { recordFacts, matchesElements, filterFacts, facetCounts, sortFacts, factsToCsv, factsToJson, csvCell, readExplorerParams, writeExplorerParams, renderHeader, renderMaterialRow, visibleColumns, DEFAULT_COLUMNS, COLUMNS, EXPORT_FIELDS } from "../database/explorer.mjs";
import { renderMaterial } from "../database/details.mjs";

const catalog = JSON.parse(readFileSync(new URL("../database/data.json", import.meta.url), "utf8"));
const facts = catalog.calculations.map(recordFacts);
const read = name => readFileSync(new URL(`../database/${name}`, import.meta.url), "utf8");

test("the periodic table places all 118 elements in the 18-column layout", () => {
  assert.equal(ELEMENTS.length, 118);
  assert.equal(new Set(ELEMENTS.map(element => element.symbol)).size, 118);
  assert.deepEqual(elementPosition(1), [1, 1]);
  assert.deepEqual(elementPosition(2), [1, 18]);
  assert.deepEqual(elementPosition(5), [2, 13]);
  assert.deepEqual(elementPosition(57), [6, 3]);
  assert.deepEqual(elementPosition(72), [6, 4]);
  assert.deepEqual(elementPosition(71), [9, 17]);
  assert.deepEqual(elementPosition(103), [10, 17]);
  assert.deepEqual(elementPosition(118), [7, 18]);
  const cells = new Set(ELEMENTS.map(element => `${element.row}:${element.column}`));
  assert.equal(cells.size, 118, "no two elements share a cell");
  assert.equal(ELEMENT_BY_SYMBOL.get("Si").name, "Silicon");
  assert.deepEqual([...ELEMENT_SYMBOLS], ELEMENTS.map(element => element.symbol));
});

test("periodic-table cells are buttons only where records exist, shaded by count", () => {
  const counts = new Map([["all", 122], ["Si", 10], ["C", 5], ["Ga", 1]]);
  const html = renderPeriodicTable({ counts, available: new Set(["Si", "C", "Ga"]), selected: new Set(["C"]) });
  assert.equal((html.match(/<button /g) || []).length, 3);
  assert.match(html, /data-element="Si" aria-pressed="false" aria-label="Silicon \(Si\), 10 records"/);
  assert.match(html, /class="pt-cell pt-heat-3 is-selected"[^>]*data-element="C" aria-pressed="true"/);
  assert.match(html, /class="pt-cell pt-heat-5"[^>]*data-element="Si"/, "the 'all' total never sets the scale");
  assert.match(html, /<span class="pt-cell pt-empty"[^>]*aria-hidden="true"><small>26<\/small><b>Fe<\/b><\/span>/);
  assert.doesNotMatch(html, /has-f-block|>Ce</, "f-block rows are drawn only with data");
  assert.match(renderPeriodicTable({ counts: new Map([["U", 1]]), available: new Set(["U"]) }), /has-f-block[\s\S]*data-element="U"/);
  assert.equal(heatLevel(0, 10), 0);
  assert.equal(heatLevel(1, 10), 1);
  assert.equal(heatLevel(10, 10), 5);
});

test("element parsing keeps only real symbols, so Phosphorene adds no Ph", () => {
  assert.deepEqual(recordElements({ material: "Phosphorene", formula: "Phosphorene", species: [{ element: "P", set_id: "x" }] }), ["P"]);
  assert.deepEqual(recordElements({ material: "MoS2-WS2" }), ["Mo", "S", "W"]);
  for (const record of catalog.calculations) {
    for (const symbol of recordElements(record)) assert.ok(ELEMENT_SYMBOLS.has(symbol), `${record.id}: ${symbol}`);
  }
});

test("formulas render counts as subscripts and stay escaped", () => {
  assert.equal(formulaHtml("MoS2"), "MoS<sub>2</sub>");
  assert.equal(formulaHtml("CuInP2Se6"), "CuInP<sub>2</sub>Se<sub>6</sub>");
  assert.equal(formulaHtml("MoS2-WS2"), "MoS<sub>2</sub>-WS<sub>2</sub>");
  assert.equal(formulaHtml("hBN"), "hBN");
  assert.equal(formulaHtml("<b>2"), "&lt;b&gt;2");
});

test("element search means 'contains all' or the exact chemical system", () => {
  assert.equal(matchesElements(["As", "Ga"], ["Ga"], "all"), true);
  assert.equal(matchesElements(["As", "Ga"], ["Ga"], "only"), false);
  assert.equal(matchesElements(["As", "Ga"], ["Ga", "As"], "only"), true);
  assert.equal(matchesElements(["As", "Ga", "N"], ["Ga", "As"], "only"), false);
  assert.equal(matchesElements(["Si"], [], "only"), true);
  const gaas = filterFacts(facts, { elements: ["Ga", "As"], elementMode: "only" });
  assert.ok(gaas.length >= 2 && gaas.every(row => row.elements.join() === "As,Ga"));
  assert.ok(filterFacts(facts, { elements: ["Ga"] }).length > gaas.length);
});

test("facets count what each option would show next to the other filters", () => {
  const counts = facetCounts(facts, {});
  assert.equal(counts.dimension.get("all"), facts.length);
  assert.equal((counts.dimension.get("2d") || 0) + (counts.dimension.get("3d") || 0), facts.length);
  assert.equal([...counts.type].filter(([key]) => key !== "all").reduce((sum, [, n]) => sum + n, 0), facts.length);
  const narrowed = facetCounts(facts, { dimension: "2d" });
  assert.equal(narrowed.dimension.get("3d"), counts.dimension.get("3d"), "a facet ignores its own selection");
  assert.equal(narrowed.software.get("all"), counts.dimension.get("2d"), "other facets respect it");
  const soc = filterFacts(facts, { methods: ["SOC"] });
  assert.equal(soc.length, counts.methods.get("SOC"));
  assert.ok(soc.every(row => row.methods.includes("SOC")));
});

test("a GW-gap range keeps only records with a GW gap inside it", () => {
  const ranged = filterFacts(facts, { gapMin: 1, gapMax: 2 });
  assert.ok(ranged.length > 0);
  assert.ok(ranged.every(row => row.gw !== null && row.gw >= 1 && row.gw <= 2));
  assert.equal(filterFacts(facts, { gapMin: 0 }).length, facts.filter(row => row.gw !== null).length);
});

test("sorting is total, puts missing values last, and toggles direction", () => {
  const ascending = sortFacts(facts, "ks", "asc").map(row => row.ks);
  const descending = sortFacts(facts, "ks", "desc").map(row => row.ks);
  for (const values of [ascending, descending]) {
    const firstMissing = values.indexOf(null);
    assert.ok(values.slice(firstMissing).every(value => value === null));
  }
  assert.ok(ascending[0] <= ascending[1] && descending[0] >= descending[1]);
  const byMaterial = sortFacts(facts, "material", "asc");
  assert.ok(byMaterial.every((row, index) => index === 0 || byMaterial[index - 1].material.localeCompare(row.material) <= 0));
  assert.deepEqual(sortFacts(facts, "material", "asc").map(row => row.id), sortFacts(facts, "material", "asc").map(row => row.id));
});

test("CSV and JSON exports carry every field and neutralize spreadsheet formulas", () => {
  assert.equal(csvCell("=HYPERLINK(1)"), "'=HYPERLINK(1)");
  assert.equal(csvCell("a,b"), '"a,b"');
  assert.equal(csvCell('say "hi"'), '"say ""hi"""');
  assert.equal(csvCell(-1.5), "-1.5");
  assert.equal(csvCell(null), "");
  const csv = factsToCsv(facts.slice(0, 3));
  const lines = csv.trimEnd().split("\r\n");
  assert.equal(lines.length, 4);
  assert.equal(lines[0], EXPORT_FIELDS.map(([name]) => name).join(","));
  const json = JSON.parse(factsToJson(facts.slice(0, 3)));
  assert.equal(json.count, 3);
  assert.deepEqual(Object.keys(json.records[0]), EXPORT_FIELDS.map(([name]) => name));
  assert.match(json.records[0].record_json, /^https:\/\/aroundpeking\.github\.io\/LibRPA-database\/data\/calculations\/.+\/record\.json$/);
});

test("explorer URL state round-trips and rejects impossible values", () => {
  const known = ["Ga", "As", "Si"];
  const state = readExplorerParams(new URLSearchParams("q=GaAs&el=Ga,As,Xx&elmode=only&dim=3d&sw=abacus&type=band&methods=GW,SOC,BAD&gmin=1&gmax=2.5&inputs=available&sort=ks&dir=asc&page=2&size=50"), known);
  assert.deepEqual(state.elements, ["Ga", "As"]);
  assert.deepEqual(state.methods, ["GW", "SOC"]);
  assert.equal(state.elementMode, "only");
  assert.equal(state.gapMin, 1);
  assert.equal(state.gapMax, 2.5);
  assert.equal(state.size, 50);
  assert.deepEqual(readExplorerParams(writeExplorerParams(state), known), state);
  const legacy = readExplorerParams(new URLSearchParams("sort=result&element=Si&size=7&page=-3&gmin=abc"), known);
  assert.equal(legacy.sort, "gw");
  assert.equal(legacy.dir, "desc");
  assert.deepEqual(legacy.elements, ["Si"]);
  assert.equal(legacy.size, 20);
  assert.equal(legacy.page, 1);
  assert.equal(legacy.gapMin, null);
  assert.equal(writeExplorerParams(readExplorerParams(new URLSearchParams(""), known)).toString(), "");
});

test("table header and rows follow the visible columns", () => {
  const columns = visibleColumns(DEFAULT_COLUMNS);
  assert.ok(columns[0].key === "material" && columns.every(column => column.fixed || DEFAULT_COLUMNS.includes(column.key)));
  assert.deepEqual(visibleColumns([]).map(column => column.key), ["material"]);
  const header = renderHeader(columns, "ks", "desc");
  assert.match(header, /aria-sort="descending"[^>]*><button type="button" class="sort-button is-active" data-sort-key="ks">/);
  assert.equal((header.match(/aria-sort="ascending"/g) || []).length, 0);
  const row = renderMaterialRow(facts.find(item => item.id === "mos2_ws2-table-gw"), visibleColumns(COLUMNS.map(column => column.key)));
  assert.match(row, /class="material-link" href="#\/material\/mos2_ws2-table-gw">MoS<sub>2<\/sub>-WS<sub>2<\/sub><\/a>/);
  assert.match(row, /<span class="element-chip">W<\/span>/);
  // The whole row is the click target now; the material cell still carries a
  // real link so keyboard and middle-click keep working.
  assert.match(row, /<tr class="material-row" data-href="#\/material\/mos2_ws2-table-gw">/);
  assert.doesNotMatch(row, /class="open-cell"/);
  assert.match(row, /<a class="material-link" href="#\/material\/mos2_ws2-table-gw">/);
  // The header must not reserve a column for an arrow that no longer exists.
  assert.equal((header.match(/<th scope="col"/g) || []).length, columns.length);
  assert.doesNotMatch(header, /Open record/);
});

test("record pages offer the MCP calls and record JSON for that record", () => {
  const band = catalog.calculations.find(record => record.id === "si-paper-all_kpath");
  const html = renderMaterial(band, catalog.basis_sets, catalog.calculations);
  assert.match(html, /<details class="api-box" id="record-api">/);
  assert.match(html, /get_material \{&quot;record_id&quot;: &quot;si-paper-all_kpath&quot;\}/);
  assert.match(html, /get_band_table \{&quot;record_id&quot;: &quot;si-paper-all_kpath&quot;, &quot;method&quot;: &quot;GW&quot;\}/);
  assert.match(html, /compare_gaps \{&quot;material&quot;: &quot;Si&quot;\}/);
  assert.match(html, /https:\/\/aroundpeking\.github\.io\/LibRPA-database\/data\/calculations\/3d\/Si\/si-paper-all_kpath\/record\.json/);
  assert.match(html, /data-section="record-api"/);
  assert.match(html, /class="copy-id" data-copy="si-paper-all_kpath"/);
  const rpa = catalog.calculations.find(record => record.record_type === "rpa_energy");
  const rpaHtml = renderMaterial(rpa, catalog.basis_sets, catalog.calculations);
  assert.doesNotMatch(rpaHtml, /get_band_table|compare_gaps/, "no band or gap calls for an RPA-energy record");
});

test("the API & agents page and llms.txt describe the read and write paths", () => {
  const index = read("index.html");
  const llms = readFileSync(new URL("../llms.txt", import.meta.url), "utf8");
  assert.match(index, /href="#\/agents" data-nav="agents">API &amp; agents</);
  assert.match(index, /<section id="agents-view" class="agents-view" hidden aria-labelledby="agents-title">/);
  assert.match(index, /\/plugin marketplace add AroundPeking\/LibRPA-database\n\/plugin install librpa-database@librpa/);
  assert.match(index, /href="\.\.\/llms\.txt"/);
  assert.match(llms, /^# LibRPA materials database\n\n> /);
  assert.match(llms, /\/plugin install librpa-database@librpa/);
  assert.match(llms, /not global fundamental gaps/);
  assert.match(read("app.js"), /if \(path === "#\/agents"\) \{ renderAgents\(\); return; \}/);
});
