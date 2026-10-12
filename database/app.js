import { matchesSearch } from "./search.mjs";
import { esc, bandGap, paperGap, filesOf, recordElements, methodNames } from "./records.mjs";
import { installPreview } from "./files.mjs";
import { renderMaterial, renderBasis, installDetailActions } from "./details.mjs";

const $ = selector => document.querySelector(selector);
const state = { mode: "materials", calculations: [], sets: [], dimension: "all", element: "all", inputs: "all", status: "all", sort: "material", query: "", page: 1, currentRecord: null, returnHash: "#/" };
const pageSize = 20;
const publication = set => set.publication?.status || "database_only";
const statusNames = { database_only: "Archive only", legacy_incomplete: "Incomplete evidence", review: "Under review", publishable: "Publishable", superseded: "Superseded" };
const gapText = value => value === null ? '<span class="not-reported" title="Not reported">—</span>' : value.toFixed(3);
let bySet = new Map();
let elements = [];
let corpus = new Map();
let linked = new Map();

function buildIndexes() {
  bySet = new Map(state.sets.map(set => [set.id, set]));
  elements = [...new Set([...state.sets.map(s => s.element), ...state.calculations.flatMap(recordElements)])].sort();
  for (const record of state.calculations) {
    const ids = new Set([...(record.species || []), ...(record.basis_candidates || [])].map(s => s.set_id).filter(Boolean));
    corpus.set(record.id, { record, basis: [...ids].map(id => bySet.get(id)).filter(Boolean) });
    for (const id of ids) { if (!linked.has(id)) linked.set(id, []); linked.get(id).push(record); }
  }
  for (const set of state.sets) {
    const records = new Map((linked.get(set.id) || []).map(r => [r.id, r]));
    for (const id of set.publication?.calculation_ids || []) {
      const record = state.calculations.find(r => r.id === id);
      if (record) records.set(id, record);
    }
    linked.set(set.id, [...records.values()]);
  }
}

function matchesQuery(item, isBasis = false) {
  const exactElement = elements.find(element => element.toLowerCase() === state.query.toLowerCase());
  if (exactElement) return isBasis ? item.element === exactElement : recordElements(item).includes(exactElement);
  return matchesSearch(isBasis ? { set: item, calculations: linked.get(item.id) } : corpus.get(item.id), state.query);
}

function filtered() {
  if (state.mode === "basis") return state.sets.filter(set => matchesQuery(set, true) && (state.element === "all" || state.element === set.element) && (state.status === "all" || state.status === publication(set))).sort((a, b) => (state.sort === "status" ? publication(a).localeCompare(publication(b)) : 0) || a.element.localeCompare(b.element) || (a.family || "").localeCompare(b.family || "") || a.id.localeCompare(b.id));
  return state.calculations.filter(record => matchesQuery(record) && (state.dimension === "all" || record.dimension === state.dimension) && (state.element === "all" || recordElements(record).includes(state.element)) && (state.inputs === "all" || (filesOf(record, "inputs").length > 0) === (state.inputs === "available"))).sort((a, b) => (state.sort === "gap" ? (bandGap(b) ?? -Infinity) - (bandGap(a) ?? -Infinity) : 0) || a.material.localeCompare(b.material) || a.id.localeCompare(b.id));
}

function materialRow(record) {
  const count = filesOf(record, "inputs").length;
  const methods = methodNames(record).map(method => `<span class="method-tag method-${method.toLowerCase()}">${method}</span>`).join("") || '<span class="not-reported">—</span>';
  const url = `#/material/${encodeURIComponent(record.id)}`;
  return `<tr class="material-row"><th scope="row"><a class="material-link" href="${url}">${esc(record.material)}</a><span class="table-description">${esc(record.formula || record.material)}</span></th><td><span class="dimension-tag">${esc(record.dimension.toUpperCase())}</span></td><td><div class="method-list">${methods}</div></td>${["DFT", "EXX", "GW"].map(method => `<td class="numeric ${method === "GW" ? "gw-value" : ""}"><span title="${paperGap(record, method) ? `Paper-reported · Table ${esc(record.paper_values.source.table)}; archived value retained in Overview` : "Archived result / sampled path"}">${gapText(bandGap(record, method))}</span></td>`).join("")}<td>${count ? `<span class="availability"><i aria-hidden="true"></i>${count} files</span>` : '<span class="missing-value">Not archived</span>'}</td><td class="open-cell"><a href="${url}" aria-label="Open ${esc(record.material)} calculation ${esc(record.id)}">↗</a></td></tr>`;
}

function basisRow(set) {
  const payloads = (set.files || []).filter(f => ["pp", "nao", "for_aux", "abf"].includes(f.role));
  const roles = [...new Set(payloads.map(f => f.role))].map(role => `<span class="asset-role">${esc(role === "for_aux" ? "for_aux" : role.toUpperCase())}</span>`).join("");
  return `<tr class="basis-row"><th scope="row"><a class="material-link" href="#/basis/${encodeURIComponent(set.id)}">${esc(set.element)}</a><span class="table-description">${esc(set.family || "Unspecified family")}</span></th><td><div class="method-list">${roles}</div></td><td><span class="publication-tag">${esc(statusNames[publication(set)] || publication(set))}</span></td><td class="basis-scope">${esc(set.validation_scope || "Not recorded")}</td><td class="numeric">${(linked.get(set.id) || []).length}</td><td class="open-cell"><a href="#/basis/${encodeURIComponent(set.id)}" aria-label="Open basis set ${esc(set.id)}">↗</a></td></tr>`;
}

function stats() {
  const withInputs = state.calculations.filter(r => filesOf(r, "inputs").length).length;
  const values = [[state.calculations.length, "Calculation records"], [new Set(state.sets.map(s => s.element)).size, "Elements in basis library"], [state.sets.length, "Basis-set records"], [withInputs, "Records with input files"]];
  $("#stats").innerHTML = values.map(([value, label], i) => `<div><span class="stat-index">0${i + 1}</span><strong>${value}</strong><span>${label}</span></div>`).join("");
  document.querySelectorAll("[data-dimension-count]").forEach(node => { node.textContent = node.dataset.dimensionCount === "all" ? state.calculations.length : state.calculations.filter(c => c.dimension === node.dataset.dimensionCount).length; });
}

function syncFilters() {
  const basis = state.mode === "basis";
  $(".dimension-filter").hidden = basis;
  $("#input-filter-control").hidden = basis;
  $("#status-filter-control").hidden = !basis;
  $("#search").value = state.query;
  $("#element-filter").value = state.element;
  $("#input-filter").value = state.inputs;
  $("#status-filter").value = state.status;
  document.querySelectorAll("input[name=dimension]").forEach(input => { input.checked = input.value === state.dimension; });
  $("#sort").innerHTML = basis ? '<option value="element">Element A–Z</option><option value="status">Publication state</option>' : '<option value="material">Material A–Z</option><option value="gap">GW gap ↓</option>';
  if (!(basis ? ["element", "status"] : ["material", "gap"]).includes(state.sort)) state.sort = basis ? "element" : "material";
  $("#sort").value = state.sort;
}

function listHash() {
  const params = new URLSearchParams();
  for (const [key, value, fallback] of [["q", state.query, ""], ["dim", state.dimension, "all"], ["element", state.element, "all"], ["inputs", state.inputs, "all"], ["status", state.status, "all"], ["sort", state.sort, state.mode === "basis" ? "element" : "material"], ["page", state.page, 1]]) if (value !== fallback) params.set(key, value);
  return `#/${state.mode === "basis" ? "basis" : ""}${params.size ? `?${params}` : ""}`;
}

function renderHome() {
  const basis = state.mode === "basis";
  $("#home-view").hidden = false;
  $("#detail-view").hidden = true;
  $("#page-title").textContent = basis ? "The basis behind each result." : "Materials, with evidence.";
  $("#intro-copy").textContent = basis ? "Inspect pseudopotentials, physical orbitals, and auxiliary basis functions — with original files, source hashes, and linked calculations." : "Electronic bands, original inputs, and exact basis files — linked to each calculation and its source commits.";
  $("#search").placeholder = basis ? "Search element, family, original filename, or linked material" : "Search material, formula, element, or calculation ID";
  $("#catalog-title").textContent = basis ? "Basis-set records" : "Calculation records";
  $("#catalog-footnote").textContent = basis ? "Archive records are not automatically recommended releases. Open a set for readable filenames, downloads, source hashes, and linked calculations." : "One row per calculation. PBE/GW values prefer the paper's own columns when recorded; EXX remains archive-derived. Original path values and differences are retained in Overview. The archived k-path is not the global fundamental gap; diagnostics retain their scope. A dash means not reported.";
  const records = filtered();
  const pages = Math.max(1, Math.ceil(records.length / pageSize));
  state.page = Math.min(state.page, pages);
  const start = (state.page - 1) * pageSize;
  $("#result-count").textContent = `${records.length} of ${basis ? state.sets.length : state.calculations.length} records${state.query ? ` matching “${state.query}”` : ""}`;
  $("#empty").hidden = records.length > 0;
  $("#catalog").hidden = !records.length;
  $("#catalog").setAttribute("aria-busy", "false");
  const headings = basis ? ["Element / family", "Assets", "Publication", "Recorded scope", "Linked", ""] : ["Material", "Dim.", "Methods", "DFT gap", "EXX gap", "GW gap", "Inputs", ""];
  $("#catalog").innerHTML = `<div class="table-wrap" tabindex="0" role="region" aria-label="${basis ? "Basis sets" : "Calculation records"}"><table class="catalog-table ${basis ? "basis-table" : ""}"><caption class="sr-only">${basis ? "Basis library" : "Materials and electronic band gaps in eV"}</caption><thead><tr>${headings.map((heading, i) => `<th scope="col" class="${!basis && i >= 3 && i <= 5 ? "numeric" : ""}">${heading || '<span class="sr-only">Open record</span>'}</th>`).join("")}</tr></thead><tbody>${records.slice(start, start + pageSize).map(basis ? basisRow : materialRow).join("")}</tbody></table></div><div class="pagination"><span>${records.length ? start + 1 : 0}–${Math.min(start + pageSize, records.length)} of ${records.length}</span><div><button type="button" data-page="${state.page - 1}" ${state.page === 1 ? "disabled" : ""} aria-label="Previous page">←</button><span>Page ${state.page} / ${pages}</span><button type="button" data-page="${state.page + 1}" ${state.page === pages ? "disabled" : ""} aria-label="Next page">→</button></div></div>`;
  document.title = `${basis ? "Basis library" : "Materials"} · ABACUS + LibRPA`;
  document.querySelectorAll("[data-nav]").forEach(a => a.setAttribute("aria-current", a.dataset.nav === state.mode ? "page" : "false"));
}

function updateFilter() {
  state.page = 1;
  renderHome();
  history.replaceState(null, "", listHash());
  state.returnHash = listHash();
}

function resetFilters() {
  Object.assign(state, { query: "", dimension: "all", element: "all", inputs: "all", status: "all", sort: state.mode === "basis" ? "element" : "material", page: 1 });
  syncFilters();
  updateFilter();
}

function route() {
  const hash = location.hash || "#/";
  const match = hash.match(/^#\/(material|basis)\/([^?]+)$/);
  if (match) {
    let id;
    try { id = decodeURIComponent(match[2]); } catch { id = null; }
    const record = (match[1] === "material" ? state.calculations : state.sets).find(r => r.id === id);
    $("#home-view").hidden = true;
    $("#detail-view").hidden = false;
    state.currentRecord = match[1] === "material" ? record : null;
    $("#detail-view").innerHTML = record ? match[1] === "material" ? renderMaterial(record, state.sets) : renderBasis(record, state.calculations) : '<div class="empty-panel"><h1>Record not found</h1><p>This ID is not in the public catalog.</p><a href="#/">Return to materials</a></div>';
    const back = $(".breadcrumb a");
    if (back && (match[1] === "material" ? state.mode === "materials" : state.mode === "basis")) back.href = state.returnHash;
    document.title = `${record?.material || record?.id || "Record not found"} · ABACUS + LibRPA`;
    document.querySelectorAll("[data-nav]").forEach(a => a.setAttribute("aria-current", a.dataset.nav === (match[1] === "material" ? "materials" : "basis") ? "page" : "false"));
    window.scrollTo(0, 0);
    return;
  }
  state.mode = hash.split("?")[0] === "#/basis" ? "basis" : "materials";
  const params = new URLSearchParams(hash.split("?")[1] || "");
  Object.assign(state, { query: params.get("q") || "", dimension: ["2d", "3d"].includes(params.get("dim")) ? params.get("dim") : "all", element: elements.includes(params.get("element")) ? params.get("element") : "all", inputs: ["available", "missing"].includes(params.get("inputs")) ? params.get("inputs") : "all", status: params.get("status") || "all", sort: params.get("sort") || (state.mode === "basis" ? "element" : "material"), page: Math.max(1, Number.parseInt(params.get("page"), 10) || 1) });
  state.returnHash = hash;
  syncFilters();
  renderHome();
}

async function start() {
  installPreview($("#file-preview"));
  installDetailActions($("#detail-view"), () => state.currentRecord);
  try {
    const response = await fetch("data.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!Array.isArray(data.calculations) || !Array.isArray(data.basis_sets)) throw new Error("Invalid catalog format");
    state.calculations = data.calculations;
    state.sets = data.basis_sets;
    buildIndexes();
    stats();
    $("#element-filter").innerHTML = '<option value="all">All elements</option>' + elements.map(e => `<option value="${esc(e)}">${esc(e)}</option>`).join("");
    $("#status-filter").innerHTML = '<option value="all">All publication states</option>' + [...new Set(state.sets.map(publication))].sort().map(s => `<option value="${esc(s)}">${esc(statusNames[s] || s)}</option>`).join("");
    $("#search").addEventListener("input", event => { state.query = event.target.value.trim(); updateFilter(); });
    for (const [id, key] of [["element-filter", "element"], ["input-filter", "inputs"], ["status-filter", "status"], ["sort", "sort"]]) $(`#${id}`).addEventListener("change", event => { state[key] = event.target.value; updateFilter(); });
    document.querySelectorAll("input[name=dimension]").forEach(input => input.addEventListener("change", event => { state.dimension = event.target.value; updateFilter(); }));
    for (const id of ["reset-filters", "empty-reset"]) $(`#${id}`).addEventListener("click", resetFilters);
    $("#filter-toggle").addEventListener("click", event => {
      const button = event.currentTarget;
      const expanded = button.getAttribute("aria-expanded") !== "true";
      button.setAttribute("aria-expanded", String(expanded));
      button.innerHTML = `${expanded ? "Hide" : "Show"} filters <span aria-hidden="true">${expanded ? "−" : "+"}</span>`;
      $(".filter-panel").classList.toggle("filters-expanded", expanded);
    });
    $("#search-examples").addEventListener("click", event => { const button = event.target.closest("[data-query]"); if (button) { state.query = button.dataset.query; $("#search").value = state.query; updateFilter(); } });
    $("#catalog").addEventListener("click", event => { const button = event.target.closest("[data-page]"); if (button && !button.disabled) { state.page = Number(button.dataset.page); renderHome(); history.replaceState(null, "", listHash()); state.returnHash = listHash(); $("#catalog-title").scrollIntoView({ block: "start" }); } });
    document.addEventListener("keydown", event => { if (event.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) && !$("#home-view").hidden && !$("#file-preview").open) { event.preventDefault(); $("#search").focus(); } });
    window.addEventListener("hashchange", route);
    route();
  } catch (error) {
    $("#result-count").textContent = "Archive unavailable";
    $("#catalog").setAttribute("aria-busy", "false");
    $("#load-error").hidden = false;
    $("#load-error").textContent = `The catalog could not be loaded (${error.message}). Serve the repository over HTTP, or retry the deployed website. No substitute records are shown.`;
  }
}
start();
