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

export function bandGap(record, method = "GW") {
  // A selected raw-state separation must not enter an ordinary GW gap column or sort.
  if (method === "GW" && restrictedGap(record)) return null;
  const patterns = { DFT: /^(PBE|DFT|KS)$/i, EXX: /^EXX$/i, GW: /^(G0W0|GW|GW path)$/i };
  const matches = (record.properties || []).filter(p => p.category === "electronic" && p.key === "band_gap" && patterns[method]?.test(p.method));
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
  const corpus = filesOf(record, "results").map(f => `${f.label || ""} ${f.path?.split("/").at(-1)}`).join(" ");
  const props = (record.properties || []).filter(p => p.category === "electronic" && p.status !== "failed").map(p => p.method).join(" ");
  return ["DFT", "EXX", "GW"].filter(method => new RegExp(method === "DFT" ? "(?:^|[^a-z])(?:KS|PBE|DFT)(?:[^a-z]|$)" : method === "GW" ? "(?:^|[^a-z])(?:GW|G0W0)(?:[^a-z]|$)" : "(?:^|[^a-z])EXX(?:[^a-z]|$)", "i").test(`${corpus} ${props}`));
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
  if (typeof bytes !== "number" || bytes < 0) return "Size not recorded";
  if (bytes < 1024) return `${bytes} B`;
  return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function inputStage(file) {
  const name = String(file.path || "").split("/").at(-1);
  const parts = name.split("__");
  return parts.length > 1 ? parts.slice(0, -1).join(" / ") : "Archived calculation";
}
