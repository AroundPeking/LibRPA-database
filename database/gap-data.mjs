// Read one record at a time. Never join by formula, frontend, or structure.
import { paperGap, recordType, structureFingerprint } from './records.mjs';

const METHODS = [
  ['ks', 'DFT / KS'], ['exx', 'EXX'], ['g0w0', 'G0W0'], ['gw', 'GW'],
  ['qsgw', 'QSGW'], ['dmft', 'DMFT'],
].map(([key, label]) => ({ key, label }));
const methodKeys = new Map([
  ...['PBE', 'PBESOL', 'KS', 'DFT', 'LDA', 'GGA', 'SCAN', 'HSE', 'HSE06'].map(name => [name, 'ks']),
  ['EXX', 'exx'], ['G0W0', 'g0w0'], ['GW', 'gw'], ['GW PATH', 'gw'], ['QSGW', 'qsgw'], ['DMFT', 'dmft'],
]);
const methodKey = name => methodKeys.get(String(name).toUpperCase());
const GAP_KEYS = new Set(['band_gap', 'sampled_path_gap_ev', 'path_gap_ev', 'sampled_path_gap', 'path_gap', 'sampled_grid_gap_ev']);
const text = value => typeof value === 'string' && !!value.trim();
const nonempty = value => Array.isArray(value) && value.some(text);
// Suppress binary tails in the readout; the unrounded number remains available
// in the model and the table's expandable provenance details.
const readout = value => String(Number(value.toPrecision(10)));

function propertyGap(p, record) {
  if (!['reported', 'validated'].includes(p.status) || !Number.isFinite(p.value) || p.unit !== 'eV') return null;
  const key = methodKey(p.method);
  if (!key || record.method_diagnostics?.some(d => methodKey(d.method) === key && d.status === 'rejected')) return null;
  // Future methods must have an explicit gap property, its own definition and evidence.
  if (['qsgw', 'dmft'].includes(key) && (!text(p.definition) || !nonempty(p.evidence))) return null;
  const isPath = /path/i.test(`${p.key} ${p.label || ''}`);
  const scope = p.key === 'sampled_grid_gap_ev' ? (record.workflow?.sampling_label || p.label || 'Sampled grid')
    : isPath ? (p.label || 'Sampled path') : (record.summary?.gap_definition?.includes('band-path') ? 'Selected band path' : p.label || 'Band gap');
  const actualMethod = key === 'ks' && ['KS', 'DFT'].includes(p.method) && text(record.functional) ? `${p.method} (${record.functional})` : p.method;
  const definition = p.definition || (key === 'g0w0' || key === 'gw' ? record.summary?.gap_definition : null);
  return { key, value: p.value, display: readout(p.value), scope: key === 'ks' ? `${actualMethod} · ${scope}` : scope, definition,
    observable: `property:${p.key}:${p.method}`, source: `${actualMethod} · ${p.key}`, evidence: p.evidence || [] };
}

function computedGaps(record) {
  const type = recordType(record), gaps = new Map();
  if (type === 'rpa_energy') return gaps;
  if (type === 'reader_conversion') {
    const run = record.associated_gw_run;
    if (run?.scheduler_state !== 'COMPLETED' || run.gap?.unit !== 'eV') return gaps;
    for (const key of ['ks', 'g0w0']) {
      const value = run.gap[`${key}_value`];
      if (run.gap[`${key}_available`] !== true || !Number.isFinite(value)) continue;
      const matching = record.properties?.find(p => p.key === 'sampled_grid_gap_ev' && methodKey(p.method) === key && p.value === value);
      gaps.set(key, { key, value, display: String(value), scope: matching?.label || 'Associated run · sampled grid', definition: matching?.definition || run.gap.reason,
        observable: `associated:${key}`, source: 'Associated completed GW run' });
    }
    return gaps;
  }
  const candidates = new Map();
  for (const p of record.properties || []) {
    if (p.category !== 'electronic' || !GAP_KEYS.has(p.key) || (type === 'large_system_gw' && p.key !== 'sampled_grid_gap_ev')) continue;
    const key = methodKey(p.method);
    if (!key) continue;
    // Including failed duplicates in the ambiguity check prevents silent substitution.
    candidates.set(key, candidates.has(key) ? null : propertyGap(p, record));
  }
  for (const [key, datum] of candidates) if (datum) gaps.set(key, datum);
  // The retained paper main columns are computed numbers, never experiments.
  // The source boundary and precision travel with each chosen number (EXX is usually archive-only).
  for (const method of ['DFT', 'EXX', 'GW']) {
    const p = paperGap(record, method);
    if (!p) continue;
    if (method === 'GW' && /\b(?:QSGW|DMFT|scGW|evGW)\b/i.test(p.column)) continue; // Never relabel a more specific method as generic GW.
    const key = method === 'GW' && /\bG0W0\b/i.test(p.column) ? 'g0w0' : methodKey(method);
    if (method === 'GW') {
      // A generic archive/paper label does not establish a second GW variant.
      gaps.delete('gw');
      gaps.delete('g0w0');
    }
    const { table, pdf_page: page } = record.paper_values.source;
    const caveat = record.scientific_scope?.original_status || (/raw[- ]band/i.test(record.summary?.observable || '') && method === 'GW' ? record.summary.observable : '');
    gaps.set(key, { key, value: p.value, display: p.value.toFixed(p.precision), scope: `Paper Table ${table}${caveat ? ` · ${caveat}` : ''}`, definition: p.scope,
      source: `${p.column} · Table ${table}, p. ${page}`, observable: `paper:${method}` });
  }
  return gaps;
}

export function gapMethods(calculations) {
  const present = new Set(calculations.flatMap(record => [...computedGaps(record).keys()]));
  return METHODS.filter(({ key }) => present.has(key)).map(method => ({ ...method }));
}
export function defaultGapMethods(methods) {
  const keys = methods.map(m => m.key), gw = keys.filter(k => k === 'g0w0' || k === 'gw');
  return gw.length ? gw : keys.filter(k => k !== 'ks').slice(0, 1);
}

function sourceLink(source) {
  if (!text(source?.citation) || !text(source.locator)) return null;
  if (/^10\.\d{4,9}\/\S+$/i.test(source.doi || '')) return `https://doi.org/${source.doi}`;
  try {
    const url = new URL(source.url);
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

// Opt-in curated measurement (none in the current catalog). Compatibility is an
// attestation for this precise computed observable, not a material-level fact.
function experiment(record) {
  const exp = record.experimental_gap;
  if (!exp) return { reason: 'No experimental gap supplied.' };
  const href = sourceLink(exp.source);
  if (exp.unit !== 'eV' || !Number.isFinite(exp.value) || !text(exp.definition) || !href)
    return { reason: 'Experimental value, gap definition, or source incomplete.' };
  const c = exp.compatibility, fp = structureFingerprint(record);
  if (!text(record.id) || c?.record_id !== record.id || !fp || c.structure_sha256 !== fp || !text(c.structure_note))
    return { reason: 'Record / structure compatibility not established.' };
  return { value: exp.value, display: String(exp.value), definition: exp.definition, source: exp.source, href, compatibility: c };
}

export function buildGapComparison(calculations, { axis = 'ks', methods: requested } = {}) {
  if (!['ks', 'material', 'experiment'].includes(axis)) throw new RangeError('Unknown gap axis');
  const inputs = calculations.map(record => ({ record, gaps: computedGaps(record) }));
  const present = new Set(inputs.flatMap(({ gaps }) => [...gaps.keys()]));
  const available = METHODS.filter(m => present.has(m.key) && !(axis === 'ks' && m.key === 'ks'));
  const keys = requested ?? defaultGapMethods(available);
  const methods = available.filter(m => keys.includes(m.key));
  const axisLabel = { ks: 'DFT / KS gap', experiment: 'Experimental gap', material: 'Material' }[axis];
  const points = [], rows = [];
  for (const { record, gaps } of inputs) {
    if (!methods.some(m => gaps.has(m.key))) continue;
    const reference = axis === 'ks' ? gaps.get('ks') : axis === 'experiment' ? experiment(record) : null;
    const values = {}, issues = {}, paired = [];
    for (const m of methods) {
      const datum = gaps.get(m.key);
      if (!datum) continue;
      values[m.key] = datum;
      let reason;
      if (axis === 'ks' && !reference) reason = 'No same-record DFT / KS gap.';
      if (axis === 'ks' && record.scientific_scope?.methods_are_separate_producers && !(reference?.observable.startsWith('paper:') && datum.observable.startsWith('paper:')))
        reason = 'Archive producers are not matched.';
      if (axis === 'experiment') {
        const match = reference.compatibility?.methods?.[m.key];
        if (reference.reason) reason = reference.reason;
        else if (!text(datum.definition)) reason = 'Computed gap definition not documented.';
        else if (match?.compatible !== true || match.observable !== datum.observable || !text(match.reason)) reason = 'No explicit match to this computed observable.';
      }
      if (reason) issues[m.key] = reason;
      else {
        paired.push(m.key);
        points.push({ record, method: m, x: axis === 'material' ? record.material : reference.value, y: datum.value, reference, datum });
      }
    }
    rows.push({ record, reference, values, issues, paired });
  }
  const plottedRecords = rows.filter(row => row.paired.length).length;
  return { axis, axisLabel, methods, rows, points, counts: { rows: rows.length, points: points.length, plottedRecords, contextRecords: rows.length - plottedRecords } };
}
