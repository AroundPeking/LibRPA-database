import { publicPath } from "./records.mjs";

const initialCategories = [
  { slug: "electronic", label: "Electronic structure" },
  { slug: "energetic", label: "Energetics" },
  { slug: "performance", label: "Performance" },
  { slug: "topological", label: "Topology" },
  { slug: "optical", label: "Optical" },
  { slug: "magnetic", label: "Magnetic" },
  { slug: "structural", label: "Structural" },
  { slug: "other", label: "Other" },
];

const statusLabels = {
  reported: "Reported",
  validated: "Validated",
  provisional: "Computed",
};

const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

function categoryLabel(slug) {
  return String(slug).replace(/_/g, " ").replace(/^\p{L}/u, letter => letter.toUpperCase());
}

function displayValue(value) {
  if (typeof value === "string") return value;
  if (value === undefined) return "—";
  const result = JSON.stringify(value);
  return result === undefined ? "—" : result;
}

function evidenceLinks(evidence) {
  return (evidence || []).map(path => {
    const file = String(path);
    const name = file.split("/").at(-1);
    const url = publicPath(file);
    return url ? `<a href="${escapeHtml(url)}" title="${escapeHtml(file)}" target="_blank" rel="noopener">${escapeHtml(name)}</a>` : '<span class="muted">Evidence link unavailable</span>';
  }).join(", ") || '<span class="muted">—</span>';
}

export function getPropertyCategories(properties = []) {
  const categories = new Map(initialCategories.map(item => [item.slug, item]));
  for (const property of properties) {
    const slug = property?.category;
    if (typeof slug === "string" && slug && !categories.has(slug)) {
      categories.set(slug, { slug, label: categoryLabel(slug) });
    }
  }
  return [...categories.values()];
}

export function renderPropertyTabs(properties = [], selectedCategory = "electronic") {
  return getPropertyCategories(properties).map(category => {
    const selected = category.slug === selectedCategory;
    return `<button class="property-tab" id="property-tab-${escapeHtml(category.slug)}" type="button" role="tab" aria-selected="${selected}" aria-controls="property-panel" tabindex="${selected ? "0" : "-1"}" data-category="${escapeHtml(category.slug)}">${escapeHtml(category.label)}</button>`;
  }).join("");
}

export function renderPropertyPanel(properties = [], selectedCategory = "electronic") {
  const rows = properties.filter(property => property?.category === selectedCategory && property.status !== "failed");
  if (!rows.length) {
    return '<div class="property-empty"><p>No results reported</p><a href="../CONTRIBUTING.md">Contribute a property</a></div>';
  }
  return `<div class="property-table-wrap"><table class="property-table"><thead><tr><th>Property</th><th>Method</th><th>Value</th><th>Status</th><th>Evidence</th></tr></thead><tbody>${rows.map(property => {
    const definition = property.definition ? `<span class="property-definition">${escapeHtml(property.definition)}</span>` : "";
    const value = displayValue(property.value);
    return `<tr><th scope="row"><span>${escapeHtml(property.label)}</span>${definition}</th><td>${escapeHtml(property.method)}</td><td><span class="property-value">${escapeHtml(value)}</span>${property.unit ? `<span class="property-unit">${escapeHtml(property.unit)}</span>` : ""}</td><td><span class="property-status ${escapeHtml(property.status)}">${escapeHtml(statusLabels[property.status] || property.status || "Unclassified")}</span></td><td class="property-evidence">${evidenceLinks(property.evidence)}</td></tr>`;
  }).join("")}</tbody></table></div>`;
}
