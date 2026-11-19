import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildGapComparison, gapMethods, gapOverview } from '../database/gaps.mjs';
import { gapInventory, readGapParams, writeGapParams, binaryTransitionMetalOxide, selectedGapRecords } from '../database/gap-controls.mjs';

const load = path => JSON.parse(readFileSync(new URL(path, import.meta.url)));
const full = load('../database/data.json').calculations;
const light = load('../database/catalog/calculations.json').records;
const inventory = gapInventory(light);

test('shared gap links reproduce exact material and method selections; empty series stays empty', () => {
  const view = readGapParams(new URLSearchParams('x=material&material=Si&material=SiC&series=exx,g0w0'), inventory);
  assert.deepEqual(view.materials, ['Si', 'SiC']);
  assert.deepEqual(new Set(selectedGapRecords(inventory, view).map(r => r.material)), new Set(['Si', 'SiC']));
  assert.deepEqual(readGapParams(writeGapParams(view), inventory), view);
  view.methods = [];
  assert.deepEqual(readGapParams(writeGapParams(view), inventory).methods, []);
});

test('oxide shortcut is a defined composition filter, not a formula substring', () => {
  for (const [formula, expected] of [['NiO', true], ['Fe2O3', true], ['NiS', false], ['MgO', false], ['ZnO', false], ['LiNiO2', false]]) {
    assert.equal(binaryTransitionMetalOxide({ formula }), expected, formula);
  }
});

test('the lightweight listing and the full detail record use the same numbers and scopes', () => {
  const detailed = new Map(full.map(r => [r.id, r]));
  assert.equal(light.length, detailed.size);
  const methods = gapMethods(full).map(m => m.key);
  for (const record of light) {
    const original = detailed.get(record.id);
    assert.deepEqual(gapOverview(record), gapOverview(original), record.id);
    for (const axis of ['material','ks','experiment']) {
      const compare = r => buildGapComparison([r], {axis, methods}).rows.map(({record: _r, ...row}) => row);
      assert.deepEqual(compare(record), compare(original), `${axis}:${record.id}`);
    }
  }
});
