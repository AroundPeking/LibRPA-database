import { filesOf, recordElements, methodNames, recordTypeLabel, workflowFrontend, workflowLabel } from "./records.mjs";

export function normalizeSearchText(value) {
  return String(value ?? "")
    .normalize("NFKC")
    .toLocaleLowerCase("en-US")
    .replace(/[\u2010-\u2015\u2212]/g, "-")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

// Search is deliberately field-scoped: material, formula, id, dimension,
// frontend, record type, elements, the method chips shown in the catalog
// (PBE / EXX / GW / SOC / SPIN), provenance commits, and linked basis
// families. Free-text prose (evidence scopes, notes, hashes) and raw file
// names are excluded so short tokens like "gw" or "spin" match the records
// that carry the label, not every archive note or band-channel suffix.
export function materialSearchText(record, basisSets = []) {
  if (!record) return "";
  return [
    record.material, record.formula, record.id, record.dimension,
    workflowFrontend(record), workflowLabel(record), recordTypeLabel(record),
    ...recordElements(record),
    ...methodNames(record),
    record.spin_orbit === true ? "SOC" : "",
    record.spin_polarized === true ? "SPIN" : "",
    record.source?.commit ?? "", record.source?.archive_commit ?? "",
    ...basisSets.map(set => [set?.element, set?.family, set?.id].filter(Boolean).join(" "))
  ].filter(Boolean).join(" ");
}

export function basisSearchText(set, calculations = []) {
  if (!set) return "";
  return [
    set.element, set.family, set.id, set.notes,
    set.generation_provenance?.commit ?? "",
    ...calculations.map(record => [record?.material, record?.formula, ...methodNames(record), record?.spin_orbit === true ? "SOC" : "", record?.spin_polarized === true ? "SPIN" : ""].filter(Boolean).join(" "))
  ].filter(Boolean).join(" ");
}

// method keywords match whole words only, so "soc" finds the SOC-labelled
// records instead of every id like "..._xsoc_1e-10"
const METHOD_KEYWORDS = new Set(["soc", "spin", "gw", "exx", "pbe", "dft", "rpa"]);

export function matchesSearch(text, query) {
  const raw = String(query ?? "");
  if (!raw.trim()) return true;
  const tokens = normalizeSearchText(raw).split(/\s+/u).filter(Boolean);
  // a query made only of punctuation has nothing to match: show nothing,
  // not everything
  if (!tokens.length) return false;
  const haystack = normalizeSearchText(text);
  const words = new Set(haystack.split(/\s+/u).filter(Boolean));
  return tokens.every(token => METHOD_KEYWORDS.has(token) ? words.has(token) : haystack.includes(token));
}
