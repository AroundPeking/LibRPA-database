import { matchesSearch, materialSearchText, basisSearchText, normalizeSearchText } from "./search.mjs";
import { esc, recordElements } from "./records.mjs";
import { installPreview, installBlobDownloads } from "./files.mjs";
import { installRadial } from "./radial.mjs";
import { renderMaterial, renderBasis, installDetailActions } from "./details.mjs";
import { buildGapComparison, renderGapOverview, renderGapChart, installGapChartTooltip } from "./gaps.mjs";
import { gapInventory, selectedGapRecords, readGapParams, writeGapParams, syncGapControls, installGapControls } from "./gap-controls.mjs";
import { installCoverEffects, replayCoverEntrance, startCoverCanvas } from "./cover.mjs?v=20261027-review-v29";
import { recordFacts, filterFacts, facetCounts, sortFacts, visibleColumns, renderHeader, renderMaterialRow, factsToCsv, factsToJson, readExplorerParams, writeExplorerParams, COLUMNS, DEFAULT_COLUMNS, DEFAULT_DIRECTION, PAGE_SIZES, RECORD_TYPES, METHOD_FACETS } from "./explorer.mjs";
import { renderPeriodicTable, ELEMENT_BY_SYMBOL } from "./ptable.mjs";

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const DEFAULTS = { query: "", elements: [], elementMode: "all", dimension: "all", software: "all", type: "all", methods: [], gapMin: null, gapMax: null, inputs: "all", sort: "material", dir: "asc", page: 1, size: PAGE_SIZES[0] };
const state = { mode: "materials", calculations: [], sets: [], facts: [], ...structuredClone(DEFAULTS), columns: storedColumns(), currentRecord: null, returnHash: "#/materials", savedScroll: null };
let bySet = new Map();
let elements = [];
let linked = new Map();
let searchCorpus = new Map();
let searchIndex = new Map();
let searchTimer = null;
let gapTimer = null;
let gapCatalog, comparison;

function storedColumns() {
  try {
    const saved = JSON.parse(localStorage.getItem("librpa-columns") || "null");
    if (Array.isArray(saved) && saved.every(key => COLUMNS.some(column => column.key === key))) return saved;
  } catch { /* storage unavailable */ }
  return [...DEFAULT_COLUMNS];
}

function buildIndexes() {
  bySet = new Map(state.sets.map(set => [set.id, set]));
  elements = [...new Set([...state.sets.map(s => s.element), ...state.calculations.flatMap(recordElements)])].sort();
  const basisOf = new Map();
  for (const record of state.calculations) {
    const ids = new Set([...(record.species || []), ...(record.basis_candidates || [])].map(s => s.set_id).filter(Boolean));
    basisOf.set(record.id, [...ids].map(id => bySet.get(id)).filter(Boolean));
    for (const id of ids) { if (!linked.has(id)) linked.set(id, []); linked.get(id).push(record); }
  }
  for (const record of state.calculations) searchCorpus.set(record.id, materialSearchText(record, basisOf.get(record.id)));
  for (const set of state.sets) searchCorpus.set(`basis:${set.id}`, basisSearchText(set, linked.get(set.id)));
  searchIndex = new Map();
  for (const [id, text] of searchCorpus) {
    for (const token of new Set(normalizeSearchText(text).split(/\s+/u).filter(Boolean))) {
      if (!searchIndex.has(token)) searchIndex.set(token, new Set());
      searchIndex.get(token).add(id);
    }
  }
  state.facts = state.calculations.map(recordFacts);
  gapCatalog = gapInventory(state.calculations);
}

// Ids matching the free-text query, or null when there is no query. An exact
// element symbol matches by composition; whole indexed tokens use the inverted
// index; anything else falls back to the field-scoped substring search.
function queryIds(isBasis) {
  const query = state.query.trim();
  if (!query) return null;
  const pool = isBasis ? state.sets : state.calculations;
  const exactElement = elements.find(element => element.toLowerCase() === query.toLowerCase());
  if (exactElement) return new Set(pool.filter(item => isBasis ? item.element === exactElement : recordElements(item).includes(exactElement)).map(item => item.id));
  const tokens = normalizeSearchText(query).split(/\s+/u).filter(Boolean);
  if (tokens.length && tokens.every(token => searchIndex.has(token))) {
    let matching = new Set(searchIndex.get(tokens[0]));
    for (const token of tokens.slice(1)) matching = new Set([...matching].filter(id => searchIndex.get(token).has(id)));
    return new Set([...matching].filter(id => isBasis === id.startsWith("basis:")).map(id => isBasis ? id.slice(6) : id));
  }
  return new Set(pool.filter(item => matchesSearch(searchCorpus.get(isBasis ? `basis:${item.id}` : item.id) || "", query)).map(item => item.id));
}

function criteria() {
  return { elements: state.elements, elementMode: state.elementMode, dimension: state.dimension, software: state.software, type: state.type, methods: state.methods, gapMin: state.gapMin, gapMax: state.gapMax, inputs: state.inputs };
}

function filterOptions() {
  const ids = queryIds(false);
  return { queryMatch: ids ? facts => ids.has(facts.id) : null };
}

function filteredFacts() {
  return sortFacts(filterFacts(state.facts, criteria(), filterOptions()), state.sort, state.dir);
}

function filteredSets() {
  const ids = queryIds(true);
  return state.sets
    .filter(set => (!ids || ids.has(set.id)) && (!state.elements.length || state.elements.includes(set.element)))
    .sort((a, b) => a.element.localeCompare(b.element) || (a.family || "").localeCompare(b.family || "") || a.id.localeCompare(b.id));
}

// A basis is identified by what it contains, not by the hash suffix on its id.
// The label is derived by scripts/basis_labels.py from the payload bytes: the
// valence electron count, the orbital and auxiliary dimensions, and what the
// set has already produced. Anything missing falls back to the raw record
// rather than to a blank cell, so a stale catalog is visible instead of silent.
function basisFacts(set) {
  const label = set.label;
  if (!label) return { valence: "—", orbital: "—", auxiliary: "—", usage: "" };
  const orbital = label.orbital ? `${esc(label.orbital.shells)} · ${label.orbital.dimension_per_atom}/atom` : "—";
  const auxiliary = label.auxiliary ? `${esc(label.auxiliary.shells)} · ${label.auxiliary.dimension_per_atom}/atom` : "no auxiliary basis";
  const usage = (label.uses || [])
    .map(use => `${esc(use.material || use.record_id)}${use.result ? ` ${esc(use.result)}` : ""}`)
    .join("; ");
  return {
    valence: label.valence_electrons === null || label.valence_electrons === undefined ? "—" : esc(String(label.valence_electrons)),
    orbital,
    auxiliary,
    usage,
  };
}

function basisRow(set) {
  const payloads = (set.files || []).filter(f => ["pp", "nao", "for_aux", "abf"].includes(f.role));
  const roles = [...new Set(payloads.map(f => f.role))].map(role => `<span class="asset-role">${esc(role.toUpperCase())}</span>`).join("");
  const facts = basisFacts(set);
  const usage = facts.usage ? `<span class="table-description">${facts.usage}</span>` : '<span class="not-reported">no calculation yet</span>';
  return `<tr class="basis-row"><th scope="row" data-label="Element"><a class="material-link" href="#/basis/${encodeURIComponent(set.id)}">${esc(set.element)}</a><span class="table-description">${esc(set.family || "Basis family")}</span></th><td class="basis-facts" data-label="What it contains"><span class="basis-fact">${facts.valence} valence electrons</span><span class="basis-fact">NAO ${facts.orbital}</span><span class="basis-fact">ABF ${facts.auxiliary}</span></td><td class="basis-usage" data-label="What it produced">${usage}</td><td data-label="Assets"><div class="method-list">${roles}</div></td><td class="numeric" data-label="Linked calculations">${(linked.get(set.id) || []).length}</td><td class="open-cell"><a href="#/basis/${encodeURIComponent(set.id)}" aria-label="Open basis set ${esc(set.element)} ${esc(set.family || "")}">↗</a></td></tr>`;
}

function renderStats() {
  const materials = new Set(state.calculations.map(record => record.material)).size;
  const covered = new Set(state.calculations.flatMap(recordElements)).size;
  const values = [[state.calculations.length, "Calculations"], [materials, "Materials"], [covered, "Elements"], [state.sets.length, "Basis sets"]];
  $("#stats").innerHTML = values.map(([value, label]) => `<div><strong>${value}</strong><span>${label}</span></div>`).join("");
}

function renderFacets() {
  const counts = facetCounts(state.facts, criteria(), filterOptions());
  const show = (attribute, map) => $$(`[${attribute}]`).forEach(node => { node.textContent = map.get(node.getAttribute(attribute)) || 0; });
  show("data-dimension-count", counts.dimension);
  show("data-software-count", counts.software);
  show("data-type-count", counts.type);
  show("data-method-count", counts.methods);
  return counts;
}

function renderPeriodic(counts) {
  const basis = state.mode === "basis";
  const tally = new Map();
  if (basis) for (const set of state.sets) tally.set(set.element, (tally.get(set.element) || 0) + 1);
  const available = new Set(basis ? state.sets.map(set => set.element) : elements);
  $("#periodic-table").innerHTML = renderPeriodicTable({ counts: basis ? tally : counts.elements, selected: new Set(state.elements), available, noun: basis ? "basis set" : "record" });
  $("#element-chips").innerHTML = state.elements.length
    ? state.elements.map(symbol => `<button type="button" class="element-pill" data-remove-element="${esc(symbol)}" aria-label="Remove ${esc(ELEMENT_BY_SYMBOL.get(symbol)?.name || symbol)} filter">${esc(symbol)} <span aria-hidden="true">×</span></button>`).join("") + '<button type="button" class="text-button" id="clear-elements">Clear</button>'
    : `<span class="element-empty">${basis ? "No element selected — showing every basis set." : "No element selected — showing every composition."}</span>`;
  $("#element-mode").hidden = basis;
  $("#ptable-hint").textContent = basis ? "Select elements to list their basis sets; shading shows how many sets each element has." : "Select elements to filter; shading shows how many records contain each element.";
}

function activeFilterChips() {
  const chips = [];
  const add = (key, label, value = "") => chips.push(`<button type="button" class="filter-chip" data-clear="${key}"${value ? ` data-value="${esc(value)}"` : ""}>${label} <span aria-hidden="true">×</span><span class="sr-only">Remove filter</span></button>`);
  if (state.query) add("query", `“${esc(state.query)}”`);
  if (state.elements.length && state.mode === "materials") add("elements", `${state.elementMode === "only" ? "Only" : "Contains"} ${state.elements.map(esc).join(" · ")}`);
  if (state.mode === "materials") {
    if (state.dimension !== "all") add("dimension", state.dimension.toUpperCase());
    if (state.software !== "all") add("software", state.software === "fhi_aims" ? "FHI-aims" : "ABACUS");
    if (state.type !== "all") add("type", esc(RECORD_TYPES.find(type => type.value === state.type)?.label || state.type));
    for (const method of state.methods) add("method", esc(method), method);
    if (state.gapMin !== null || state.gapMax !== null) add("gap", `GW gap ${state.gapMin ?? 0}–${state.gapMax ?? "∞"} eV`);
    if (state.inputs !== "all") add("inputs", state.inputs === "available" ? "Inputs available" : "No inputs");
  }
  return chips.join("");
}

function syncFilters() {
  const basis = state.mode === "basis";
  const gaps = state.mode === "gaps";
  $(".filter-panel").hidden = gaps;
  $(".search-box").hidden = gaps;
  $(".search-examples").hidden = gaps;
  $(".ptable-panel").hidden = gaps;
  $(".search-panel").hidden = gaps;
  $(".dimension-filter").hidden = basis;
  $(".software-filter").hidden = basis;
  for (const selector of [".type-filter", ".method-filter", ".gap-filter", "#input-filter-control"]) $(selector).hidden = basis;
  $("#columns-menu").hidden = basis || gaps;
  $("#export-menu").hidden = basis || gaps;
  $("#search").value = state.query;
  $("#element-filter").value = state.elements.length === 1 ? state.elements[0] : "all";
  $("#input-filter").value = state.inputs;
  $("#gap-min").value = state.gapMin ?? "";
  $("#gap-max").value = state.gapMax ?? "";
  $$("input[name=dimension]").forEach(input => { input.checked = input.value === state.dimension; });
  $$("input[name=software]").forEach(input => { input.checked = input.value === state.software; });
  $$("input[name=type]").forEach(input => { input.checked = input.value === state.type; });
  $$("input[name=method]").forEach(input => { input.checked = state.methods.includes(input.value); });
  $$("input[name=elmode]").forEach(input => { input.checked = input.value === state.elementMode; });
  const options = gaps ? [["result", "Largest selected gap ↓"], ["material", "Material A–Z"]]
    : basis ? [["element", "Element A–Z"]]
    : [["material:asc", "Material A–Z"], ["gw:desc", "GW gap ↓"], ["gw:asc", "GW gap ↑"], ["ks:desc", "KS gap ↓"], ["atoms:desc", "Atoms ↓"], ["id:asc", "Record ID"]];
  $("#sort").innerHTML = options.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
  const current = gaps ? (state.sort === "material" ? "material" : "result") : basis ? "element" : `${state.sort}:${state.dir}`;
  if (!options.some(([value]) => value === current)) $("#sort").insertAdjacentHTML("beforeend", `<option value="${current}">${esc(COLUMNS.find(column => column.sort === state.sort)?.label || state.sort)} ${state.dir === "desc" ? "↓" : "↑"}</option>`);
  $("#sort").value = current;
}

function listHash() {
  let params;
  if (state.mode === "materials") params = writeExplorerParams(state);
  else {
    params = new URLSearchParams();
    if (state.mode === "basis") {
      if (state.query) params.set("q", state.query);
      if (state.elements.length) params.set("el", state.elements.join(","));
      if (state.page > 1) params.set("page", state.page);
    } else {
      params = writeGapParams(comparison);
      if (state.sort === "material") params.set("sort", "material");
    }
  }
  const query = params.toString();
  const prefix = state.mode === "basis" ? "#/basis" : state.mode === "gaps" ? "#/gaps" : "#/materials";
  return `${prefix}${query ? `?${query}` : ""}`;
}

function showView(name) {
  for (const [view, id] of [["landing", "#landing-view"], ["home", "#home-view"], ["detail", "#detail-view"], ["agents", "#agents-view"]]) $(id).hidden = view !== name;
  document.body.classList.toggle("cover-mode", name === "landing");
}

function markNavigation(current) {
  $$("[data-nav]").forEach(a => a.setAttribute("aria-current", a.dataset.nav === current ? "page" : "false"));
}

function renderLanding() {
  showView("landing");
  document.title = "LibRPA materials database";
  document.querySelectorAll("[data-nav]").forEach(a => a.setAttribute("aria-current", "false"));
  window.scrollTo(0, 0);
  document.body.classList.add("cover-mode");
  replayCoverEntrance($("#landing-cover"));
  startCoverCanvas($("#landing-cover"));
}

function renderAgents() {
  showView("agents");
  document.title = "API & agents · LibRPA";
  markNavigation("agents");
  window.scrollTo(0, 0);
  const heading = $("#agents-title");
  heading.tabIndex = -1;
  heading.focus({ preventScroll: true });
}

function renderHistory() {
  let html = "";
  try {
    const viewed = JSON.parse(localStorage.getItem("librpa-history") || "[]");
    const records = viewed.map(id => state.calculations.find(r => r.id === id)).filter(Boolean);
    if (records.length) html = `<div class="history-section"><h3>Recently viewed</h3><ul class="history-list">${records.slice(0, 5).map(r => `<li><a href="#/material/${encodeURIComponent(r.id)}">${esc(r.material)}</a><span>${esc(r.id)}</span></li>`).join("")}</ul></div>`;
  } catch { /* storage unavailable */ }
  let node = $(".sidebar-history");
  if (html && state.mode === "materials") {
    if (!node) { node = document.createElement("div"); node.className = "sidebar-history"; $(".sidebar-link").before(node); }
    node.innerHTML = html;
  } else node?.remove();
}

function paginate(total) {
  const pages = Math.max(1, Math.ceil(total / state.size));
  state.page = Math.min(state.page, pages);
  const start = (state.page - 1) * state.size;
  const sizes = state.mode === "materials" ? `<label class="page-size">Rows <select id="page-size">${PAGE_SIZES.map(size => `<option value="${size}"${size === state.size ? " selected" : ""}>${size}</option>`).join("")}</select></label>` : "";
  const html = `<div class="pagination"><span>${total ? start + 1 : 0}–${Math.min(start + state.size, total)} of ${total}</span>${sizes}<div><button type="button" data-page="${state.page - 1}" ${state.page === 1 ? "disabled" : ""} aria-label="Previous page">←</button><span>Page ${state.page} / ${pages}</span><button type="button" data-page="${state.page + 1}" ${state.page === pages ? "disabled" : ""} aria-label="Next page">→</button></div></div>`;
  return { start, html };
}

function renderHome() {
  const basis = state.mode === "basis";
  const gaps = state.mode === "gaps";
  showView("home");
  $("#page-kicker").textContent = basis ? "BASIS LIBRARY" : gaps ? "GAP OVERVIEW" : "MATERIALS EXPLORER";
  $("#page-title").textContent = basis ? "The basis behind each result." : gaps ? "Band gaps, across materials." : "Materials, with evidence.";
  $("#intro-copy").textContent = basis ? "Inspect pseudopotentials, physical orbitals, and auxiliary basis functions — with original files and linked calculations." : gaps ? "Compare calculated gaps for the materials you choose. Use the Kohn–Sham gap as a baseline, compare methods by material, or select a matched experimental measurement." : "Electronic bands, RPA energies, large-system GW results, and reader-format provenance — with original inputs, basis provenance, and evidence.";
  $("#search").placeholder = basis ? "Search element, family, original filename, or linked material" : "Search material, formula, element, or calculation ID";
  $("#catalog-title").textContent = basis ? "Basis-set records" : gaps ? "Gap overview" : "Calculation records";
  $("#catalog-footnote").textContent = basis ? "Open a basis record for readable filenames, downloads, radial functions, and linked calculations." : gaps ? "Use Cite beside a result to copy its record citation and find available sources. A shared material name does not establish the same structure or gap definition." : "One row per calculation. Primary results retain their recorded unit and scope; path-resolved and sampled-grid observables are not presented as global fundamental gaps. A dash means no value is listed. Open a record for source evidence and definitions.";
  markNavigation(state.mode);
  renderHistory();
  $("#catalog").setAttribute("aria-busy", "false");
  $("#gap-controls").hidden = !gaps;
  $("#gap-chart").hidden = !gaps;
  if (gaps) {
    $("#gap-no-measurements").hidden = state.calculations.some(record => Number.isFinite(record.experimental_gap?.value));
    syncGapControls($("#gap-controls"), gapCatalog, comparison);
    const records = selectedGapRecords(gapCatalog, comparison);
    const { counts } = buildGapComparison(records, comparison);
    $("#result-count").textContent = `${counts.rows} calculation record${counts.rows === 1 ? '' : 's'} · ${counts.points} plotted value${counts.points === 1 ? '' : 's'}`;
    $("#active-filters").hidden = true;
    $("#empty").hidden = true;
    $("#catalog").hidden = false;
    renderChart(records);
    $("#catalog").innerHTML = renderGapOverview(records, state.sort, comparison);
    document.title = "Gap overview · LibRPA";
    return;
  }
  const counts = renderFacets();
  renderPeriodic(counts);
  const chips = activeFilterChips();
  $("#active-filters").hidden = !chips;
  $("#active-filters").innerHTML = chips ? `${chips}<button type="button" class="text-button" data-clear="all">Clear all</button>` : "";
  if (basis) {
    const sets = filteredSets();
    const { start, html } = paginate(sets.length);
    $("#result-count").textContent = `${sets.length} of ${state.sets.length} records${state.query ? ` matching “${state.query}”` : ""}`;
    $("#empty").hidden = sets.length > 0;
    $("#catalog").hidden = !sets.length;
    const headings = ["Element / family", "What it contains", "What it produced", "Assets", "Linked", ""];
    $("#catalog").innerHTML = `<div class="table-wrap" tabindex="0" role="region" aria-label="Basis sets"><table class="catalog-table basis-table basis-facts-table"><caption class="sr-only">Basis library</caption><thead><tr>${headings.map(heading => `<th scope="col">${heading || '<span class="sr-only">Open record</span>'}</th>`).join("")}</tr></thead><tbody>${sets.slice(start, start + state.size).map(basisRow).join("")}</tbody></table></div>${html}`;
    document.title = "Basis library · LibRPA";
    return;
  }
  const records = filteredFacts();
  const { start, html } = paginate(records.length);
  $("#result-count").textContent = `${records.length} of ${state.calculations.length} records${state.query ? ` matching “${state.query}”` : ""}`;
  $("#empty").hidden = records.length > 0;
  $("#catalog").hidden = !records.length;
  const columns = visibleColumns(state.columns);
  $("#catalog").innerHTML = `<div class="table-wrap" tabindex="0" role="region" aria-label="Calculation records"><table class="catalog-table"><caption class="sr-only">Materials and evidence-linked electronic-structure results</caption>${renderHeader(columns, state.sort, state.dir)}<tbody>${records.slice(start, start + state.size).map(facts => renderMaterialRow(facts, columns)).join("")}</tbody></table></div>${html}`;
  $("#columns-panel").innerHTML = COLUMNS.filter(column => !column.fixed).map(column => `<label><input type="checkbox" data-column="${column.key}"${state.columns.includes(column.key) ? " checked" : ""}><span>${esc(column.label)}</span></label>`).join("") + '<button type="button" class="text-button" data-columns-reset>Default columns</button>';
  document.title = "Materials · LibRPA";
}

// The chart is drawn at the card's real pixel width so its labels keep their
// set size on every screen; it is redrawn when the window size changes.
function renderChart(records = selectedGapRecords(gapCatalog, comparison)) {
  const card = $("#gap-chart");
  const width = Math.max(300, Math.round(card.getBoundingClientRect().width) - 42);
  card.innerHTML = renderGapChart(records, { ...comparison, width });
}

function updateFilter() {
  state.page = 1;
  renderHome();
  history.replaceState(null, "", listHash());
  state.returnHash = listHash();
}

function resetFilters() {
  Object.assign(state, structuredClone(DEFAULTS), { sort: state.mode === "basis" ? "element" : state.mode === "gaps" ? "gw" : "material" });
  syncFilters();
  updateFilter();
}

function exportResults(kind) {
  const records = filteredFacts();
  const stamp = new Date().toISOString().slice(0, 10);
  const blob = kind === "csv" ? new Blob([factsToCsv(records)], { type: "text/csv;charset=utf-8" }) : new Blob([factsToJson(records)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: `librpa-records-${stamp}.${kind}` });
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

async function copyText(button, text) {
  const original = button.textContent;
  try { await navigator.clipboard.writeText(text); button.textContent = "Copied"; } catch { button.textContent = "Copy failed"; }
  setTimeout(() => { button.textContent = original; }, 1800);
}

async function route() {
  const hash = location.hash || "#/";
  const [path, query] = hash.split("?");
  const params = new URLSearchParams(query);
  const match = path.match(/^#\/(material|basis)\/([^?]+)$/);
  if (match) {
    let id;
    try { id = decodeURIComponent(match[2]); } catch { id = null; }
    const record = (match[1] === "material" ? state.calculations : state.sets).find(r => r.id === id);
    if (!$("#home-view").hidden) state.savedScroll = window.scrollY;
    const cite = match[1] === "material" && params.get("cite") === "1";
    showView("detail");
    state.currentRecord = match[1] === "material" ? record : null;
    if (record && match[1] === "material" && !record.files) {
      $("#detail-view").innerHTML = '<div class="detail-loading"><p>Loading record…</p></div>';
      const path = `../data/calculations/${record.dimension}/${record.material}/${record.id}/record.json`;
      try { const resp = await fetch(path); if (resp.ok) { const fullRecord = await resp.json(); Object.assign(record, fullRecord); } } catch {}
    }
    $("#detail-view").innerHTML = record ? match[1] === "material" ? renderMaterial(record, state.sets, state.calculations, { cite }) : renderBasis(record, state.calculations) : '<div class="empty-panel"><h1>Record not found</h1><p>This ID is not in the public catalog.</p><a href="#/materials">Return to materials</a></div>';
    if (record && match[1] === "material") { try { const viewed = JSON.parse(localStorage.getItem("librpa-history") || "[]"); const idx = viewed.indexOf(record.id); if (idx >= 0) viewed.splice(idx, 1); viewed.unshift(record.id); localStorage.setItem("librpa-history", JSON.stringify(viewed.slice(0, 10))); } catch {} }
    const back = $(".breadcrumb a");
    const canRestore = match[1] === "material" ? ["materials", "gaps"].includes(state.mode) : state.mode === "basis";
    if (back && canRestore) {
      back.href = state.returnHash;
      back.textContent = state.mode === "gaps" ? "Gap overview" : state.mode === "basis" ? "Basis library" : "Materials";
    }
    document.title = `${record?.material || record?.id || "Record not found"} · LibRPA`;
    markNavigation(match[1] === "basis" ? "basis" : state.mode === "gaps" ? "gaps" : "materials");
    window.scrollTo(0, 0);
    const heading = $("#detail-view h1");
    if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
    if (record && cite) {
      const box = $("#record-citation");
      if (box) { box.open = true; box.scrollIntoView({ block: "start" }); box.querySelector("summary").focus({ preventScroll: true }); }
    }
    if (record && match[1] === "basis") $("#detail-view .radial-file[open] [data-radial-load]")?.click();
    return;
  }
  if ((path === "#/" || path === "#" || path === "") && !params.size) { renderLanding(); return; }
  if (path === "#/agents") { renderAgents(); return; }
  state.mode = path === "#/basis" ? "basis" : path === "#/gaps" ? "gaps" : "materials";
  Object.assign(state, readExplorerParams(params, elements));
  if (state.mode === "gaps") {
    comparison = readGapParams(params, gapCatalog);
    state.sort = params.get("sort") === "material" ? "material" : "result";
  }
  if (state.mode === "basis") state.sort = "element";
  state.returnHash = hash;
  syncFilters();
  renderHome();
  if (state.savedScroll !== null) { window.scrollTo(0, state.savedScroll); state.savedScroll = null; }
  const heading = $("#page-title");
  if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
}

function toggleElement(symbol) {
  state.elements = state.elements.includes(symbol) ? state.elements.filter(item => item !== symbol) : [...state.elements, symbol];
  syncFilters();
  updateFilter();
}

function clearFilter(key, value) {
  if (key === "all") { resetFilters(); return; }
  if (key === "query") state.query = "";
  if (key === "elements") state.elements = [];
  if (key === "dimension") state.dimension = "all";
  if (key === "software") state.software = "all";
  if (key === "type") state.type = "all";
  if (key === "method") state.methods = state.methods.filter(method => method !== value);
  if (key === "gap") { state.gapMin = null; state.gapMax = null; }
  if (key === "inputs") state.inputs = "all";
  syncFilters();
  updateFilter();
}

function installExplorer() {
  $("#element-filter").innerHTML = '<option value="all">All elements</option>' + elements.map(e => `<option value="${esc(e)}">${esc(e)} · ${esc(ELEMENT_BY_SYMBOL.get(e)?.name || e)}</option>`).join("");
  $("#search").addEventListener("input", event => { state.query = event.target.value.trim(); clearTimeout(searchTimer); searchTimer = setTimeout(updateFilter, 150); });
  $("#element-filter").addEventListener("change", event => { state.elements = event.target.value === "all" ? [] : [event.target.value]; updateFilter(); });
  $("#input-filter").addEventListener("change", event => { state.inputs = event.target.value; updateFilter(); });
  $("#sort").addEventListener("change", event => {
    const [key, dir] = event.target.value.split(":");
    state.sort = key;
    state.dir = dir || DEFAULT_DIRECTION[key] || "asc";
    updateFilter();
  });
  for (const [name, key] of [["dimension", "dimension"], ["software", "software"], ["type", "type"], ["elmode", "elementMode"]]) {
    $$(`input[name=${name}]`).forEach(input => input.addEventListener("change", event => { state[key] = event.target.value; updateFilter(); }));
  }
  $$("input[name=method]").forEach(input => input.addEventListener("change", () => {
    state.methods = METHOD_FACETS.filter(method => $(`input[name=method][value="${method}"]`).checked);
    updateFilter();
  }));
  for (const [id, key] of [["gap-min", "gapMin"], ["gap-max", "gapMax"]]) {
    $(`#${id}`).addEventListener("input", event => {
      const value = event.target.value.trim() === "" ? null : Number(event.target.value);
      state[key] = Number.isFinite(value) ? value : null;
      clearTimeout(gapTimer);
      gapTimer = setTimeout(updateFilter, 300);
    });
  }
  for (const id of ["reset-filters", "empty-reset"]) $(`#${id}`).addEventListener("click", resetFilters);
  $("#filter-toggle").addEventListener("click", event => {
    const button = event.currentTarget;
    const expanded = button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", String(expanded));
    button.innerHTML = `${expanded ? "Hide" : "Show"} filters <span aria-hidden="true">${expanded ? "−" : "+"}</span>`;
    $(".filter-panel").classList.toggle("filters-expanded", expanded);
  });
  $("#search-examples").addEventListener("click", event => { const button = event.target.closest("[data-query]"); if (button) { state.query = button.dataset.query; $("#search").value = state.query; updateFilter(); } });
  $(".search-panel").addEventListener("click", event => {
    const cell = event.target.closest("[data-element]");
    if (cell) { toggleElement(cell.dataset.element); return; }
    const pill = event.target.closest("[data-remove-element]");
    if (pill) { toggleElement(pill.dataset.removeElement); return; }
    if (event.target.closest("#clear-elements")) { state.elements = []; syncFilters(); updateFilter(); }
  });
  $("#active-filters").addEventListener("click", event => { const chip = event.target.closest("[data-clear]"); if (chip) clearFilter(chip.dataset.clear, chip.dataset.value); });
  $("#columns-panel").addEventListener("change", event => {
    const box = event.target.closest("[data-column]");
    if (!box) return;
    state.columns = COLUMNS.filter(column => column.fixed || $(`[data-column="${column.key}"]`)?.checked).map(column => column.key);
    try { localStorage.setItem("librpa-columns", JSON.stringify(state.columns)); } catch { /* storage unavailable */ }
    renderHome();
  });
  $("#columns-panel").addEventListener("click", event => {
    if (!event.target.closest("[data-columns-reset]")) return;
    state.columns = [...DEFAULT_COLUMNS];
    try { localStorage.removeItem("librpa-columns"); } catch { /* storage unavailable */ }
    renderHome();
  });
  $("#export-menu").addEventListener("click", event => { const button = event.target.closest("[data-export]"); if (button) { exportResults(button.dataset.export); $("#export-menu").open = false; } });
  $("#catalog").addEventListener("click", event => {
    const sortButton = event.target.closest("[data-sort-key]");
    if (sortButton) {
      const key = sortButton.dataset.sortKey;
      state.dir = state.sort === key ? (state.dir === "asc" ? "desc" : "asc") : DEFAULT_DIRECTION[key] || "asc";
      state.sort = key;
      syncFilters();
      updateFilter();
      $(`[data-sort-key="${key}"]`)?.focus();
      return;
    }
    const button = event.target.closest("[data-page]");
    if (button && !button.disabled) {
      state.page = Number(button.dataset.page);
      renderHome();
      history.replaceState(null, "", listHash());
      state.returnHash = listHash();
      const title = $("#catalog-title");
      title.scrollIntoView({ block: "start" });
      title.tabIndex = -1;
      title.focus({ preventScroll: true });
      return;
    }
    // Anywhere on a row opens its record - the catalog table and the Gap
    // overview table share this container. Modified clicks and clicks that land
    // on a real link keep the browser's own behaviour.
    const row = event.target.closest("tr[data-href]");
    if (row && !event.target.closest("a") && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && event.button === 0) {
      location.hash = row.dataset.href;
    }
  });
  $("#catalog").addEventListener("change", event => { if (event.target.id === "page-size") { state.size = Number(event.target.value); updateFilter(); } });
  document.addEventListener("click", event => {
    for (const menu of $$(".toolbar-menu[open]")) if (!menu.contains(event.target)) menu.open = false;
    const copy = event.target.closest("[data-copy]");
    if (copy) copyText(copy, copy.dataset.copy || copy.parentElement.querySelector("code")?.textContent || "");
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") for (const menu of $$(".toolbar-menu[open]")) { menu.open = false; menu.querySelector("summary").focus(); }
    if (event.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) && !$("#home-view").hidden && !$(".search-box").hidden && !$("#file-preview").open) { event.preventDefault(); $("#search").focus(); }
  });
  installGapControls($("#gap-controls"), gapCatalog, () => comparison, updateFilter);
  installGapChartTooltip($("#gap-chart"));

  let resizeTimer = null;
  window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (!$("#gap-chart").hidden) renderChart(); }, 200); });
  // The periodic table remembers whether this viewer keeps it open; without a
  // saved choice it starts closed on narrow screens.
  let saved = null;
  try { saved = localStorage.getItem("librpa-ptable"); } catch { /* storage unavailable */ }
  const panel = $("#ptable-panel");
  panel.open = saved ? saved === "open" : !matchMedia("(max-width: 820px)").matches;
  // Only the reader's own clicks are remembered; the programmatic default above
  // also fires a (queued) toggle event, which must not be stored as a choice.
  panel.querySelector("summary").addEventListener("click", () => setTimeout(() => { try { localStorage.setItem("librpa-ptable", panel.open ? "open" : "closed"); } catch { /* storage unavailable */ } }, 0));
}

async function start() {
  $("#catalog").innerHTML = Array.from({length:8},()=>'<div class="skeleton-row"><div class="skeleton-bar w-25"></div><div class="skeleton-bar w-15"></div><div class="skeleton-bar w-40"></div><div class="skeleton-bar w-30"></div></div>').join("");
  installPreview($("#file-preview"));
  installBlobDownloads();
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
    const [indexResp, calcsResp, setsResp] = await Promise.all([
      fetch("catalog/index.json", { cache: "no-cache" }),
      fetch("catalog/calculations.json", { cache: "no-cache" }),
      fetch("catalog/basis-sets.json", { cache: "no-cache" })
    ]);
    if (!indexResp.ok || !calcsResp.ok || !setsResp.ok) throw new Error("Catalog fetch failed");
    await indexResp.json();
    const calcsData = await calcsResp.json();
    const setsData = await setsResp.json();
    if (!Array.isArray(calcsData.records) || !Array.isArray(setsData.records)) throw new Error("Invalid catalog format");
    state.calculations = calcsData.records;
    state.sets = setsData.records;
    buildIndexes();
    renderStats();
    installExplorer();
    window.addEventListener("hashchange", route);
    installCoverEffects($("#landing-cover"));
    route();
  } catch (error) {
    showView("home");
    $("#result-count").textContent = "Catalog unavailable";
    $("#catalog").setAttribute("aria-busy", "false");
    $("#load-error").hidden = false;
    $("#load-error").textContent = `The catalog could not be loaded (${error.message}). Serve the repository over HTTP, or retry the deployed website. No substitute records are shown.`;
  }
}
start();
