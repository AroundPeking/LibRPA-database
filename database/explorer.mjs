// Materials-explorer logic shared by the catalog page and its regression
// tests: per-record facts, faceted filtering, sorting, table columns, CSV and
// JSON export, and the URL state of a search. Everything here is pure.
import { esc, formulaHtml, recordElements, methodNames, methodTag, recordType, recordTypeLabel, workflowFrontend, workflowLabel, atomCount, primaryResult } from "./records.mjs";
import { gapOverview } from "./gaps.mjs";

export const SITE_ROOT = "https://aroundpeking.github.io/LibRPA-database";

export const RECORD_TYPES = [
  { value: "band", label: "Band structure" },
  { value: "large_system_gw", label: "Large-system GW" },
  { value: "rpa_energy", label: "RPA energy" },
  { value: "reader_conversion", label: "Reader conversion" },
];

// Method facets are the chips a row shows; the mean-field functional is left
// out because nearly every record carries one.
export const METHOD_FACETS = ["GW", "EXX", "RPA", "Delta-ST", "SPIN", "SOC"];

export function fileCount(record, kind) {
  if (Array.isArray(record?.files?.[kind])) return record.files[kind].length;
  const counted = record?._file_counts?.[kind];
  return typeof counted === "number" ? counted : 0;
}

export function recordMethods(record) {
  const chips = [...methodNames(record)];
  if (record?.spin_polarized === true) chips.push("SPIN");
  if (record?.spin_orbit === true) chips.push("SOC");
  return [...new Set(chips)];
}

export function recordJsonUrl(record) {
  const parts = ["data", "calculations", record.dimension, record.material, record.id, "record.json"];
  return `${SITE_ROOT}/${parts.map(encodeURIComponent).join("/")}`;
}

export function recordPageUrl(record) {
  return `${SITE_ROOT}/database/#/material/${encodeURIComponent(record.id)}`;
}

// The values a row shows, derived once per record from the shared readers so
// the table, the export, and the record page never disagree.
export function recordFacts(record) {
  const gaps = gapOverview(record);
  return {
    id: record.id,
    material: record.material,
    formula: record.formula || record.material,
    dimension: record.dimension,
    frontend: workflowFrontend(record),
    workflow: workflowLabel(record),
    type: recordType(record),
    typeLabel: recordTypeLabel(record),
    methods: recordMethods(record),
    elements: recordElements(record),
    atoms: atomCount(record),
    ks: gaps?.ks ?? null,
    exx: gaps?.exx ?? null,
    gw: gaps?.gw ?? null,
    gapScope: gaps?.scope ?? null,
    primary: primaryResult(record),
    inputs: fileCount(record, "inputs"),
    recordUrl: recordJsonUrl(record),
    pageUrl: recordPageUrl(record),
  };
}

export const DEFAULT_CRITERIA = Object.freeze({
  query: "", elements: [], elementMode: "all", dimension: "all", software: "all",
  type: "all", methods: [], gapMin: null, gapMax: null, inputs: "all",
});

// "all" keeps records that contain every selected element; "only" keeps the
// exact chemical system, as a periodic-table search usually means it.
export function matchesElements(elements, selected, mode = "all") {
  if (!selected.length) return true;
  const present = new Set(elements);
  if (!selected.every(symbol => present.has(symbol))) return false;
  return mode !== "only" || present.size === new Set(selected).size;
}

export function matchesCriteria(facts, criteria, { skip = null, queryMatch = null } = {}) {
  const c = { ...DEFAULT_CRITERIA, ...criteria };
  if (skip !== "query" && queryMatch && !queryMatch(facts)) return false;
  if (skip !== "elements" && !matchesElements(facts.elements, c.elements, c.elementMode)) return false;
  if (skip !== "dimension" && c.dimension !== "all" && facts.dimension !== c.dimension) return false;
  if (skip !== "software" && c.software !== "all" && facts.frontend !== c.software) return false;
  if (skip !== "type" && c.type !== "all" && facts.type !== c.type) return false;
  if (skip !== "methods" && !c.methods.every(method => facts.methods.includes(method))) return false;
  if (skip !== "gap" && (c.gapMin !== null || c.gapMax !== null)) {
    // A range asks about the GW gap; records that list none cannot satisfy it.
    if (facts.gw === null) return false;
    if (c.gapMin !== null && facts.gw < c.gapMin) return false;
    if (c.gapMax !== null && facts.gw > c.gapMax) return false;
  }
  if (skip !== "inputs" && c.inputs !== "all" && (facts.inputs > 0) !== (c.inputs === "available")) return false;
  return true;
}

export function filterFacts(allFacts, criteria, options = {}) {
  return allFacts.filter(facts => matchesCriteria(facts, criteria, options));
}

function tally(allFacts, criteria, options, skip, keysOf) {
  const counts = new Map([["all", 0]]);
  for (const facts of allFacts) {
    if (!matchesCriteria(facts, criteria, { ...options, skip })) continue;
    counts.set("all", counts.get("all") + 1);
    for (const key of keysOf(facts)) counts.set(key, (counts.get(key) || 0) + 1);
  }
  return counts;
}

// Each facet counts what selecting that option would show next to the other
// active filters. Methods narrow with AND, so their counts keep every filter.
export function facetCounts(allFacts, criteria, options = {}) {
  return {
    dimension: tally(allFacts, criteria, options, "dimension", facts => [facts.dimension]),
    software: tally(allFacts, criteria, options, "software", facts => [facts.frontend]),
    type: tally(allFacts, criteria, options, "type", facts => [facts.type]),
    methods: tally(allFacts, criteria, options, null, facts => facts.methods),
    elements: tally(allFacts, criteria, options, "elements", facts => facts.elements),
  };
}

const SORT_READERS = {
  material: facts => facts.material,
  id: facts => facts.id,
  workflow: facts => facts.workflow,
  type: facts => facts.typeLabel,
  atoms: facts => facts.atoms,
  ks: facts => facts.ks,
  exx: facts => facts.exx,
  gw: facts => facts.gw,
  inputs: facts => facts.inputs,
};

export const SORT_KEYS = Object.keys(SORT_READERS);
export const DEFAULT_DIRECTION = { material: "asc", id: "asc", workflow: "asc", type: "asc", atoms: "desc", ks: "desc", exx: "desc", gw: "desc", inputs: "desc" };

// Missing values always sort last, in either direction; ties fall back to
// material and then id so every ordering is total and stable.
export function sortFacts(list, key = "material", direction = DEFAULT_DIRECTION[key] || "asc") {
  const read = SORT_READERS[key] || SORT_READERS.material;
  const sign = direction === "desc" ? -1 : 1;
  return [...list].sort((a, b) => {
    const x = read(a);
    const y = read(b);
    const xMissing = x === null || x === undefined;
    const yMissing = y === null || y === undefined;
    if (xMissing !== yMissing) return xMissing ? 1 : -1;
    if (!xMissing) {
      const order = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      if (order) return sign * order;
    }
    return a.material.localeCompare(b.material) || a.id.localeCompare(b.id);
  });
}

const gapPrecision = facts => facts.gapScope === "sampled" ? 5 : 3;
const missing = '<span class="not-reported">—</span>';
const gapCell = (key, label) => facts => {
  const value = facts[key];
  return `<td class="numeric${key === "gw" ? " gw-value" : ""}" data-label="${label}">${value === null ? missing : value.toFixed(gapPrecision(facts))}</td>`;
};

function primaryCell(facts) {
  const primary = facts.primary;
  if (!primary) return `<td class="primary-result" data-label="Primary result">${missing}</td>`;
  const precision = facts.type === "large_system_gw" || facts.type === "reader_conversion" ? 5 : 3;
  const value = typeof primary.value === "number" ? primary.value.toFixed(precision) : esc(primary.value);
  return `<td class="primary-result" data-label="Primary result"><strong>${value}${primary.unit ? ` <small>${esc(primary.unit)}</small>` : ""}</strong><span class="table-description">${esc(primary.label)}</span></td>`;
}

export const COLUMNS = [
  { key: "material", label: "Material", sort: "material", fixed: true },
  { key: "workflow", label: "Workflow", sort: "workflow", visible: true },
  { key: "type", label: "Record type", sort: "type", visible: false },
  { key: "scale", label: "Scale", sort: "atoms", visible: true },
  { key: "methods", label: "Methods", visible: true },
  { key: "ks", label: "KS gap (eV)", sort: "ks", numeric: true, visible: true },
  { key: "exx", label: "EXX gap (eV)", sort: "exx", numeric: true, visible: false },
  { key: "gw", label: "GW gap (eV)", sort: "gw", numeric: true, visible: false },
  { key: "primary", label: "Primary result", visible: true },
  { key: "elements", label: "Elements", visible: false },
];

export const DEFAULT_COLUMNS = COLUMNS.filter(column => column.fixed || column.visible).map(column => column.key);

const CELLS = {
  material: (facts, url) => `<th scope="row" data-label="Material"><a class="material-link" href="${url}">${formulaHtml(facts.material)}</a><span class="table-description record-id">${esc(facts.id)}</span></th>`,
  workflow: facts => `<td data-label="Workflow"><span class="record-type-tag">${esc(facts.workflow)}</span></td>`,
  type: facts => `<td data-label="Record type"><span class="type-tag">${esc(facts.typeLabel)}</span></td>`,
  scale: facts => `<td data-label="Scale"><span class="dimension-tag">${esc(String(facts.dimension).toUpperCase())}</span>${facts.atoms ? `<span class="table-description">${facts.atoms} atoms</span>` : ""}</td>`,
  methods: facts => `<td data-label="Methods"><div class="method-list">${facts.methods.map(methodTag).join("") || missing}</div></td>`,
  ks: gapCell("ks", "KS gap (eV)"),
  exx: gapCell("exx", "EXX gap (eV)"),
  gw: gapCell("gw", "GW gap (eV)"),
  primary: primaryCell,
  elements: facts => `<td data-label="Elements"><div class="element-list">${facts.elements.map(symbol => `<span class="element-chip">${esc(symbol)}</span>`).join("")}</div></td>`,
};

export function visibleColumns(keys = DEFAULT_COLUMNS) {
  const wanted = new Set(keys);
  return COLUMNS.filter(column => column.fixed || wanted.has(column.key));
}

export function renderHeader(columns, sort, direction) {
  const cells = columns.map(column => {
    if (!column.sort) return `<th scope="col"${column.numeric ? ' class="numeric"' : ""}>${esc(column.label)}</th>`;
    const active = column.sort === sort;
    const state = active ? (direction === "desc" ? "descending" : "ascending") : "none";
    const arrow = active ? (direction === "desc" ? "↓" : "↑") : "↕";
    return `<th scope="col" aria-sort="${state}"${column.numeric ? ' class="numeric"' : ""}><button type="button" class="sort-button${active ? " is-active" : ""}" data-sort-key="${column.sort}">${esc(column.label)}<span aria-hidden="true">${arrow}</span></button></th>`;
  }).join("");
  // No trailing "open record" column: the row itself opens the record, so a
  // header over an arrow that no longer exists would be an empty cell.
  return `<thead><tr>${cells}</tr></thead>`;
}

export function renderMaterialRow(facts, columns) {
  const url = `#/material/${encodeURIComponent(facts.id)}`;
  // The whole row is the target: data-href lets the catalog delegate one click
  // handler instead of asking the reader to aim at a trailing arrow. The
  // material cell keeps a real link, so keyboard and middle-click still work.
  return `<tr class="material-row" data-href="${url}">${columns.map(column => CELLS[column.key](facts, url)).join("")}</tr>`;
}

export const EXPORT_FIELDS = [
  ["id", facts => facts.id],
  ["material", facts => facts.material],
  ["formula", facts => facts.formula],
  ["dimension", facts => facts.dimension],
  ["workflow", facts => facts.workflow],
  ["record_type", facts => facts.type],
  ["methods", facts => facts.methods.join(" ")],
  ["elements", facts => facts.elements.join(" ")],
  ["atoms", facts => facts.atoms],
  ["ks_gap_ev", facts => facts.ks],
  ["exx_gap_ev", facts => facts.exx],
  ["gw_gap_ev", facts => facts.gw],
  ["gap_scope", facts => facts.gapScope],
  ["primary_result", facts => facts.primary?.label],
  ["primary_value", facts => facts.primary?.value],
  ["primary_unit", facts => facts.primary?.unit],
  ["input_files", facts => facts.inputs],
  ["record_json", facts => facts.recordUrl],
  ["page", facts => facts.pageUrl],
];

// Spreadsheet applications execute cells that start with = + - @; text cells
// get a leading apostrophe, numbers are written as they are.
export function csvCell(value) {
  if (value === null || value === undefined) return "";
  let text = String(value);
  if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function factsToCsv(list) {
  const rows = [EXPORT_FIELDS.map(([name]) => name).join(",")];
  for (const facts of list) rows.push(EXPORT_FIELDS.map(([, read]) => csvCell(read(facts))).join(","));
  return `${rows.join("\r\n")}\r\n`;
}

export function factsToJson(list) {
  const records = list.map(facts => Object.fromEntries(EXPORT_FIELDS.map(([name, read]) => [name, read(facts) ?? null])));
  return `${JSON.stringify({ source: `${SITE_ROOT}/database/`, note: "Gap values keep each record's own definition and scope; open record_json for evidence.", count: records.length, records }, null, 2)}\n`;
}

const listParam = value => String(value || "").split(",").map(item => item.trim()).filter(Boolean);
const numberParam = value => {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

export const PAGE_SIZES = [20, 50, 100];

// URL state of a materials search. Unknown values fall back to defaults, so a
// hand-edited or stale link never produces an impossible filter.
export function readExplorerParams(params, knownElements = []) {
  const known = new Set(knownElements);
  const elements = [...new Set([...listParam(params.get("el")), ...listParam(params.get("element"))])].filter(symbol => known.has(symbol));
  const types = RECORD_TYPES.map(type => type.value);
  const legacySort = params.get("sort") === "result" ? "gw" : params.get("sort");
  const sort = SORT_KEYS.includes(legacySort) ? legacySort : "material";
  const size = Number.parseInt(params.get("size"), 10);
  return {
    query: params.get("q") || "",
    elements,
    elementMode: params.get("elmode") === "only" ? "only" : "all",
    dimension: ["2d", "3d"].includes(params.get("dim")) ? params.get("dim") : "all",
    software: ["all", "abacus", "fhi_aims"].includes(params.get("sw")) ? params.get("sw") : "all",
    type: types.includes(params.get("type")) ? params.get("type") : "all",
    methods: listParam(params.get("methods")).filter(method => METHOD_FACETS.includes(method)),
    gapMin: numberParam(params.get("gmin")),
    gapMax: numberParam(params.get("gmax")),
    inputs: ["available", "missing"].includes(params.get("inputs")) ? params.get("inputs") : "all",
    sort,
    dir: ["asc", "desc"].includes(params.get("dir")) ? params.get("dir") : DEFAULT_DIRECTION[sort],
    page: Math.max(1, Number.parseInt(params.get("page"), 10) || 1),
    size: PAGE_SIZES.includes(size) ? size : PAGE_SIZES[0],
  };
}

export function writeExplorerParams(state) {
  const params = new URLSearchParams();
  const put = (key, value, fallback) => { if (value !== fallback && value !== null && value !== "") params.set(key, value); };
  put("q", state.query, "");
  put("el", (state.elements || []).join(","), "");
  put("elmode", state.elementMode, "all");
  put("dim", state.dimension, "all");
  put("sw", state.software, "all");
  put("type", state.type, "all");
  put("methods", (state.methods || []).join(","), "");
  put("gmin", state.gapMin === null || state.gapMin === undefined ? null : String(state.gapMin), "");
  put("gmax", state.gapMax === null || state.gapMax === undefined ? null : String(state.gapMax), "");
  put("inputs", state.inputs, "all");
  put("sort", state.sort, "material");
  put("dir", state.dir, DEFAULT_DIRECTION[state.sort] || "asc");
  put("page", String(state.page), "1");
  put("size", String(state.size), String(PAGE_SIZES[0]));
  return params;
}
