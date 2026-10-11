const statusNames = {
  gw_validated: "GW validated", gw_diagnostic: "GW diagnostic", path_diagnostic: "Path diagnostic",
  pbe_only: "PBE only", generation_only: "Generation only", failed: "Failed gate", pending: "Pending",
  database_only: "Database only", review: "Under review", publishable: "Publishable", superseded: "Superseded"
};
const state = { mode: "materials", calculations: [], sets: [], dimension: "all", status: "all", sort: "material", query: "" };
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const statusLabel = value => statusNames[value] || value || "Unclassified";
const assetLink = file => `<a href="../${encodeURI(file.path)}">${esc(file.label || file.path.split("/").pop())}</a>`;
const allFiles = record => Object.entries(record.files || {}).flatMap(([kind, files]) => (files || []).map(file => ({ ...file, kind })));

function basisStatus(set) { return set.publication?.status || "database_only"; }
function basisText(set, linked) {
  return [set.id, set.element, set.family, set.validation_scope, set.notes, basisStatus(set), ...linked.map(c => `${c.material} ${c.formula} ${c.id}`)].join(" ").toLowerCase();
}
function linkedCalculations(set) {
  const explicit = new Set(set.publication?.calculation_ids || []);
  return state.calculations.filter(c => explicit.has(c.id) || (c.species || []).some(s => s.set_id === set.id) || (c.basis_candidates || []).some(s => s.set_id === set.id));
}
function dimensionMatches(value, linked) { return state.dimension === "all" || linked.some(c => c.dimension === state.dimension) || (value === state.dimension && !linked.length); }
function filteredCalculations() {
  const knownMaterials = new Set(state.calculations.flatMap(c => [c.material, c.formula]).filter(Boolean).map(value => value.toLowerCase()));
  return state.calculations.filter(c => {
    const text = [c.material, c.formula, c.id, c.dimension, c.status, c.summary?.observable, c.summary?.notes, c.summary?.scope,
      ...(c.species || []).flatMap(s => [s.element, s.set_id]), ...(c.basis_candidates || []).flatMap(s => [s.element, s.set_id, s.scope]),
      c.software?.abacus?.commit, c.software?.librpa?.commit].join(" ").toLowerCase();
    const exactMaterial = [c.material, c.formula].filter(Boolean).some(value => value.toLowerCase() === state.query);
    const searchMatch = knownMaterials.has(state.query) ? exactMaterial : text.includes(state.query);
    return dimensionMatches(c.dimension, [c]) && (state.status === "all" || c.status === state.status) && searchMatch;
  }).sort((a, b) => state.sort === "status" ? statusLabel(a.status).localeCompare(statusLabel(b.status)) || a.material.localeCompare(b.material) : a.material.localeCompare(b.material) || a.id.localeCompare(b.id));
}
function filteredSets() {
  const knownElements = new Set(state.sets.map(set => set.element.toLowerCase()));
  return state.sets.filter(set => {
    const linked = linkedCalculations(set);
    const elementMatch = set.element.toLowerCase() === state.query;
    const searchMatch = knownElements.has(state.query) ? elementMatch : basisText(set, linked).includes(state.query);
    return dimensionMatches(null, linked) && (state.status === "all" || basisStatus(set) === state.status) && searchMatch;
  }).sort((a, b) => state.sort === "element" ? a.element.localeCompare(b.element) || a.id.localeCompare(b.id) : state.sort === "status" ? statusLabel(basisStatus(a)).localeCompare(statusLabel(basisStatus(b))) || a.id.localeCompare(b.id) : a.element.localeCompare(b.element) || a.id.localeCompare(b.id));
}
function gateText(record) {
  const gates = record.summary?.gates || record.gates || [];
  return Array.isArray(gates) && gates.length ? gates.join("; ") : "Not summarized";
}
function renderStats() {
  const twoD = state.calculations.filter(c => c.dimension === "2d").length;
  const threeD = state.calculations.filter(c => c.dimension === "3d").length;
  const released = state.sets.filter(s => basisStatus(s) === "publishable").length;
  document.querySelector("#stats").innerHTML = `<span><strong>${state.calculations.length}</strong> calculation records</span><span><strong>${twoD}</strong> 2D</span><span><strong>${threeD}</strong> 3D</span><span><strong>${state.sets.length}</strong> element basis records</span><span><strong>${released}</strong> publishable sets</span>`;
}
function renderMaterialCard(c) {
  const result = c.summary || {};
  const files = allFiles(c);
  const plot = (c.files?.figures || []).find(f => /\.(png|jpe?g|webp)$/i.test(f.path));
  const exact = (c.species || []).map(s => `${s.element}${s.set_id ? ` · ${s.set_id}` : ""}`).join("<br>") || "Exact production basis not linked";
  const candidates = (c.basis_candidates || []).map(s => `${s.element} · ${s.set_id} <small>${esc(s.scope || "candidate")}</small>`).join("<br>");
  const bands = files.filter(f => f.kind === "results" && /(band|GW|EXX|KS)/i.test(f.label || f.path)).map(assetLink).join("<br>") || "Not recorded";
  const figures = (c.files?.figures || []).map(assetLink).join("<br>") || "Not recorded";
  return `<article class="record-card"><div class="card-heading"><div><span class="eyebrow">${esc(c.dimension.toUpperCase())}</span><h2>${esc(c.material)} <span>${esc(c.formula || "")}</span></h2><p class="record-id">${esc(c.id)}</p></div><span class="badge ${esc(c.status)}">${esc(statusLabel(c.status))}</span></div>
    <div class="metric-grid"><div><small>Observable</small><strong>${esc(result.observable || "Not recorded")}</strong></div><div><small>Value</small><strong>${result.value == null ? "Not recorded" : `${esc(result.value)} ${esc(result.unit || "eV")}`}</strong></div><div><small>RPA correlation</small><strong>${esc(result.rpa_correlation_energy ?? result.rpa_energy ?? "Not recorded")}</strong></div></div>
    <details><summary>Structure, basis, and provenance</summary><div class="details-body"><dl><dt>Basis used</dt><dd>${exact}</dd>${candidates ? `<dt>Other candidates</dt><dd>${candidates}</dd>` : ""}<dt>Gates</dt><dd>${esc(gateText(c))}</dd><dt>ABACUS</dt><dd>${esc(c.software?.abacus?.commit || "Commit not recorded")}</dd><dt>LibRPA</dt><dd>${esc(c.software?.librpa?.commit || "Commit not recorded")}</dd><dt>Notes</dt><dd>${esc(result.notes || c.missing?.join("; ") || "")}</dd></dl></div></details>
    <details><summary>Band results and files</summary><div class="details-body"><p><strong>Band tables</strong><br>${bands}</p><p><strong>Figures</strong><br>${figures}</p><ul>${files.map(f => `<li>${esc(f.kind)}: ${assetLink(f)}</li>`).join("")}</ul></div></details>${plot ? `<a href="../${encodeURI(plot.path)}"><img class="preview" loading="lazy" src="../${encodeURI(plot.path)}" alt="${esc(c.material)} band plot"></a>` : ""}</article>`;
}
function renderBasisCard(set) {
  const linked = linkedCalculations(set);
  const files = (set.files || []).filter(f => ["pp", "nao", "for_aux", "abf"].includes(f.role));
  const linkedText = linked.length ? linked.map(c => `<a href="#" data-material="${esc(c.id)}">${esc(c.material)} (${esc(c.dimension)})</a>`).join(", ") : "No linked calculation";
  return `<article class="record-card basis-card"><div class="card-heading"><div><span class="eyebrow">ELEMENT · ${esc(set.element)}</span><h2>${esc(set.family || "Basis set")}</h2><p class="record-id">${esc(set.id)}</p></div><span class="badge ${esc(basisStatus(set))}">${esc(statusLabel(basisStatus(set)))}</span></div><p>${esc(set.validation_scope || "Validation scope not recorded")}</p><div class="metric-grid"><div><small>PP</small><strong>${files.some(f => f.role === "pp") ? "Available" : "Missing"}</strong></div><div><small>Physical NAO</small><strong>${files.some(f => f.role === "nao") ? "Available" : "Missing"}</strong></div><div><small>ABF</small><strong>${files.some(f => f.role === "abf") ? "Available" : "Missing"}</strong></div></div><details><summary>Files, calculations, and notes</summary><div class="details-body"><dl><dt>Calculations</dt><dd>${linkedText}</dd><dt>for_aux</dt><dd>${files.some(f => f.role === "for_aux") ? "Available; auxiliary generation only" : "Not recorded"}</dd><dt>Notes</dt><dd>${esc(set.notes || "")}</dd></dl><ul>${files.map(f => `<li>${esc(f.role)}: ${assetLink(f)}</li>`).join("")}</ul></div></details></article>`;
}
function render() {
  const records = state.mode === "materials" ? filteredCalculations() : filteredSets();
  document.querySelector("#result-count").textContent = `${records.length} of ${state.mode === "materials" ? state.calculations.length : state.sets.length} ${state.mode}`;
  document.querySelector("#empty").hidden = records.length !== 0;
  document.querySelector("#catalog").innerHTML = records.map(state.mode === "materials" ? renderMaterialCard : renderBasisCard).join("");
  document.querySelectorAll("[data-material]").forEach(link => link.addEventListener("click", event => { event.preventDefault(); state.mode = "materials"; state.query = event.currentTarget.dataset.material; document.querySelector("#search").value = state.query; updateTabs(); render(); }));
}
function updateTabs() {
  document.querySelectorAll(".tab").forEach(tab => { const active = tab.id === `${state.mode}-tab`; tab.classList.toggle("active", active); tab.setAttribute("aria-selected", active ? "true" : "false"); });
  const status = document.querySelector("#status-filter");
  const values = state.mode === "materials" ? [...new Set(state.calculations.map(c => c.status))] : [...new Set(state.sets.map(basisStatus))];
  status.innerHTML = `<option value="all">All levels</option>` + values.sort().map(value => `<option value="${esc(value)}">${esc(statusLabel(value))}</option>`).join("");
  status.value = values.includes(state.status) ? state.status : "all";
  if (!values.includes(state.status)) state.status = "all";
}
async function start() {
  try {
    const response = await fetch("data.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json(); state.calculations = data.calculations || []; state.sets = data.basis_sets || [];
    renderStats();
    document.querySelector("#search").addEventListener("input", event => { state.query = event.target.value.trim().toLowerCase(); render(); });
    document.querySelector("#status-filter").addEventListener("change", event => { state.status = event.target.value; render(); });
    document.querySelector("#sort").addEventListener("change", event => { state.sort = event.target.value; render(); });
    document.querySelectorAll("input[name=dimension]").forEach(input => input.addEventListener("change", event => { state.dimension = event.target.value; render(); }));
    document.querySelector("#materials-tab").addEventListener("click", () => { state.mode = "materials"; state.status = "all"; updateTabs(); render(); });
    document.querySelector("#basis-tab").addEventListener("click", () => { state.mode = "basis"; state.status = "all"; updateTabs(); render(); });
    updateTabs(); render();
  } catch (error) { document.querySelector("#result-count").textContent = `Database could not be loaded: ${error.message}`; }
}
start();
