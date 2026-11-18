// Cross-material gap overview: one row per calculation that lists a gap value.
import { esc, bandGap, recordType, atomCount, restrictedGap, sampledGridGap, workflowLabel, workflowFrontend } from "./records.mjs";

export function gapOverview(record) {
  const type = recordType(record);
  if (type === "rpa_energy") return null;
  if (type === "large_system_gw") {
    const pbe = sampledGridGap(record, "PBE");
    const gw = sampledGridGap(record, "G0W0");
    if (!pbe && !gw) return null;
    return { ks: pbe?.value ?? null, exx: null, gw: gw?.value ?? null, scope: "sampled" };
  }
  if (type === "reader_conversion") {
    const run = record.associated_gw_run;
    if (run?.scheduler_state !== "COMPLETED") return null;
    const ks = run.gap?.ks_available && typeof run.gap.ks_value === "number" && Number.isFinite(run.gap.ks_value) ? run.gap.ks_value : null;
    const gw = run.gap?.g0w0_available && typeof run.gap.g0w0_value === "number" && Number.isFinite(run.gap.g0w0_value) ? run.gap.g0w0_value : null;
    if (ks === null && gw === null) return null;
    return { ks, exx: null, gw, scope: "sampled" };
  }
  const ks = bandGap(record, "DFT");
  const exx = bandGap(record, "EXX");
  const gw = bandGap(record, "GW");
  if (ks === null && exx === null && gw === null) return null;
  return { ks, exx, gw, scope: restrictedGap(record) ? "path" : "band" };
}

const scopeNote = { sampled: " · sampled Γ" };

function niceAxis(max) {
  const step = [0.5, 1, 2, 2.5, 5, 10].find(candidate => max / candidate <= 7) || 20;
  const top = Math.max(step, Math.ceil(max / step) * step);
  const ticks = [];
  for (let value = 0; value <= top + 1e-9; value += step) ticks.push(Number(value.toFixed(6)));
  return { top, ticks };
}

// GW against PBE/KS for every record that lists both: the parity line shows
// the quasiparticle correction at a glance. Each point keeps its record's own
// gap definition; the table below remains the complete, exact view.
export function renderGapChart(calculations, { width = 760 } = {}) {
  const points = calculations
    .map(record => ({ record, gaps: gapOverview(record) }))
    .filter(({ gaps }) => gaps && gaps.ks !== null && gaps.gw !== null);
  if (!points.length) return "";
  const height = Math.round(Math.min(420, Math.max(260, width * 0.42))), left = 58, right = 20, top = 16, bottom = 52;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const xAxis = niceAxis(Math.max(...points.map(point => point.gaps.ks)));
  const yAxis = niceAxis(Math.max(...points.map(point => point.gaps.gw)));
  const x = value => left + (value / xAxis.top) * plotWidth;
  const y = value => top + plotHeight - (value / yAxis.top) * plotHeight;
  const parity = Math.min(xAxis.top, yAxis.top);
  const grid = yAxis.ticks.map(tick => `<line class="chart-grid" x1="${left}" x2="${width - right}" y1="${y(tick).toFixed(1)}" y2="${y(tick).toFixed(1)}"/><text class="chart-tick" x="${left - 10}" y="${(y(tick) + 4).toFixed(1)}" text-anchor="end">${tick}</text>`).join("")
    + xAxis.ticks.map(tick => `<text class="chart-tick" x="${x(tick).toFixed(1)}" y="${height - bottom + 20}" text-anchor="middle">${tick}</text>`).join("");
  // FHI-aims points are the minority; drawing them last keeps them visible
  // where they coincide with an ABACUS point for the same material.
  const order = record => workflowFrontend(record) === "fhi_aims" ? 1 : 0;
  const dots = points
    .sort((a, b) => order(a.record) - order(b.record) || a.record.id.localeCompare(b.record.id))
    .map(({ record, gaps }) => {
      const frontend = workflowFrontend(record);
      const precision = gaps.scope === "sampled" ? 5 : 3;
      const label = `${record.material} (${record.id}): GW ${gaps.gw.toFixed(precision)} eV, PBE / KS ${gaps.ks.toFixed(precision)} eV, ${workflowLabel(record)}`;
      const cx = x(gaps.ks).toFixed(1), cy = y(gaps.gw).toFixed(1);
      return `<a class="gap-point" href="#/material/${encodeURIComponent(record.id)}" data-frontend="${frontend}" data-gw="${gaps.gw.toFixed(precision)}" data-ks="${gaps.ks.toFixed(precision)}" data-material="${esc(record.material)}" data-id="${esc(record.id)}" data-workflow="${esc(workflowLabel(record))}" aria-label="${esc(label)}"><circle class="gap-hit" cx="${cx}" cy="${cy}" r="12"/><circle class="gap-dot" cx="${cx}" cy="${cy}" r="5"/></a>`;
    }).join("");
  const svg = `<svg class="gap-scatter" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="group" aria-label="GW gap against PBE / KS gap for ${points.length} records">${grid}<line class="chart-axis" x1="${left}" x2="${width - right}" y1="${y(0)}" y2="${y(0)}"/><line class="chart-axis" x1="${left}" x2="${left}" y1="${top}" y2="${y(0)}"/><line class="chart-parity" x1="${x(0)}" y1="${y(0)}" x2="${x(parity).toFixed(1)}" y2="${y(parity).toFixed(1)}"/><text class="chart-label" x="${left + plotWidth / 2}" y="${height - 10}" text-anchor="middle">PBE / KS gap (eV)</text><text class="chart-label" transform="translate(16 ${top + plotHeight / 2}) rotate(-90)" text-anchor="middle">GW gap (eV)</text>${dots}</svg>`;
  return `<figure class="chart-card"><figcaption><div><h3>GW against PBE / KS gap</h3><p>${points.length} records list both values. Points above the dashed parity line have a GW gap larger than the mean-field gap; each keeps its record's own definition (band path, sampled Γ, or paper value).</p></div><ul class="chart-legend"><li><span class="legend-dot" data-frontend="abacus" aria-hidden="true"></span>ABACUS workflows</li><li><span class="legend-dot" data-frontend="fhi_aims" aria-hidden="true"></span>FHI-aims workflows</li><li><span class="legend-line" aria-hidden="true"></span>GW = PBE / KS</li></ul></figcaption><div class="chart-frame">${svg}<div class="chart-tooltip" role="status" hidden></div></div></figure>`;
}

// Value-first hover and focus readout for the scatter points. Labels come from
// data attributes and are written with textContent only.
export function installGapChartTooltip(container) {
  const show = point => {
    const tooltip = container.querySelector(".chart-tooltip");
    const frame = container.querySelector(".chart-frame");
    if (!tooltip || !frame) return;
    tooltip.replaceChildren();
    const rows = [["GW", point.dataset.gw], ["PBE / KS", point.dataset.ks]];
    for (const [name, value] of rows) {
      const row = document.createElement("p");
      const strong = document.createElement("strong");
      strong.textContent = `${value} eV`;
      row.append(strong, document.createTextNode(` ${name}`));
      tooltip.append(row);
    }
    const title = document.createElement("p");
    title.className = "chart-tooltip-name";
    title.textContent = `${point.dataset.material} · ${point.dataset.workflow}`;
    const id = document.createElement("p");
    id.className = "chart-tooltip-id";
    id.textContent = point.dataset.id;
    tooltip.append(title, id);
    const dot = point.querySelector(".gap-dot").getBoundingClientRect();
    const box = frame.getBoundingClientRect();
    tooltip.hidden = false;
    const leftEdge = Math.min(Math.max(8, dot.left - box.left + 14), box.width - tooltip.offsetWidth - 8);
    tooltip.style.left = `${leftEdge}px`;
    tooltip.style.top = `${Math.max(8, dot.top - box.top - tooltip.offsetHeight - 10)}px`;
  };
  const hide = () => { const tooltip = container.querySelector(".chart-tooltip"); if (tooltip) tooltip.hidden = true; };
  container.addEventListener("pointerover", event => { const point = event.target.closest?.(".gap-point"); if (point) show(point); });
  container.addEventListener("pointerout", event => { if (event.target.closest?.(".gap-point") && !event.relatedTarget?.closest?.(".gap-point")) hide(); });
  container.addEventListener("focusin", event => { const point = event.target.closest?.(".gap-point"); if (point) show(point); });
  container.addEventListener("focusout", hide);
}

export function renderGapOverview(calculations, sort = "result") {
  const rows = calculations
    .map(record => ({ record, gaps: gapOverview(record) }))
    .filter(row => row.gaps)
    .sort((a, b) => sort === "material"
      ? a.record.material.localeCompare(b.record.material) || a.record.id.localeCompare(b.record.id)
      : (b.gaps.gw ?? -Infinity) - (a.gaps.gw ?? -Infinity) || a.record.material.localeCompare(b.record.material));
  const maxGw = Math.max(0, ...rows.map(row => row.gaps.gw).filter(value => value !== null));
  const body = rows.map(({ record, gaps }) => {
    const url = `#/material/${encodeURIComponent(record.id)}`;
    const precision = gaps.scope === "sampled" ? 5 : 3;
    const value = gapValue => gapValue === null ? '<span class="not-reported">—</span>' : gapValue.toFixed(precision);
    const bar = gaps.gw === null ? "" : `<span class="gap-bar" aria-hidden="true"><i style="width:${Math.max(3, Math.round(gaps.gw / (maxGw || 1) * 100))}%"></i></span>`;
    const atoms = atomCount(record);
    return `<tr class="gap-row"><th scope="row"><a class="material-link" href="${url}">${esc(record.material)}</a><span class="table-description">${esc(record.id)}${scopeNote[gaps.scope] || ""}</span></th><td data-label="Software"><span class="record-type-tag">${esc(workflowLabel(record))}</span></td><td data-label="Scale"><span class="dimension-tag">${esc(record.dimension.toUpperCase())}</span>${atoms ? `<span class="table-description">${atoms} atoms</span>` : ""}</td><td class="numeric" data-label="PBE / KS">${value(gaps.ks)}</td><td class="numeric" data-label="EXX">${value(gaps.exx)}</td><td class="numeric gap-cell" data-label="GW"><div class="gw-line"><strong class="gw-value">${value(gaps.gw)}</strong>${bar}</div></td><td class="open-cell"><a href="${url}" aria-label="Open ${esc(record.material)} calculation ${esc(record.id)}">↗</a></td></tr>`;
  }).join("");
  return `<div class="table-wrap" tabindex="0" role="region" aria-label="Gap overview"><table class="gap-table"><caption class="sr-only">Recorded band gap values across materials</caption><thead><tr><th scope="col">Material</th><th scope="col">Software</th><th scope="col">Scale</th><th scope="col">PBE / KS</th><th scope="col">EXX</th><th scope="col">GW</th><th scope="col"><span class="sr-only">Open record</span></th></tr></thead><tbody>${body}</tbody></table></div>`;
}
