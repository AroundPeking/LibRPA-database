import { esc, bandGap, recordType, atomCount, restrictedGap, sampledGridGap, workflowLabel, workflowFrontend } from './records.mjs';
import { buildGapComparison } from './gap-data.mjs';
export { buildGapComparison, gapMethods, defaultGapMethods } from './gap-data.mjs';

// Legacy API shared by the explorer and MCP catalog. New comparisons distinguish
// individual GW variants and keep provenance per value, not per record.
export function gapOverview(record) {
  const type = recordType(record);
  if (type === 'rpa_energy') return null;
  if (type === 'large_system_gw') {
    const pbe = sampledGridGap(record, 'PBE'), gw = sampledGridGap(record, 'G0W0');
    if (!pbe && !gw) return null;
    return { ks: pbe?.value ?? null, exx: null, gw: gw?.value ?? null, scope: 'sampled' };
  }
  if (type === 'reader_conversion') {
    const run = record.associated_gw_run;
    if (run?.scheduler_state !== 'COMPLETED') return null;
    const ks = run.gap?.ks_available && Number.isFinite(run.gap.ks_value) ? run.gap.ks_value : null;
    const gw = run.gap?.g0w0_available && Number.isFinite(run.gap.g0w0_value) ? run.gap.g0w0_value : null;
    if (ks === null && gw === null) return null;
    return { ks, exx: null, gw, scope: 'sampled' };
  }
  const ks = bandGap(record, 'DFT'), exx = bandGap(record, 'EXX'), gw = bandGap(record, 'GW');
  if (ks === null && exx === null && gw === null) return null;
  return { ks, exx, gw, scope: restrictedGap(record) ? 'path' : 'band' };
}

const route = record => `#/material/${encodeURIComponent(record.id)}`;
const format = n => Number(n.toPrecision(6));
function numericScale(values, start, end) {
  const min = Math.min(0, ...values), max = Math.max(0, ...values), raw = (max - min || 1) / 5;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 2.5, 5, 10].find(n => n * mag >= raw) || 10) * mag;
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step || (min < 0 ? 0 : step);
  const ticks = Array.from({ length: Math.round((hi - lo) / step) + 1 }, (_, i) => format(lo + i * step));
  return { lo, hi, ticks, at: n => start + (end - start) * ((n - lo) / (hi - lo)) };
}
function glyph(key) {
  if (key === 'ks') return '<rect class="gap-dot" x="-4.5" y="-4.5" width="9" height="9"/>';
  const path = { exx: 'M0 -6 6 0 0 6 -6 0Z', qsgw: 'M0 -6 6 5 -6 5Z', dmft: 'M-6 -4 6 -4 0 6Z', gw: 'M-5 -3 0 -6 5 -3 5 3 0 6 -5 3Z' }[key];
  return path ? `<path class="gap-dot" d="${path}"/>` : '<circle class="gap-dot" r="5"/>';
}
function emptyMessage(model) {
  if (!model.methods.length) return 'No computed series selected or available. Select a method with recorded gap values.';
  if (model.axis === 'experiment') return 'No compatible experimental pairs. A point needs a sourced measurement and an explicit match to this record, structure and computed gap. Available computed values remain in the table.';
  return 'No paired gaps for this selection. Try Material on the horizontal axis to see values without a same-record DFT / KS gap.';
}
export function renderGapChart(calculations, { width = 760, ...options } = {}) {
  const model = buildGapComparison(calculations, options);
  const { axis, axisLabel, methods, points, counts } = model;
  if (!points.length) return `<figure class="chart-card chart-empty"><figcaption><div><h3>No points to plot</h3><p>${emptyMessage(model)}</p></div></figcaption></figure>`;
  width = Math.max(240, Math.min(2400, Math.round(Number.isFinite(width) ? width : 760)));
  const height = Math.round(Math.min(420, Math.max(280, width * 0.44)));
  const categorical = axis === 'material', left = 58, right = width - 20, top = 20, bottom = height - (categorical ? 82 : 54);
  const y = numericScale(points.map(p => p.y), bottom, top);
  const categories = [...new Set(points.map(p => p.record.material))].sort((a, b) => a.localeCompare(b));
  const x = categorical ? null : numericScale(points.map(p => p.x), left, right);
  const band = (right - left) / categories.length;
  const categoryAt = name => left + band * (categories.indexOf(name) + 0.5);
  const line = (cls, x1, y1, x2, y2) => `<line class="${cls}" x1="${format(x1)}" y1="${format(y1)}" x2="${format(x2)}" y2="${format(y2)}"/>`;
  const tick = (value, xpos, ypos, anchor) => `<text class="chart-tick" x="${format(xpos)}" y="${format(ypos)}" text-anchor="${anchor}">${esc(value)}</text>`;
  const grid = y.ticks.map(t => line('chart-grid', left, y.at(t), right, y.at(t)) + tick(t, left - 8, y.at(t) + 4, 'end')).join('');
  const stride = Math.max(1, Math.ceil(48 / band));
  const xTicks = categorical ? categories.filter((_, i) => i % stride === 0).map(name => `<text class="chart-tick" transform="translate(${format(categoryAt(name))} ${bottom + 12}) rotate(-32)" text-anchor="end">${esc(name)}</text>`).join('') : x.ticks.map(t => tick(t, x.at(t), bottom + 18, 'middle')).join('');
  const parity = categorical ? '' : line('chart-parity', x.at(Math.max(x.lo, y.lo)), y.at(Math.max(x.lo, y.lo)), x.at(Math.min(x.hi, y.hi)), y.at(Math.min(x.hi, y.hi)));
  const dots = points.map(({ record, method, datum, reference, x: xv }) => {
    const cx = categorical ? categoryAt(xv) + (methods.indexOf(method) - (methods.length - 1) / 2) * Math.min(12, band / (methods.length + 1)) : x.at(xv);
    const refText = categorical ? record.material : `${reference.display} eV`;
    const label = `${record.material} (${record.id}), ${method.label}: ${datum.display} eV · ${datum.scope}; ${axisLabel}: ${refText}; ${workflowLabel(record)}`;
    return `<a class="gap-point" href="${route(record)}" aria-label="${esc(label)}" data-method="${method.key}" data-frontend="${workflowFrontend(record)}" data-series="${esc(method.label)}" data-y="${esc(datum.display)}" data-axis="${axisLabel}" data-x="${esc(refText)}" data-scope="${esc(datum.scope)}" data-id="${esc(record.id)}" data-material="${esc(record.material)}" data-workflow="${esc(workflowLabel(record))}"><g transform="translate(${format(cx)} ${format(y.at(datum.value))})"><circle class="gap-hit" r="12"/>${glyph(method.key)}</g></a>`;
  }).join('');
  const heading = categorical ? 'Computed gaps by material' : `Computed gaps against ${axisLabel}`;
  const ylabel = methods.length === 1 ? `${methods[0].label} gap` : 'Computed gap';
  const svg = `<svg class="gap-scatter" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="group" aria-label="${heading}: ${counts.points} points">${grid}${xTicks}${line('chart-axis', left, bottom, right, bottom)}${line('chart-axis', left, bottom, left, top)}${parity}<text class="chart-label" x="${(right + left) / 2}" y="${height - 8}" text-anchor="middle">${axisLabel}${categorical ? '' : ' (eV)'}</text><text class="chart-label" transform="translate(16 ${(top + bottom) / 2}) rotate(-90)" text-anchor="middle">${ylabel} (eV)</text>${dots}</svg>`;
  const legend = methods.map(m => `<li><svg class="gap-symbol" data-method="${m.key}" width="16" height="16" viewBox="-8 -8 16 16" aria-hidden="true">${glyph(m.key)}</svg>${m.label}</li>`).join('');
  const note = categorical ? 'Each point is one record and method, not a material average.' : 'Dashed line: equal gaps. Each point uses the reference and gap definition of its own record.';
  return `<figure class="chart-card"><figcaption><div><h3>${heading}</h3><p>${counts.points} point${counts.points === 1 ? '' : 's'} from ${counts.plottedRecords} record${counts.plottedRecords === 1 ? '' : 's'}. ${note}${categorical && stride > 1 ? ' Selected material labels shown; all points are identified in the table.' : ''}</p></div><ul class="chart-legend">${legend}</ul></figcaption><div class="chart-frame">${svg}<div class="chart-tooltip" role="status" hidden></div></div></figure>`;
}

export function installGapChartTooltip(container) {
  const show = point => {
    const tooltip = container.querySelector('.chart-tooltip'), frame = container.querySelector('.chart-frame');
    if (!tooltip || !frame) return;
    const d = point.dataset;
    tooltip.replaceChildren();
    const add = (tag, content, cls) => {
      const element = document.createElement(tag);
      element.textContent = content;
      if (cls) element.className = cls;
      tooltip.append(element);
    };
    add('strong', `${d.series}: ${d.y} eV`);
    add('p', `${d.axis}: ${d.x}`);
    add('p', `${d.material} · ${d.workflow}`, 'chart-tooltip-name');
    add('p', d.scope);
    add('p', d.id, 'chart-tooltip-id');
    tooltip.hidden = false;
    const dot = point.getBoundingClientRect(), box = frame.getBoundingClientRect();
    tooltip.style.left = `${Math.max(0, Math.min(dot.left - box.left + 16, box.width - tooltip.offsetWidth))}px`;
    tooltip.style.top = `${Math.max(0, dot.top - box.top - tooltip.offsetHeight - 4)}px`;
  };
  const hide = () => { const tooltip = container.querySelector('.chart-tooltip'); if (tooltip) tooltip.hidden = true; };
  for (const type of ['pointerover', 'focusin']) container.addEventListener(type, e => { const p = e.target.closest?.('.gap-point'); if (p) show(p); });
  for (const type of ['pointerout', 'focusout']) container.addEventListener(type, e => { if (!e.relatedTarget?.closest?.('.gap-point')) hide(); });
  container.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });
}

const missing = '<span class="not-reported">—</span>';
function exactValue(value, reason) {
  if (!value) return missing;
  const evidence = Array.isArray(value.evidence) ? value.evidence.filter(path => typeof path === 'string').map(path => path.split('/').at(-1)) : [];
  return `<strong>${esc(value.display)}</strong><details class="gap-meta"><summary>${esc(value.scope)}</summary><p>${esc(value.definition || 'No further definition supplied.')}</p><p>${esc(value.source)}</p>${evidence.length ? `<p>Record evidence: ${esc(evidence.join(', '))}</p>` : ''}${Number(value.display) !== value.value ? `<p>Stored value: ${esc(value.value)} eV</p>` : ''}</details>${reason ? `<span class="gap-scope">Not plotted: ${esc(reason)}</span>` : ''}`;
}
function refCell(row, model) {
  if (model.axis === 'material') return '';
  const r = row.reference;
  let body;
  if (model.axis === 'ks') body = exactValue(r);
  else if (!row.paired.length) body = `${missing}<span class="gap-scope">No compatible pair</span>`;
  else body = `<strong>${esc(r.display)}</strong><details class="gap-meta"><summary>${esc(r.definition)}</summary><p><a href="${esc(r.href)}">${esc(r.source.citation)}</a> · ${esc(r.source.locator)}</p><p>${esc(r.compatibility.structure_note)}</p>${row.paired.map(k => `<p>${esc(model.methods.find(m => m.key === k).label)}: ${esc(r.compatibility.methods[k].reason)}</p>`).join('')}</details>`;
  return `<td class="numeric" data-label="${model.axisLabel}">${body}</td>`;
}
export function renderGapOverview(calculations, sort = 'result', options = {}) {
  const model = buildGapComparison(calculations, options);
  const { rows, methods, axis, axisLabel } = model;
  if (!rows.length) return '<p class="chart-empty">No recorded gaps for the selected methods and records.</p>';
  const maxY = row => Math.max(...Object.values(row.values).map(d => d.value));
  rows.sort((a, b) => (sort === 'material' ? 0 : maxY(b) - maxY(a)) || a.record.material.localeCompare(b.record.material) || a.record.id.localeCompare(b.record.id));
  const body = rows.map(row => {
    const r = row.record, url = route(r), atoms = atomCount(r);
    const cells = methods.map(m => `<td class="numeric" data-label="${m.label}">${exactValue(row.values[m.key], row.issues[m.key])}</td>`).join('');
    return `<tr class="gap-row"><th scope="row"><a class="material-link" href="${url}">${esc(r.material)}</a><span class="table-description">${esc(r.id)}</span> <a class="gap-cite" href="${url}?cite=1" aria-label="Cite ${esc(r.id)}">Cite</a></th><td data-label="Software"><span class="record-type-tag">${esc(workflowLabel(r))}</span>${r.spin_orbit === true ? ' · SOC' : ''}${r.spin_polarized === true ? ' · spin-polarized' : ''}</td><td data-label="Scale"><span class="dimension-tag">${esc(r.dimension?.toUpperCase() || '—')}</span>${atoms ? `<span class="table-description">${atoms} atoms</span>` : ''}</td>${refCell(row, model)}${cells}</tr>`;
  }).join('');
  const headers = ['Material', 'Software', 'Scale', ...(axis === 'material' ? [] : [axisLabel]), ...methods.map(m => m.label)].map(h => `<th scope="col">${esc(h)}</th>`).join('');
  return `<div class="table-wrap" tabindex="0" role="region" aria-label="Exact gap values in eV"><table class="gap-table"><caption>Exact gap values (eV) · select a scope for its definition and source.</caption><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table></div>`;
}
