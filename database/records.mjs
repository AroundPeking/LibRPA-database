// Shared data interpretation for the list, detail page, and regression tests.
export const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

export function publicPath(path) {
  const parts = String(path || "").split("/");
  if (!parts.length || parts.some(part => !part || part === "." || part === ".." || /[\\\u0000-\u001f]/.test(part)) || /:/.test(parts[0])) return null;
  return "../" + parts.map(encodeURIComponent).join("/");
}

export function safeFilename(name) {
  return typeof name === "string" && name === name.trim() && name && !/[\\/<>:"|?*\u0000-\u001f\u007f]/.test(name) && !name.includes("..") ? name : null;
}

export function fileName(file) {
  for (const name of [file.display_name, file.label]) {
    if (name && name !== "payload") return String(name);
  }
  return String(file.path || "Unknown file").split("/").at(-1);
}

export function downloadName(file) {
  return safeFilename(file.download_name) || safeFilename(file.path?.split("/").at(-1)) || "download";
}

export function filesOf(record, kind) {
  return Array.isArray(record.files?.[kind]) ? record.files[kind] : [];
}

export function restrictedGap(record) {
  return record.status === "path_diagnostic" || /raw[- ]band|frontier|restricted/i.test(record.summary?.observable || "");
}

export function paperGap(record, method = "GW") {
  const paper = record.paper_values;
  const value = paper?.values?.[method];
  const source = paper?.source;
  if (!paper || !source || !/^[0-9a-f]{64}$/i.test(source.document_sha256 || "") ||
      !Number.isInteger(source.pdf_page) || source.pdf_page < 1 || !source.table ||
      !filesOf(record, "results").some(file => file.path === paper.evidence && /^[0-9a-f]{64}$/i.test(file.sha256 || "")) ||
      !value || value.unit !== "eV" || !Number.isFinite(value.value) ||
      !Number.isInteger(value.precision) || value.precision < 0 || value.precision > 8 || !value.column) return null;
  return value;
}

export function bandGap(record, method = "GW") {
  // A cited paper value is displayable even when its archived spectrum is restricted.
  // It does not turn that spectrum into an accepted fundamental gap: archive fallback
  // still enforces the restriction and the UI keeps the scope beside the paper value.
  const paper = paperGap(record, method);
  if (paper) return paper.value;
  return archivedBandGap(record, method);
}

export function archivedBandGap(record, method = "GW") {
  if (method === "GW" && restrictedGap(record)) return null;
  const patterns = { DFT: /^(PBE|DFT|KS)$/i, EXX: /^EXX$/i, GW: /^(G0W0|GW|GW path)$/i };
  const matches = (record.properties || []).filter(p => p.category === "electronic" && /^(?:band_gap|sampled_path_gap(?:_ev)?|path_gap(?:_ev)?)$/.test(p.key || "") && patterns[method]?.test(p.method));
  // Do not silently replace an unvalidated or ambiguous contributed value with a legacy value.
  if (matches.length) {
    return matches.length === 1 && matches[0].unit === "eV" && matches[0].status !== "failed" && typeof matches[0].value === "number" && Number.isFinite(matches[0].value) ? matches[0].value : null;
  }
  const summary = record.summary || {};
  const value = method === "DFT" ? summary.dft_gap_ev ?? summary.pbe_gap_ev : method === "EXX" ? summary.exx_gap_ev : summary.gw_gap_ev;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (method === "GW" && /(?:GW|G0W0).*gap/i.test(summary.observable || "") && summary.unit === "eV" && typeof summary.value === "number" && Number.isFinite(summary.value)) return summary.value;
  return null;
}

export function methodNames(record) {
  const corpus = [...filesOf(record, "results"), ...filesOf(record, "logs")].map(f => `${f.label || ""} ${f.path?.split("/").at(-1)}`).join(" ");
  const props = (record.properties || []).filter(p => p.category === "electronic" && p.status !== "failed").map(p => p.method).join(" ");
  return ["DFT", "EXX", "GW"].filter(method => new RegExp(method === "DFT" ? "(?:^|[^a-z])(?:KS|PBE|DFT)(?:[^a-z]|$)" : method === "GW" ? "(?:^|[^a-z])(?:GW|G0W0)(?:[^a-z]|$)" : "(?:^|[^a-z])EXX(?:[^a-z]|$)", "i").test(`${corpus} ${props}`));
}

export function recordType(record) {
  return ["band", "large_system_gw", "rpa_energy", "reader_conversion"].includes(record?.record_type) ? record.record_type : "band";
}

export function recordTypeLabel(record) {
  return ({ band: "Band structure", large_system_gw: "Large-system GW", rpa_energy: "RPA energy", reader_conversion: "Reader conversion" })[recordType(record)];
}

export function atomCount(record) {
  const value = record?.computational_scale?.atom_count;
  return Number.isInteger(value) && value > 0 ? value : null;
}

function finiteProperty(record, predicate) {
  const matches = (record.properties || []).filter(property => property.status !== "failed" && typeof property.value === "number" && Number.isFinite(property.value) && predicate(property));
  return matches.length === 1 ? matches[0] : null;
}

export function sampledGridGap(record, method = "G0W0") {
  return finiteProperty(record, property => property.category === "electronic" && property.key === "sampled_grid_gap_ev" && property.unit === "eV" && new RegExp(method === "PBE" ? "^(?:PBE|DFT|KS)$" : "^(?:G0W0|GW)$", "i").test(property.method || ""));
}

export function primaryResult(record) {
  const type = recordType(record);
  if (type === "large_system_gw") {
    const property = sampledGridGap(record, "G0W0");
    return property ? { label: "Sampled Γ G0W0 gap", value: property.value, unit: property.unit, scope: property.definition || "Regular-grid Γ-point observable" } : null;
  }
  if (type === "rpa_energy") {
    const property = finiteProperty(record, item => item.key === "rpa_correlation_energy");
    return property ? { label: property.label || "RPA correlation energy", value: property.value, unit: property.unit, scope: property.definition || "" } : null;
  }
  if (type === "reader_conversion") {
    const dimension = record?.computational_scale?.matrix_rows;
    return Number.isInteger(dimension) && dimension > 0 ? { label: "Reader-v1 matrix dimension", value: dimension, unit: "states", scope: "Conversion evidence only; no RPA/GW observable" } : null;
  }
  const value = bandGap(record, "GW");
  if (value !== null) return { label: restrictedGap(record) ? "Path-resolved GW value" : "GW gap", value, unit: "eV", scope: record.summary?.gap_definition || "" };
  for (const method of ["EXX", "DFT"]) {
    const fallback = bandGap(record, method);
    if (fallback !== null) return { label: `${method} gap`, value: fallback, unit: "eV", scope: record.summary?.gap_definition || "" };
  }
  return null;
}

export function performanceSummary(record) {
  const performance = record?.performance;
  if (!performance || typeof performance !== "object") return [];
  const values = [
    ["Wall time", performance.wall_time_seconds, value => {
      const hours = Math.floor(value / 3600);
      const minutes = Math.floor((value % 3600) / 60);
      const seconds = value % 60;
      return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }],
    ["Nodes", performance.nodes, String],
    ["MPI ranks", performance.mpi_ranks, String],
    ["OpenMP threads / rank", performance.omp_threads_per_rank, String],
  ];
  return values.filter(([, value]) => Number.isInteger(value) && value > 0).map(([label, value, format]) => ({ label, value: format(value) }));
}

export function recordElements(record) {
  const elements = new Set([...(record.species || []), ...(record.basis_candidates || [])].map(s => s.element).filter(Boolean));
  for (const element of String(record.formula || record.material || "").match(/[A-Z][a-z]?/g) || []) elements.add(element);
  return [...elements].sort();
}

export function setRelation(record, setId) {
  if ((record.species || []).some(s => s.set_id === setId)) return "Exact binding";
  if ((record.basis_candidates || []).some(s => s.set_id === setId)) return "Candidate only";
  return "Publication link";
}

export function boundFiles(set, species = {}) {
  const counts = new Map();
  for (const f of set.files || []) counts.set(f.role, (counts.get(f.role) || 0) + 1);
  return (set.files || []).map(file => {
    const candidate = counts.get(file.role) === 1 && safeFilename(species.asset_aliases?.[file.role]);
    const suffix = file.path?.match(/\.[^.\/]+$/)?.[0]?.toLowerCase();
    const alias = candidate && suffix && candidate.toLowerCase().endsWith(suffix) && !/^payload\./i.test(candidate) ? candidate : null;
    return alias ? { ...file, display_name: alias, download_name: alias, name_source: "calculation_alias" } : file;
  });
}

export function sizeLabel(bytes) {
  if (typeof bytes !== "number" || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function inputStage(file) {
  const name = String(file.path || "").split("/").at(-1);
  const parts = name.split("__");
  return parts.length > 1 ? parts.slice(0, -1).join(" / ") : "Archived calculation";
}
