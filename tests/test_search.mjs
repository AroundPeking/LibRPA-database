import test from "node:test";
import assert from "node:assert/strict";
import { matchesSearch, normalizeSearchText } from "../database/search.mjs";

test("matches every query token across punctuation-separated text", () => {
  const record = { material: "MoS2", method: "G0W0", value: 2.14 };
  assert.equal(matchesSearch(record, "mos2 G0W0"), true);
  assert.equal(matchesSearch(record, "mos2 missing"), false);
});

test("normalizes Unicode formula subscripts and dash variants", () => {
  assert.equal(normalizeSearchText("MoS₂ – GW"), "mos2 gw");
  assert.equal(matchesSearch({ formula: "MoS2" }, "MoS₂"), true);
});

test("searches nested method, commit, file, and property metadata", () => {
  const record = {
    software: { librpa: { commit: "abc123" } },
    files: { results: [{ path: "data/results/GW_bands.dat" }] },
    properties: [{ category: "topological", label: "Z2 invariant", value: 1 }],
  };
  assert.equal(matchesSearch(record, "abc123 topological"), true);
  assert.equal(matchesSearch(record, "GW_bands.dat Z2"), true);
  assert.equal(matchesSearch(record, "GW_bands.dat absent"), false);
});

test("basis records can match terms from their linked calculations", () => {
  const record = {
    set: { id: "Mo-GTH", element: "Mo", family: "GTH" },
    linked_calculations: [{ material: "MoS2", properties: [{ method: "G0W0" }] }],
  };
  assert.equal(matchesSearch(record, "MoS₂ G0W0"), true);
});

test("an empty query matches every record", () => {
  assert.equal(matchesSearch({}, "  — "), true);
});
