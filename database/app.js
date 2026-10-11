const statusNames = {
  gw_validated: "Validated", gw_diagnostic: "Archived result", path_diagnostic: "Path review",
  pbe_only: "PBE only", generation_only: "Generation only", failed: "Failed gate", pending: "Pending",
  database_only: "Database only", review: "Under review", publishable: "Publishable", superseded: "Superseded", legacy_incomplete: "Legacy incomplete"
};
const state = { mode: "materials", calculations: [], sets: [], dimension: "all", status: "all", sort: "material", query: "" };
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const statusLabel = value => statusNames[value] || value || "Unclassified";
const pathOf = file => `../${encodeURI(file.path)}`;
const assetLink = file => `<a href="${pathOf(file)}">${esc(file.label || file.path.split("/").pop())}</a>`;
const allFiles = record => Object.entries(record.files || {}).flatMap(([kind, files]) => (files || []).map(file => ({ ...file, kind })));
const basisStatus = set => set.publication?.status || "database_only";
const gapValue = record => record.summary?.gw_gap_ev ?? record.summary?.value;

function textForCalculation(c) {
  return [c.material, c.formula, c.id, c.dimension, c.summary?.observable, c.summary?.notes, c.summary?.scope,
    ...(c.species || []).flatMap(s => [s.element, s.set_id]), ...(c.basis_candidates || []).flatMap(s => [s.element, s.set_id, s.scope])].join(" ").toLowerCase();
}
function searchMatch(value) { return !state.query || value.includes(state.query); }
function methodFiles(record) {
  const labels = new Set((record.files?.results || []).map(file => file.label || file.path));
  return ["DFT", "EXX", "GW"].filter(method => [...labels].some(label => new RegExp(method === "DFT" ? "KS|PBE|DFT" : method, "i").test(label)));
}
function linkedCalculations(set) {
  const explicit = new Set(set.publication?.calculation_ids || []);
  return state.calculations.filter(c => explicit.has(c.id) || (c.species || []).some(s => s.set_id === set.id) || (c.basis_candidates || []).some(s => s.set_id === set.id));
}
function filteredCalculations() {
  return state.calculations.filter(c => (state.dimension === "all" || c.dimension === state.dimension) && searchMatch(textForCalculation(c))).sort((a, b) => {
    if (state.sort === "gap") return (gapValue(b) ?? -Infinity) - (gapValue(a) ?? -Infinity) || a.material.localeCompare(b.material);
    if (state.sort === "status") return statusLabel(a.status).localeCompare(statusLabel(b.status)) || a.material.localeCompare(b.material);
    return a.material.localeCompare(b.material) || a.id.localeCompare(b.id);
  });
}
function filteredSets() {
  return state.sets.filter(set => {
    const linked = linkedCalculations(set);
    const text = [set.id, set.element, set.family, set.validation_scope, set.notes, basisStatus(set), ...linked.flatMap(c => [c.material, c.formula, c.id])].join(" ").toLowerCase();
    return (!state.query || text.includes(state.query)) && (state.status === "all" || basisStatus(set) === state.status);
  }).sort((a, b) => state.sort === "element" ? a.element.localeCompare(b.element) || a.id.localeCompare(b.id) : state.sort === "status" ? statusLabel(basisStatus(a)).localeCompare(statusLabel(basisStatus(b))) || a.id.localeCompare(b.id) : a.element.localeCompare(b.element) || a.id.localeCompare(b.id));
}
function fileCount(record, group) { return (record.files?.[group] || []).length; }
function formatGap(value) { return value == null ? "—" : `${Number(value).toFixed(2)} eV`; }
function formatCommit(app) { return app?.commit ? app.commit.slice(0, 10) : "not recorded"; }
function observableLabel(record) { return String(record.summary?.observable || "Not recorded").replace(/^Archived\s+/i, ""); }
function recordNote(record) {
  const note = record.summary?.notes || record.missing?.join("; ") || "No additional note recorded.";
  return /diagnostic/i.test(note) ? "Archived result record; detailed files and provenance are listed below." : note;
}

function renderStats() {
  const twoD = state.calculations.filter(c => c.dimension === "2d").length;
  const threeD = state.calculations.filter(c => c.dimension === "3d").length;
  const withFigures = state.calculations.filter(c => (c.files?.figures || []).some(f => /\.(svg|png|jpe?g|webp)$/i.test(f.path))).length;
  const released = state.sets.filter(s => basisStatus(s) === "publishable").length;
  document.querySelector("#stats").innerHTML = state.mode === "materials"
    ? `<span><strong>${state.calculations.length}</strong> records</span><span><strong>${twoD}</strong> 2D</span><span><strong>${threeD}</strong> 3D</span><span><strong>${withFigures}</strong> with figures</span>`
    : `<span><strong>${state.sets.length}</strong> element records</span><span><strong>${released}</strong> publishable sets</span><span><strong>${state.calculations.length}</strong> linked calculations</span>`;
}
function renderMaterialRow(c) {
  const methods = methodFiles(c).map(method => `<span class="method-tag method-${method.toLowerCase()}">${method}</span>`).join("") || '<span class="muted">table only</span>';
  const figureCount = (c.files?.figures || []).filter(f => /\.(svg|png|jpe?g|webp)$/i.test(f.path)).length;
  const exactBasis = (c.species || []).map(s => s.set_id || s.element).filter(Boolean).join(", ") || "Not linked";
  return `<a class="catalog-row material-row" href="#/material/${encodeURIComponent(c.id)}"><div class="material-name"><strong>${esc(c.material)}</strong><span>${esc(c.formula || "")}</span></div><div><span class="dimension-tag">${esc(c.dimension.toUpperCase())}</span></div><div class="row-value"><span class="row-label">GW gap</span><strong>${formatGap(gapValue(c))}</strong></div><div class="row-methods"><span class="row-label">Methods</span><span>${methods}</span></div><div class="row-basis"><span class="row-label">Basis</span><span title="${esc(exactBasis)}">${esc(exactBasis)}</span></div><div class="row-figures"><span class="row-label">Figures</span><strong>${figureCount || "—"}</strong><span class="chevron">›</span></div></a>`;
}
function renderBasisRow(set) {
  const linked = linkedCalculations(set);
  const files = new Set((set.files || []).map(file => file.role));
  return `<article class="catalog-row basis-row"><div class="material-name"><strong>${esc(set.element)}</strong><span>${esc(set.family || "Basis set")}</span></div><div><span class="publication-tag ${esc(basisStatus(set))}">${esc(statusLabel(basisStatus(set)))}</span></div><div class="basis-scope"><span class="row-label">Scope</span><span>${esc(set.validation_scope || "Not recorded")}</span></div><div class="basis-files"><span class="row-label">Assets</span><span>${["pp", "nao", "abf"].filter(role => files.has(role)).map(role => `<b>${role.toUpperCase()}</b>`).join(" ") || "—"}</span></div><div class="basis-linked"><span class="row-label">Linked records</span><strong>${linked.length}</strong></div><div class="row-link">${linked.length ? linked.slice(0, 3).map(c => `<a href="#/material/${encodeURIComponent(c.id)}">${esc(c.material)}</a>`).join(", ") : "No linked calculation"}</div></article>`;
}
function renderHome() {
  document.querySelector("#home-view").hidden = false;
  document.querySelector("#detail-view").hidden = true;
  const basis = state.mode === "basis";
  document.querySelector("#catalog-kicker").textContent = basis ? "BASIS LIBRARY" : "MATERIALS";
  document.querySelector("#catalog-title").textContent = basis ? "Pseudopotential, NAO, and auxiliary basis records" : "Calculation records";
  document.querySelector("#search").placeholder = basis ? "Search element, family, scope, or linked material" : "Search material, formula, element, or record ID";
  document.querySelector(".dimension-filter").hidden = basis;
  document.querySelector("#status-filter").closest(".select-control").hidden = !basis;
  const sortOptions = basis ? ["element", "status"] : ["material", "gap"];
  if (!sortOptions.includes(state.sort)) state.sort = sortOptions[0];
  document.querySelector("#sort").innerHTML = basis ? '<option value="element">Element</option><option value="status">Publication</option>' : '<option value="material">Material</option><option value="gap">GW gap</option>';
  document.querySelector("#sort").value = state.sort;
  const records = basis ? filteredSets() : filteredCalculations();
  document.querySelector("#result-count").textContent = `${records.length} of ${basis ? state.sets.length : state.calculations.length} ${basis ? "basis records" : "materials"}`;
  document.querySelector("#empty").hidden = records.length !== 0;
  document.querySelector("#catalog").innerHTML = basis ? records.map(renderBasisRow).join("") : `<div class="catalog-head"><span>Material</span><span>Dim.</span><span>GW gap</span><span>Methods</span><span>Basis linkage</span><span>Figures</span></div>${records.map(renderMaterialRow).join("")}`;
  renderStats();
}
function detailsList(items) {
  return items.filter(Boolean).map(item => `<li>${item}</li>`).join("") || '<li class="muted">Not recorded</li>';
}
function renderDetail(id) {
  const record = state.calculations.find(item => item.id === id);
  document.querySelector("#home-view").hidden = true;
  const view = document.querySelector("#detail-view");
  view.hidden = false;
  if (!record) { view.innerHTML = '<a class="back-link" href="#/">← Back to materials</a><div class="not-found"><h1>Record not found</h1><p>This calculation ID is not in the public catalog.</p></div>'; return; }
  const figures = (record.files?.figures || []).filter(file => /\.(svg|png|jpe?g|webp)$/i.test(file.path));
  const files = allFiles(record);
  const firstInput = files.find(file => file.kind === "inputs");
  const inputAction = firstInput ? `<a class="outline-button" href="${pathOf(firstInput)}">Open first input</a>` : "";
  const basisUsed = (record.species || []).map(s => `<li><strong>${esc(s.element)}</strong><span>${esc(s.set_id || "set not linked")}</span></li>`).join("");
  const candidates = (record.basis_candidates || []).map(s => `<li><strong>${esc(s.element)}</strong><span>${esc(s.set_id)} · ${esc(s.scope || "candidate")}</span></li>`).join("");
  const result = record.summary || {};
  view.innerHTML = `<a class="back-link" href="#/">← Back to materials</a>
    <div class="detail-header"><div><p class="kicker">${esc(record.dimension.toUpperCase())} MATERIAL RECORD</p><h1>${esc(record.material)} <span>${esc(record.formula || "")}</span></h1><p class="detail-id">${esc(record.id)}</p></div><div class="detail-actions">${inputAction}</div></div>
    <div class="result-strip"><div><span>DFT gap</span><strong>${formatGap(result.dft_gap_ev)}</strong></div><div><span>EXX gap</span><strong>${formatGap(result.exx_gap_ev)}</strong></div><div class="result-primary"><span>GW gap</span><strong>${formatGap(gapValue(record))}</strong></div><div><span>RPA correlation</span><strong>${esc(result.rpa_correlation_energy ?? result.rpa_energy ?? "—")}</strong></div></div>
    <section class="detail-section figure-section"><div class="section-heading"><div><p class="kicker">BAND STRUCTURE</p><h2>Electronic bands</h2></div><p>${figures.length} figure${figures.length === 1 ? "" : "s"}</p></div>${figures.length ? `<div class="figure-grid">${figures.map(file => `<figure><a href="${pathOf(file)}"><img loading="lazy" src="${pathOf(file)}" alt="${esc(file.label || record.material + " band figure")}"></a><figcaption><span>${esc(file.label || file.path.split("/").pop())}</span><a href="${pathOf(file)}">Open full size ↗</a></figcaption></figure>`).join("")}</div>` : '<div class="empty-panel">No derived figure is registered for this record. The raw band tables remain available below.</div>'}</section>
    <div class="detail-columns"><section class="detail-section"><p class="kicker">BASIS LINKAGE</p><h2>Basis used</h2><ul class="key-list">${basisUsed || '<li class="muted">Exact species linkage not recorded</li>'}</ul>${candidates ? `<h3>Other candidates</h3><ul class="key-list">${candidates}</ul>` : ""}</section><section class="detail-section"><p class="kicker">PROVENANCE</p><h2>Calculation identity</h2><dl class="provenance"><dt>ABACUS</dt><dd>${esc(formatCommit(record.software?.abacus))}</dd><dt>LibRPA</dt><dd>${esc(formatCommit(record.software?.librpa))}</dd><dt>Observable</dt><dd>${esc(observableLabel(record))}</dd><dt>Scope</dt><dd>${esc(result.scope || "Not recorded")}</dd></dl></section></div>
    <section class="detail-section"><p class="kicker">FILES AND NOTES</p><h2>Reproducibility bundle</h2><p class="detail-note">${esc(recordNote(record))}</p><div class="file-groups">${["inputs", "results", "logs", "figures"].map(kind => `<details><summary>${kind} <span>${fileCount(record, kind)}</span></summary><ul>${detailsList((record.files?.[kind] || []).map(assetLink))}</ul></details>`).join("")}</div></section>`;
}
function updatePublicationFilter() {
  const select = document.querySelector("#status-filter");
  const values = [...new Set(state.sets.map(basisStatus))].sort();
  select.innerHTML = '<option value="all">All publication states</option>' + values.map(value => `<option value="${esc(value)}">${esc(statusLabel(value))}</option>`).join("");
  select.value = values.includes(state.status) ? state.status : "all";
  if (!values.includes(state.status)) state.status = "all";
}
function route() {
  const match = location.hash.match(/^#\/material\/(.+)$/);
  if (match) { renderDetail(decodeURIComponent(match[1])); return; }
  state.mode = location.hash === "#/basis" ? "basis" : "materials";
  updatePublicationFilter();
  renderHome();
}
async function start() {
  try {
    const response = await fetch("data.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    state.calculations = data.calculations || [];
    state.sets = data.basis_sets || [];
    document.querySelector("#search").addEventListener("input", event => { state.query = event.target.value.trim().toLowerCase(); renderHome(); });
    document.querySelector("#status-filter").addEventListener("change", event => { state.status = event.target.value; renderHome(); });
    document.querySelector("#sort").addEventListener("change", event => { state.sort = event.target.value; renderHome(); });
    document.querySelectorAll("input[name=dimension]").forEach(input => input.addEventListener("change", event => { state.dimension = event.target.value; renderHome(); }));
    window.addEventListener("hashchange", route);
    route();
  } catch (error) { document.querySelector("#result-count").textContent = `Database could not be loaded: ${error.message}`; }
}
start();
