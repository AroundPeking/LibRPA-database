import { matchesSearch } from "./search.mjs";
import { esc, filesOf, recordElements, methodNames, methodTag, socTag, spinPolTag, recordType, atomCount, primaryResult, workflowLabel, workflowFrontend } from "./records.mjs";
import { installPreview } from "./files.mjs";
import { installRadial } from "./radial.mjs";
import { renderMaterial, renderBasis, installDetailActions } from "./details.mjs";
import { gapOverview, renderGapOverview } from "./gaps.mjs";

const $ = selector => document.querySelector(selector);
const state = { mode: "materials", calculations: [], sets: [], dimension: "all", software: "all", element: "all", inputs: "all", sort: "material", query: "", page: 1, currentRecord: null, returnHash: "#/" };
const pageSize = 20;
const gapText = value => value === null ? '<span class="not-reported">—</span>' : value.toFixed(3);
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
}

function matchesQuery(item, isBasis = false) {
  const exactElement = elements.find(element => element.toLowerCase() === state.query.toLowerCase());
  if (exactElement) return isBasis ? item.element === exactElement : recordElements(item).includes(exactElement);
  return matchesSearch(isBasis ? { set: item, calculations: linked.get(item.id) } : corpus.get(item.id), state.query);
}

function filtered() {
  if (state.mode === "basis") return state.sets.filter(set => matchesQuery(set, true) && (state.element === "all" || state.element === set.element)).sort((a, b) => a.element.localeCompare(b.element) || (a.family || "").localeCompare(b.family || "") || a.id.localeCompare(b.id));
  return state.calculations.filter(record => matchesQuery(record) && (state.dimension === "all" || record.dimension === state.dimension) && (state.software === "all" || workflowFrontend(record) === state.software) && (state.element === "all" || recordElements(record).includes(state.element)) && (state.inputs === "all" || (filesOf(record, "inputs").length > 0) === (state.inputs === "available"))).sort((a, b) => (state.sort === "result" ? (primaryResult(b)?.value ?? -Infinity) - (primaryResult(a)?.value ?? -Infinity) : 0) || a.material.localeCompare(b.material) || a.id.localeCompare(b.id));
}

function materialRow(record) {
  const count = filesOf(record, "inputs").length;
  const methods = methodNames(record).map(methodTag).join("") + spinPolTag(record) + socTag(record) || '<span class="not-reported">—</span>';
  const url = `#/material/${encodeURIComponent(record.id)}`;
  const atoms = atomCount(record);
  const primary = primaryResult(record);
  const precision = recordType(record) === "large_system_gw" ? 5 : recordType(record) === "reader_conversion" ? 5 : 3;
  const primaryValue = primary ? `${typeof primary.value === "number" ? primary.value.toFixed(precision) : esc(primary.value)}${primary.unit ? ` <small>${esc(primary.unit)}</small>` : ""}` : '<span class="not-reported">—</span>';
  return `<tr class="material-row"><th scope="row"><a class="material-link" href="${url}">${esc(record.material)}</a><span class="table-description">${esc(record.formula || record.material)}</span></th><td><span class="record-type-tag">${esc(workflowLabel(record))}</span></td><td><span class="dimension-tag">${esc(record.dimension.toUpperCase())}</span>${atoms ? `<span class="table-description">${atoms} atoms</span>` : ""}</td><td><div class="method-list">${methods}</div></td><td class="primary-result"><strong>${primaryValue}</strong>${primary ? `<span class="table-description">${esc(primary.label)}</span>` : ""}</td><td>${count ? `<span class="availability"><i aria-hidden="true"></i>${count} files</span>` : '<span class="not-reported">—</span>'}</td><td class="open-cell"><a href="${url}" aria-label="Open ${esc(record.material)} calculation ${esc(record.id)}">↗</a></td></tr>`;
}

function basisRow(set) {
  const payloads = (set.files || []).filter(f => ["pp", "nao", "for_aux", "abf"].includes(f.role));
  const roles = [...new Set(payloads.map(f => f.role))].map(role => `<span class="asset-role">${esc(role.toUpperCase())}</span>`).join("");
  return `<tr class="basis-row"><th scope="row"><a class="material-link" href="#/basis/${encodeURIComponent(set.id)}">${esc(set.element)}</a><span class="table-description">${esc(set.family || "Basis family")}</span></th><td><div class="method-list">${roles}</div></td><td class="basis-scope">${esc(set.validation_scope || "Recorded basis data")}</td><td class="numeric">${(linked.get(set.id) || []).length}</td><td class="open-cell"><a href="#/basis/${encodeURIComponent(set.id)}" aria-label="Open basis set ${esc(set.id)}">↗</a></td></tr>`;
}

function stats() {
  const withInputs = state.calculations.filter(r => filesOf(r, "inputs").length).length;
  const values = [[state.calculations.length, "Calculation records"], [new Set(state.sets.map(s => s.element)).size, "Elements in basis library"], [state.sets.length, "Basis-set records"], [withInputs, "Records with input files"]];
  $("#stats").innerHTML = values.map(([value, label], i) => `<div><span class="stat-index">0${i + 1}</span><strong>${value}</strong><span>${label}</span></div>`).join("");
  document.querySelectorAll("[data-dimension-count]").forEach(node => { node.textContent = node.dataset.dimensionCount === "all" ? state.calculations.length : state.calculations.filter(c => c.dimension === node.dataset.dimensionCount).length; });
}

function syncFilters() {
  const basis = state.mode === "basis";
  const gaps = state.mode === "gaps";
  $(".filter-panel").hidden = gaps;
  $(".search-box").hidden = gaps;
  $(".search-examples").hidden = gaps;
  $(".dimension-filter").hidden = basis;
  $(".software-filter").hidden = basis;
  $("#input-filter-control").hidden = basis;
  $("#search").value = state.query;
  $("#element-filter").value = state.element;
  $("#input-filter").value = state.inputs;
  document.querySelectorAll("input[name=dimension]").forEach(input => { input.checked = input.value === state.dimension; });
  document.querySelectorAll("input[name=software]").forEach(input => { input.checked = input.value === state.software; });
  $("#sort").innerHTML = gaps ? '<option value="result">GW gap ↓</option><option value="material">Material A–Z</option>' : basis ? '<option value="element">Element A–Z</option>' : '<option value="material">Material A–Z</option><option value="result">Primary result ↓</option>';
  if (!(gaps ? ["result", "material"] : basis ? ["element"] : ["material", "result"]).includes(state.sort)) state.sort = gaps ? "result" : basis ? "element" : "material";
  $("#sort").value = state.sort;
}

function listHash() {
  const params = new URLSearchParams();
  for (const [key, value, fallback] of [["q", state.query, ""], ["dim", state.dimension, "all"], ["sw", state.software, "all"], ["element", state.element, "all"], ["inputs", state.inputs, "all"], ["sort", state.sort, state.mode === "basis" ? "element" : state.mode === "gaps" ? "result" : "material"], ["page", state.page, 1]]) if (value !== fallback) params.set(key, value);
  const prefix = state.mode === "basis" ? "#/basis" : state.mode === "gaps" ? "#/gaps" : "#/";
  return `${prefix}${params.size ? `?${params}` : ""}`;
}

function renderHome() {
  const basis = state.mode === "basis";
  const gaps = state.mode === "gaps";
  $("#home-view").hidden = false;
  $("#detail-view").hidden = true;
  $("#page-title").textContent = basis ? "The basis behind each result." : gaps ? "Band gaps, across materials." : "Materials, with evidence.";
  $("#intro-copy").textContent = basis ? "Inspect pseudopotentials, physical orbitals, and auxiliary basis functions — with original files and linked calculations." : gaps ? "Every recorded gap value in one table: PBE / KS, EXX, and GW side by side, one row per calculation, ready for cross-material comparison." : "Electronic bands, RPA energies, large-system GW results, and reader-format provenance — with original inputs, basis provenance, and evidence.";
  $("#search").placeholder = basis ? "Search element, family, original filename, or linked material" : "Search material, formula, element, or calculation ID";
  $("#catalog-title").textContent = basis ? "Basis-set records" : gaps ? "Gap overview" : "Calculation records";
  $("#catalog-footnote").textContent = basis ? "Open a basis record for readable filenames, downloads, radial functions, and linked calculations." : gaps ? "One row per calculation that lists at least one gap value. Values are in eV and keep each record's own definition (path observable, sampled Γ, or paper reference); the bar scales to the largest GW value in the table. A dash means no value is listed." : "One row per calculation. Primary results retain their recorded unit and scope; path-resolved and sampled-grid observables are not presented as global fundamental gaps. A dash means no value is listed. Open a record for source evidence and definitions.";
  if (gaps) {
    const rows = state.calculations.filter(record => gapOverview(record));
    $("#result-count").textContent = `${rows.length} of ${state.calculations.length} records list a gap value`;
    $("#empty").hidden = true;
    $("#catalog").hidden = false;
    $("#catalog").setAttribute("aria-busy", "false");
    $("#catalog").innerHTML = renderGapOverview(state.calculations, state.sort);
    document.title = `Gap overview · LibRPA`;
    document.querySelectorAll("[data-nav]").forEach(a => a.setAttribute("aria-current", a.dataset.nav === state.mode ? "page" : "false"));
    return;
  }
  const records = filtered();
  const pages = Math.max(1, Math.ceil(records.length / pageSize));
  state.page = Math.min(state.page, pages);
  const start = (state.page - 1) * pageSize;
  $("#result-count").textContent = `${records.length} of ${basis ? state.sets.length : state.calculations.length} records${state.query ? ` matching “${state.query}”` : ""}`;
  $("#empty").hidden = records.length > 0;
  $("#catalog").hidden = !records.length;
  $("#catalog").setAttribute("aria-busy", "false");
  const headings = basis ? ["Element / family", "Assets", "Recorded scope", "Linked", ""] : ["Material", "Software", "Scale", "Methods", "Primary result", "Inputs", ""];
  $("#catalog").innerHTML = `<div class="table-wrap" tabindex="0" role="region" aria-label="${basis ? "Basis sets" : "Calculation records"}"><table class="catalog-table ${basis ? "basis-table" : ""}"><caption class="sr-only">${basis ? "Basis library" : "Materials and evidence-linked electronic-structure results"}</caption><thead><tr>${headings.map(heading => `<th scope="col">${heading || '<span class="sr-only">Open record</span>'}</th>`).join("")}</tr></thead><tbody>${records.slice(start, start + pageSize).map(basis ? basisRow : materialRow).join("")}</tbody></table></div><div class="pagination"><span>${records.length ? start + 1 : 0}–${Math.min(start + pageSize, records.length)} of ${records.length}</span><div><button type="button" data-page="${state.page - 1}" ${state.page === 1 ? "disabled" : ""} aria-label="Previous page">←</button><span>Page ${state.page} / ${pages}</span><button type="button" data-page="${state.page + 1}" ${state.page === pages ? "disabled" : ""} aria-label="Next page">→</button></div></div>`;
  document.title = `${basis ? "Basis library" : "Materials"} · LibRPA`;
  document.querySelectorAll("[data-nav]").forEach(a => a.setAttribute("aria-current", a.dataset.nav === state.mode ? "page" : "false"));
}

function updateFilter() {
  state.page = 1;
  renderHome();
  history.replaceState(null, "", listHash());
  state.returnHash = listHash();
}

function resetFilters() {
  Object.assign(state, { query: "", dimension: "all", software: "all", element: "all", inputs: "all", sort: state.mode === "basis" ? "element" : state.mode === "gaps" ? "result" : "material", page: 1 });
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
    $("#detail-view").innerHTML = record ? match[1] === "material" ? renderMaterial(record, state.sets, state.calculations) : renderBasis(record, state.calculations) : '<div class="empty-panel"><h1>Record not found</h1><p>This ID is not in the public catalog.</p><a href="#/">Return to materials</a></div>';
    const back = $(".breadcrumb a");
    if (back && (match[1] === "material" ? state.mode === "materials" : state.mode === "basis")) back.href = state.returnHash;
    document.title = `${record?.material || record?.id || "Record not found"} · LibRPA`;
    document.querySelectorAll("[data-nav]").forEach(a => a.setAttribute("aria-current", a.dataset.nav === (match[1] === "material" ? "materials" : "basis") ? "page" : "false"));
    window.scrollTo(0, 0);
    if (record && match[1] === "basis") $("#detail-view .radial-file[open] [data-radial-load]")?.click();
    return;
  }
  state.mode = hash.split("?")[0] === "#/basis" ? "basis" : hash.split("?")[0] === "#/gaps" ? "gaps" : "materials";
  const params = new URLSearchParams(hash.split("?")[1] || "");
  Object.assign(state, { query: params.get("q") || "", dimension: ["2d", "3d"].includes(params.get("dim")) ? params.get("dim") : "all", software: ["all", "abacus", "fhi_aims"].includes(params.get("sw")) ? params.get("sw") : "all", element: elements.includes(params.get("element")) ? params.get("element") : "all", inputs: ["available", "missing"].includes(params.get("inputs")) ? params.get("inputs") : "all", sort: params.get("sort") || (state.mode === "basis" ? "element" : state.mode === "gaps" ? "result" : "material"), page: Math.max(1, Number.parseInt(params.get("page"), 10) || 1) });
  state.returnHash = hash;
  syncFilters();
  renderHome();
}

async function start() {
  installPreview($("#file-preview"));
  installRadial($("#detail-view"));
  installDetailActions($("#detail-view"), () => state.currentRecord);
  const themeToggle = $("#theme-toggle");
  if (themeToggle) {
    themeToggle.setAttribute("aria-pressed", String(document.documentElement.dataset.theme === "dark"));
    themeToggle.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch { /* storage unavailable */ }
      themeToggle.setAttribute("aria-pressed", String(next === "dark"));
    });
  }
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
    $("#search").addEventListener("input", event => { state.query = event.target.value.trim(); updateFilter(); });
    for (const [id, key] of [["element-filter", "element"], ["input-filter", "inputs"], ["sort", "sort"]]) $(`#${id}`).addEventListener("change", event => { state[key] = event.target.value; updateFilter(); });
    document.querySelectorAll("input[name=dimension]").forEach(input => input.addEventListener("change", event => { state.dimension = event.target.value; updateFilter(); }));
    document.querySelectorAll("input[name=software]").forEach(input => input.addEventListener("change", event => { state.software = event.target.value; updateFilter(); }));
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
    document.addEventListener("keydown", event => { if (event.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) && !$("#home-view").hidden && !$(".search-box").hidden && !$("#file-preview").open) { event.preventDefault(); $("#search").focus(); } });
    window.addEventListener("hashchange", route);
    route();
  } catch (error) {
    $("#result-count").textContent = "Catalog unavailable";
    $("#catalog").setAttribute("aria-busy", "false");
    $("#load-error").hidden = false;
    $("#load-error").textContent = `The catalog could not be loaded (${error.message}). Serve the repository over HTTP, or retry the deployed website. No substitute records are shown.`;
  }
}
start();
