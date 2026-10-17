import test from "node:test";
import assert from "node:assert/strict";
import { matchesSearch, materialSearchText, basisSearchText, normalizeSearchText } from "../database/search.mjs";

test("matches every query token across punctuation-separated text", () => {
  assert.equal(matchesSearch("MoS2 G0W0 2.14", "mos2 G0W0"), true);
  assert.equal(matchesSearch("MoS2 G0W0", "mos2 missing"), false);
});

test("normalizes Unicode formula subscripts and dash variants", () => {
  assert.equal(normalizeSearchText("MoS₂ – GW"), "mos2 gw");
  assert.equal(matchesSearch(materialSearchText({ formula: "MoS2" }), "MoS₂"), true);
});

test("material search text carries ids, commits, and method chips", () => {
  const text = materialSearchText({ id: "si-paper-gw", material: "Si", functional: "PBE", source: { commit: "abc123" } });
  assert.equal(matchesSearch(text, "abc123 si-paper-gw"), true);
  assert.equal(matchesSearch(text, "pbe"), true);
  assert.equal(matchesSearch(text, "pbe absent"), false);
});

test("method keywords match whole words, other tokens stay substrings", () => {
  assert.equal(matchesSearch("gaas paper gw xsoc 1e 10", "soc"), false, "no substring hit inside xsoc");
  assert.equal(matchesSearch("gaas soc pbe exx gw", "soc"), true);
  assert.equal(matchesSearch("nio spin", "spin"), true);
  assert.equal(matchesSearch("silicene", "si"), true, "element-like tokens keep substring matching");
  assert.equal(matchesSearch("si abacus delta-sternheimer lib rpa", "delta-st"), true, "the hyphenated Delta-ST query finds Delta-Sternheimer labels");
  assert.equal(matchesSearch("si abacus delta-sternheimer lib rpa", "sternheimer"), true);
  assert.equal(matchesSearch("si abacus gw", "delta"), false, "delta stays a whole-word method keyword");
});

test("basis records can match terms from their linked calculations", () => {
  const text = basisSearchText({ id: "Mo-GTH", element: "Mo", family: "GTH" }, [{ material: "MoS2", properties: [{ method: "G0W0" }] }]);
  assert.equal(matchesSearch(text, "MoS₂ GTH"), true);
  assert.equal(matchesSearch(text, "MoS₂ absent"), false);
});

test("blank queries match everything; punctuation-only queries match nothing", () => {
  assert.equal(matchesSearch("anything", ""), true);
  assert.equal(matchesSearch("anything", "   "), true);
  assert.equal(matchesSearch("anything", " — "), false);
  assert.equal(matchesSearch("anything", "zz..zz!?"), false);
});
