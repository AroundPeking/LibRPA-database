import test from "node:test";
import assert from "node:assert/strict";
import {
  getPropertyCategories,
  renderPropertyPanel,
  renderPropertyTabs,
} from "../database/properties.mjs";

test("provides the six initial property categories", () => {
  assert.deepEqual(getPropertyCategories([]).map(item => item.slug), [
    "electronic", "topological", "optical", "magnetic", "structural", "other",
  ]);
});

test("renders a numeric property with method, unit, status, and evidence", () => {
  const property = {
    category: "electronic", key: "band_gap", label: "Band gap", method: "G0W0",
    value: 2.14, unit: "eV", status: "reported", evidence: ["data/case/GW_bands.dat"],
  };
  const panel = renderPropertyPanel([property], "electronic");
  assert.match(panel, /Band gap/);
  assert.match(panel, /G0W0/);
  assert.match(panel, /2\.14/);
  assert.match(panel, /eV/);
  assert.match(panel, /reported/i);
  assert.match(panel, /\.\.\/data\/case\/GW_bands\.dat/);
});

test("adds contributed categories and escapes their displayed labels", () => {
  const categories = getPropertyCategories([{ category: "berry_phase", label: "Polarization" }]);
  assert.deepEqual(categories.at(-1), { slug: "berry_phase", label: "Berry phase" });
  assert.match(renderPropertyTabs([{ category: "<custom>" }], "electronic"), /&lt;custom&gt;/);
});

test("shows an empty topology category without inventing a value", () => {
  const panel = renderPropertyPanel([], "topological");
  assert.match(panel, /No results reported/);
  assert.match(panel, /CONTRIBUTING\.md/);
  assert.doesNotMatch(panel, /\b(?:0|1|2)\b/);
});

test("internal failed properties are omitted from the formal database view", () => {
  const panel = renderPropertyPanel([{ category: "electronic", label: "Internal gate", method: "GW", status: "failed", value: null }], "electronic");
  assert.match(panel, /No results reported/);
  assert.doesNotMatch(panel, /Internal gate|Failed/);
});
