// Cross-material gap overview: one row per calculation that lists a gap value.
import { esc, bandGap, recordType, atomCount, restrictedGap, sampledGridGap, workflowLabel } from "./records.mjs";

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
    if (run?.scheduler_state !== "COMPLETED" || !run.gap?.g0w0_available
        || typeof run.gap.g0w0_value !== "number" || !Number.isFinite(run.gap.g0w0_value)) return null;
    const ks = run.gap.ks_available && Number.isFinite(run.gap.ks_value) ? run.gap.ks_value : null;
    return { ks, exx: null, gw: run.gap.g0w0_value, scope: "sampled" };
  }
  const ks = bandGap(record, "DFT");
  const exx = bandGap(record, "EXX");
  const gw = bandGap(record, "GW");
  if (ks === null && exx === null && gw === null) return null;
  return { ks, exx, gw, scope: restrictedGap(record) ? "path" : "band" };
}

const scopeNote = { sampled: " · sampled Γ", path: " · path-resolved" };

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
    return `<tr class="gap-row"><th scope="row"><a class="material-link" href="${url}">${esc(record.material)}</a><span class="table-description">${esc(record.id)}${scopeNote[gaps.scope] || ""}</span></th><td><span class="record-type-tag">${esc(workflowLabel(record))}</span></td><td><span class="dimension-tag">${esc(record.dimension.toUpperCase())}</span>${atoms ? `<span class="table-description">${atoms} atoms</span>` : ""}</td><td class="numeric">${value(gaps.ks)}</td><td class="numeric">${value(gaps.exx)}</td><td class="numeric gap-cell"><div class="gw-line"><strong class="gw-value">${value(gaps.gw)}</strong>${bar}</div></td><td class="open-cell"><a href="${url}" aria-label="Open ${esc(record.material)} calculation ${esc(record.id)}">↗</a></td></tr>`;
  }).join("");
  return `<div class="table-wrap" tabindex="0" role="region" aria-label="Gap overview"><table class="gap-table"><caption class="sr-only">Recorded band gap values across materials</caption><thead><tr><th scope="col">Material</th><th scope="col">Software</th><th scope="col">Scale</th><th scope="col">PBE / KS</th><th scope="col">EXX</th><th scope="col">GW</th><th scope="col"><span class="sr-only">Open record</span></th></tr></thead><tbody>${body}</tbody></table></div>`;
}
