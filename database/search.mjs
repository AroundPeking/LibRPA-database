export function normalizeSearchText(value) {
  return String(value ?? "")
    .normalize("NFKC")
    .toLocaleLowerCase("en-US")
    .replace(/[\u2010-\u2015\u2212]/g, "-")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

export function matchesSearch(record, query) {
  const tokens = normalizeSearchText(query).split(/\s+/u).filter(Boolean);
  if (!tokens.length) return true;
  const values = [];
  const visit = value => {
    if (typeof value === "string" || typeof value === "number") values.push(value);
    else if (Array.isArray(value)) value.forEach(visit);
    else if (value && typeof value === "object") Object.values(value).forEach(visit);
  };
  visit(record);
  const corpus = normalizeSearchText(values.join(" "));
  return tokens.every(token => corpus.includes(token));
}
