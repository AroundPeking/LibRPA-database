import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { gapOverview, gapMethods, defaultGapMethods, buildGapComparison, renderGapChart, renderGapOverview } from '../database/gaps.mjs';

const catalog = JSON.parse(readFileSync(new URL('../database/data.json', import.meta.url))).calculations;
const byId = id => catalog.find(r => r.id === id);
const keys = records => gapMethods(records).map(m => m.key);
const profile = (records, axis, methods) => buildGapComparison(records, { axis, methods });
const prop = (method, value, extra = {}) => ({ category: 'electronic', key: 'band_gap', status: 'reported', unit: 'eV', method, value, ...extra });
const fixture = (...properties) => ({ id: 'synthetic', material: 'Fixture', dimension: '3d', record_type: 'band', properties, structure_identity: { algorithm: 'cell-sites-v1', sha256: '1'.repeat(64) } });

// These are existing record values; no experimental numbers are hard-coded by the UI.
test('catalog exposes only recorded methods and computes coverage per selected record', () => {
  const records = [byId('nio-aims-gw-int'), byId('c2048-reader-v1-20260607')];
  assert.deepEqual(keys(records), ['ks', 'exx', 'g0w0']);
  assert.deepEqual(defaultGapMethods(gapMethods(records)), ['g0w0']);
  const baseline = profile(records, 'ks', ['g0w0']);
  assert.deepEqual(baseline.counts, { rows: 2, points: 1, plottedRecords: 1, contextRecords: 1 });
  const experiment = profile(records, 'experiment', keys(records));
  assert.equal(experiment.points.length, 0);
  assert.equal(experiment.counts.contextRecords, 2);
  assert.match(renderGapChart(records, { axis: 'experiment' }), /No compatible experimental pairs/);
  // New methods and future measured pairs may grow the catalog without rewriting this test.
  for (const axis of ['ks', 'experiment', 'material']) {
    const { rows, points, counts } = profile(catalog, axis, keys(catalog));
    assert.equal(counts.rows, counts.plottedRecords + counts.contextRecords);
    assert.equal(points.length, rows.reduce((total, row) => total + row.paired.length, 0));
    assert.equal(counts.plottedRecords, new Set(points.map(p => p.record.id)).size);
  }
});

test('NiO remains a single spin-polarized record with two sampled-path methods and no KS or experimental substitute', () => {
  const nio = byId('nio-aims-gw-int');
  const methods = keys([nio]);
  assert.deepEqual(methods, ['exx', 'g0w0']);
  const actual = profile([nio], 'material', methods);
  assert.deepEqual(actual.points.map(p => [p.method.key, p.x, p.y, p.datum.scope]), [
    ['exx', 'NiO', 14.40432, 'Sampled path band gap'], ['g0w0', 'NiO', 1.81713, 'Sampled path band gap'],
  ]);
  const chart = renderGapChart([nio], { axis: 'material', methods });
  assert.match(chart, /2 points from 1 record\./);
  assert.equal((chart.match(/class="gap-point"/g) || []).length, 2);
  assert.doesNotMatch(chart, /chart-parity/);
  const table = renderGapOverview([nio], 'material', { axis: 'experiment', methods: ['exx'] });
  assert.match(table, /14\.40432/);
  assert.doesNotMatch(table, /1\.81713/);
  assert.match(table, /href="#\/material\/nio-aims-gw-int\?cite=1"/);
  assert.match(table, /No experimental gap supplied/);
  const ksPeer = { ...fixture(prop('PBE', 0.5)), id: 'other-record', material: 'NiO', structure_identity: nio.structure_identity };
  assert.deepEqual(profile([nio, ksPeer], 'ks', methods).counts, { rows: 1, points: 0, plottedRecords: 0, contextRecords: 1 });
});

test('paper main-column precision and scope are per value; incompatible diagnostic EXX is not promoted', () => {
  const records = [byId('hbn-tzdp10-fgext-20261008'), byId('gete-table-gw'), byId('snse-table-gw')];
  const { rows } = profile(records, 'material', keys(records));
  assert.equal(rows[0].values.g0w0.display, '6.94183');
  assert.match(rows[0].values.g0w0.scope, /Paper Table I.*raw-band-5 frontier/);
  assert.equal(rows[0].values.exx.observable, 'property:sampled_path_gap_ev:EXX');
  assert.match(rows[0].values.exx.scope, /sampled path/i);
  for (const row of rows.slice(1)) assert.equal(row.values.exx, undefined);
  assert.equal(rows[1].values.g0w0.display, '1.38070');
  assert.equal(rows[1].values.ks.value, 0.86874);
  // A generic archive line is not a second method alongside the paper G0W0.
  const alias = structuredClone(records[0]); alias.properties.push(prop('GW', 0.75));
  assert.deepEqual(keys([alias]), ['ks', 'exx', 'g0w0']);
  alias.paper_values.values.GW.column = 'GW'; alias.properties.push(prop('G0W0', 0.75));
  assert.deepEqual(keys([alias]), ['ks', 'exx', 'gw']);
});

test('grid and reader scopes and independent availability survive comparison and legacy API', () => {
  const reader = structuredClone(byId('c2048-reader-v1-20260607'));
  assert.deepEqual(gapOverview(reader), { ks: 4.28728, exx: null, gw: 5.74313, scope: 'sampled' });
  for (const record of [reader, byId('c1024-gamma-g0w0-20260521')]) assert.match(profile([record], 'ks', ['g0w0']).points[0].datum.scope, /Γ|Gamma/);
  reader.associated_gw_run.gap.ks_available = false;
  assert.equal(profile([reader], 'ks', ['g0w0']).points.length, 0);
  assert.equal(profile([reader], 'material', ['ks', 'g0w0']).points.length, 1);
  reader.associated_gw_run.scheduler_state = 'FAILED';
  assert.deepEqual(keys([reader]), []);
});

test('future variants require their own explicit valid electronic gap, units, status, definition and evidence', () => {
  const evidence = { evidence: ['synthetic/results/gap.dat'], definition: 'Synthetic test path; not site data.' };
  const r = fixture(prop('LDA', 0.3), prop('QSGW', 1.65, evidence), prop('DMFT', 1.3, evidence), prop('GW', 1.27));
  const model = profile([r], 'ks', ['qsgw', 'dmft', 'gw', 'ks']);
  assert.deepEqual(model.points.map(p => [p.method.key, p.x, p.y]), [['gw', 0.3, 1.27], ['qsgw', 0.3, 1.65], ['dmft', 0.3, 1.3]]);
  assert.match(model.points[0].reference.scope, /LDA/);
  assert.deepEqual(keys([fixture(prop('QSGW', 1.3), prop('DMFT', 0, { ...evidence, status: 'failed' }), prop('EXX', Infinity), prop('GW+DMFT', 2, evidence), prop('KS', 0.5, { key: 'total_energy' }), prop('G0W0', 2, { unit: 'Ha' }))]), []);
  r.properties.push(prop('QSGW', 9, evidence));
  r.method_diagnostics = [{ method: 'DMFT', status: 'rejected' }];
  assert.deepEqual(keys([r]), ['ks', 'gw']);
  r.summary = { observable: 'test window', value: 5, dft_gap_ev: 2, unit: 'eV' }; r.properties = [];
  assert.deepEqual(keys([r]), []);
});

// Wholly synthetic fixture for a future curated entry, not an experimental measurement.
function experimentFixture() {
  const r = fixture(prop('PBE', 0.6), prop('G0W0', 1.2, { definition: 'Synthetic electronic gap.' }), prop('EXX', 3, { definition: 'Synthetic EXX gap.' }));
  r.experimental_gap = { value: 1.1, unit: 'eV', definition: 'Synthetic electronic gap', source: { citation: 'Test fixture only', locator: 'Test row A', url: 'https://example.invalid/test-fixture' },
    compatibility: { record_id: r.id, structure_sha256: r.structure_identity.sha256, structure_note: 'Synthetic phase/geometry match.', methods: { g0w0: { compatible: true, observable: 'property:band_gap:G0W0', reason: 'Synthetic same-transition measurement.' } } } };
  return r;
}
test('experiment axis requires an explicit per-method match to record, structure and observable', () => {
  const r = experimentFixture(), methods = ['exx', 'g0w0'];
  const model = profile([r], 'experiment', methods);
  assert.deepEqual(model.points.map(p => [p.method.key, p.x, p.y]), [['g0w0', 1.1, 1.2]]);
  assert.match(model.rows[0].issues.exx, /No explicit match/);
  assert.match(renderGapOverview([r], 'result', { axis: 'experiment', methods }), /https:\/\/example.invalid\/test-fixture/);
  assert.match(renderGapChart([r], { axis: 'experiment', methods }), /1 point from 1 record\./);
  for (const mutate of [
    r => { r.id = 'same-formula-different-run'; }, r => { r.structure_identity.sha256 = '2'.repeat(64); },
    r => { delete r.experimental_gap.compatibility.structure_note; }, r => { delete r.experimental_gap.definition; },
    r => { delete r.properties[1].definition; },
    r => { r.experimental_gap.value = null; }, r => { r.experimental_gap.unit = 'Ha'; },
    r => { delete r.experimental_gap.source.locator; }, r => { r.experimental_gap.source.url = 'javascript:foo'; },
    r => { r.experimental_gap.compatibility.methods.g0w0.observable = 'paper:GW'; }, r => { r.experimental_gap.compatibility.methods.g0w0.compatible = false; },
    r => { r.experimental_gap.compatibility.methods.g0w0.reason = ''; }, r => { r.experimental_gap = [r.experimental_gap, r.experimental_gap]; },
  ]) {
    const other = structuredClone(r); mutate(other);
    const m = profile([other], 'experiment', methods);
    assert.equal(m.points.length, 0, String(mutate));
    assert.equal(m.rows[0].values.g0w0.value, 1.2);
  }
  const doi = structuredClone(r); delete doi.experimental_gap.source.url; doi.experimental_gap.source.doi = '10.9999/test-only';
  assert.equal(profile([doi], 'experiment', ['g0w0']).rows[0].reference.href, 'https://doi.org/10.9999/test-only');
});

test('plot/table agree on active series; maxima sort by selected result; empty and escaped labels are safe', () => {
  const a = fixture(prop('GW', 2.2), prop('EXX', 3.2)); a.material = '<unsafe>'; a.id = 'test-a';
  const b = fixture(prop('GW', 3.1), prop('EXX', 1.2)); b.id = 'test-b';
  const options = { axis: 'material', methods: ['exx'] };
  for (const html of [renderGapOverview([b, a], 'result', options), renderGapChart([b, a], options)]) {
    assert.match(html, /&lt;unsafe&gt;/);
    assert.doesNotMatch(html, /<unsafe>|2\.2 eV|3\.1 eV/);
  }
  const table = renderGapOverview([b, a], 'result', options);
  assert.ok(table.indexOf('test-a') < table.indexOf('test-b'));
  const empty = { axis: 'material', methods: [] };
  assert.equal(profile([a], 'material', []).points.length, 0);
  assert.match(renderGapChart([a], empty), /No points to plot/);
  assert.match(renderGapOverview([a], 'result', empty), /No recorded gaps/);
  assert.match(renderGapChart([fixture(prop('KS', 0), prop('GW', -0.12))]), /class="chart-parity"/);
});
