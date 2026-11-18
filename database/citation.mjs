import { esc, filesByPath, fileUrl, publicPath } from "./records.mjs";
import { recordPageUrl, recordJsonUrl } from "./explorer.mjs";
import { buildGapComparison, gapMethods } from "./gap-data.mjs";

// Keep citation data as text. Escape for BibTeX and HTML at their respective
// boundaries, not when assembling plain-text titles or publication metadata.
const bibChar = { "\\": "\\textbackslash{}", "~": "\\textasciitilde{}", "^": "\\textasciicircum{}" };
const bibText = value => String(value).replace(/[\\~^{}&%$#_]/g, c => bibChar[c] ?? `\\${c}`);
export function recordCitation(record) {
  const url = recordPageUrl(record);
  const title = `${record.material} — LibRPA Materials Database`;
  const note = `Calculation record: ${record.id}`;
  // A database record is not the publication that reports a result. No record
  // authorship or publication year is declared in the current record schema.
  return {
    text: `${title}. ${note}. ${url}`,
    bibtex: `@misc{librpa-${record.id.replace(/[^a-zA-Z0-9:._-]+/g, "-")},\n  title = {{${bibText(title)}}},\n  note  = {${bibText(note)}},\n  url   = {${url}}\n}`,
  };
}

export function paperEvidenceUrl(record) {
  const path = record.paper_values?.evidence;
  const file = filesByPath(record).get(path);
  // A compact catalog entry has the identity path, but no payload URL. In
  // particular, that path need not exist locally for a referenced-tier file.
  return file ? fileUrl(file) : null;
}

function originalSources(record) {
  const paper = record.paper_values?.source;
  const pub = record.publication;
  const source = record.source || {};
  const paragraphs = [];
  if (paper?.title) {
    const doi = /^10\.\d{4,9}\/[^\s]+$/i.test(paper.doi || "") ? `https://doi.org/${paper.doi.split("/").map(encodeURIComponent).join("/")}` : null;
    const evidence = paperEvidenceUrl(record);
    paragraphs.push(`<p><strong>Source of the reported values:</strong> <cite>${esc(paper.title)}</cite>${paper.table ? `, Table ${esc(paper.table)}` : ""}${paper.pdf_page ? `, PDF p. ${esc(paper.pdf_page)}` : ""}.${doi ? ` <a href="${esc(doi)}" target="_blank" rel="noopener">DOI: ${esc(paper.doi)}</a>.` : ""}${evidence ? ` <a href="${esc(evidence)}" target="_blank" rel="noopener">View source extract ↗</a>` : ""}</p>`);
  }
  if (record.experimental_gap) {
    const methods = gapMethods([record]).map(method => method.key);
    const { points } = buildGapComparison([record], { axis: "experiment", methods });
    if (points.length) {
      const { definition, href, source: measurement } = points[0].reference;
      const series = points.map(point => point.method.label).join(", ");
      paragraphs.push(`<p><strong>Experimental measurement (matched to ${esc(series)}):</strong> <a href="${esc(href)}" target="_blank" rel="noopener"><cite>${esc(measurement.citation)}</cite></a>, ${esc(measurement.locator)}. Gap definition: ${esc(definition)}</p>`);
    }
  }
  if (pub?.manuscript_id) {
    paragraphs.push(`<p><strong>Supporting data:</strong> ${esc(pub.note || pub.manuscript_id)}${source.tar ? ` Archive: <code>${esc(source.tar)}</code>.` : ""}</p>`);
  }
  // Link to the source archive, not the repository for a calculation program.
  if (/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/.test(source.repository || "")) {
    const commit = /^[a-f\d]{40}$/i.test(source.archive_commit || "") ? source.archive_commit : null;
    const path = publicPath(source.archive_directory);
    const url = source.repository.replace(/\/$/, "") + (commit ? `/tree/${commit}${path ? `/${path.slice(3)}` : ""}` : "");
    paragraphs.push(`<p><a href="${esc(url)}" target="_blank" rel="noopener">Original calculation archive ↗</a>${commit ? ` · revision <code>${esc(commit.slice(0, 12))}</code>` : ""}</p>`);
  }
  return paragraphs.length ? `<h3 class="subheading">Original sources</h3><p>Cite the source separately when using its results.</p>${paragraphs.join("")}` : "";
}

const modes = [["text", "Plain text"], ["bibtex", "BibTeX"]];
export function citationBox(record, open = false) {
  const citation = recordCitation(record);
  const tabs = modes.map(([mode, label], index) => `<button type="button" class="citation-tab" role="tab" id="cite-tab-${mode}" aria-controls="cite-panel-${mode}" aria-selected="${index === 0}" tabindex="${index === 0 ? 0 : -1}" data-citation="${mode}">${label}</button>`).join("");
  const panels = modes.map(([mode, label], index) => `<div id="cite-panel-${mode}" role="tabpanel" aria-labelledby="cite-tab-${mode}"${index ? " hidden" : ""}><textarea class="citation-text" rows="${index ? 6 : 3}" aria-label="${label} record citation" readonly data-citation-content="${mode}">${esc(citation[mode])}</textarea></div>`).join("");
  return `<details class="citation-box" id="record-citation"${open ? " open" : ""}><summary>Cite this record</summary><div class="citation-body"><p>Use this citation to identify the exact calculation in the database.</p><div class="citation-tabs" role="tablist" aria-label="Record citation format">${tabs}</div>${panels}<button type="button" class="citation-copy" data-citation-copy>Copy citation</button> <span role="status" data-citation-status></span><p><a href="${esc(recordPageUrl(record))}">Record permalink</a> · <a href="${esc(recordJsonUrl(record))}">Record JSON</a></p>${originalSources(record)}</div></details>`;
}

function activateTab(box, tab) {
  for (const button of box.querySelectorAll(".citation-tab")) {
    button.setAttribute("aria-selected", String(button === tab));
    button.tabIndex = button === tab ? 0 : -1;
  }
  for (const panel of box.querySelectorAll('[role="tabpanel"]')) panel.hidden = panel.id !== tab.getAttribute("aria-controls");
  box.querySelector("[data-citation-status]").textContent = "";
}

// Manual selection works on non-secure origins and browsers which reject a
// clipboard request. Never report success merely because text was selected.
export async function copyCitation(area, status, write = text => navigator.clipboard.writeText(text)) {
  status.textContent = "";
  try {
    await write(area.value);
    if (area.isConnected && !area.parentElement.hidden) status.textContent = "Copied.";
  } catch {
    if (!area.isConnected || area.parentElement.hidden) return;
    area.focus();
    area.select();
    status.textContent = "Text selected. Press Ctrl+C or ⌘C to copy.";
  }
}

export function installCitationActions(view) {
  view.addEventListener("click", event => {
    const box = event.target.closest(".citation-box");
    if (!box) return;
    const tab = event.target.closest(".citation-tab");
    if (tab) activateTab(box, tab);
    if (event.target.closest("[data-citation-copy]")) {
      const area = box.querySelector('[role="tabpanel"]:not([hidden]) textarea');
      if (area) void copyCitation(area, box.querySelector("[data-citation-status]"));
    }
  });
  view.addEventListener("keydown", event => {
    const tab = event.target.closest(".citation-tab");
    if (!tab || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const box = tab.closest(".citation-box");
    const tabs = [...box.querySelectorAll(".citation-tab")];
    const index = tabs.indexOf(tab);
    const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    event.preventDefault();
    activateTab(box, tabs[next]);
    tabs[next].focus();
  });
}
