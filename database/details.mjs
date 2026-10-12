import { esc, publicPath, fileName, filesOf, bandGap, boundFiles, methodNames, setRelation, restrictedGap } from "./records.mjs";
import { renderFiles, roleNames } from "./files.mjs";
import { renderPropertyPanel, renderPropertyTabs } from "./properties.mjs";

const gapText = value => value === null ? "Not reported" : `${value.toFixed(3)} <small>eV</small>`;
const materialLink = record => `#/material/${encodeURIComponent(record.id)}`;
const basisLink = set => `#/basis/${encodeURIComponent(set.id)}`;
const section = (id, number, title, body, open = false, badge = "") => `<details class="detail-section" id="${id}" ${open ? "open" : ""}><summary><span class="section-number">${number}</span><h2>${title}</h2>${badge ? `<span class="section-badge">${badge}</span>` : ""}<span class="expand-mark" aria-hidden="true">+</span></summary><div class="section-body">${body}</div></details>`;
const jump = (id, title) => `<button type="button" data-section="${id}">${title}</button>`;
const chips = methods => methods.map(method => `<span class="method-tag method-${method.toLowerCase()}">${method}</span>`).join("");
const formatField = value => esc(typeof value === "object" ? JSON.stringify(value) : value ?? "Not recorded");

function softwareInfo(record) {
  return ["abacus", "librpa"].map(name => {
    const app = record.software?.[name] || {};
    const url = /^https:\/\/github\.com\/[^\s]+$/.test(app.source_url || "") && /^[0-9a-f]{40,64}$/.test(app.commit || "") ? `${app.source_url}/commit/${app.commit}` : null;
    return `<div class="software-entry"><h3>${name === "abacus" ? "ABACUS" : "LibRPA"}</h3>${app.commit ? `<code>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(app.commit)}</a>` : esc(app.commit)}</code>` : '<span class="missing-value">Full commit not recorded</span>'}${app.identity_note || app.missing_reason ? `<p>${esc(app.identity_note || app.missing_reason)}</p>` : ""}</div>`;
  }).join("");
}

function basisBindings(record, sets) {
  const byId = new Map(sets.map(s => [s.id, s]));
  const exact = (record.species || []).map(species => {
    const set = byId.get(species.set_id);
    if (!set) return `<div class="notice warning">${esc(species.element)}: exact basis files were not archived.${species.missing_roles?.length ? ` Missing roles: ${species.missing_roles.map(esc).join(", ")}.` : ""}</div>`;
    const files = boundFiles(set, species).filter(f => ["pp", "nao", "abf", "for_aux"].includes(f.role));
    return `<div class="binding-card"><div class="binding-heading"><h3>${esc(set.element)} <span>${esc(set.family || "Basis set")}</span></h3><a href="${basisLink(set)}">Basis record ↗</a></div><p class="binding-id">${esc(set.id)}</p>${renderFiles(files)}${species.missing_roles?.length ? `<p class="name-warning">Missing roles: ${species.missing_roles.map(esc).join(", ")}</p>` : ""}</div>`;
  }).join("");
  const candidates = (record.basis_candidates || []).map(candidate => `<li><a href="#/basis/${encodeURIComponent(candidate.set_id)}">${esc(candidate.element)} · ${esc(byId.get(candidate.set_id)?.family || candidate.set_id)}</a><span>${esc(candidate.scope || "Candidate only")}</span></li>`).join("");
  return `<p class="section-intro">Each file retains its immutable archive path and SHA-256. Recorded calculation filenames are used for downloads when available.</p>${exact || '<div class="notice warning">Exact production basis linkage was not retained for this calculation.</div>'}${candidates ? `<details class="candidate-section"><summary>Other candidate sets · not verified as the production basis (${record.basis_candidates.length})</summary><ul class="candidate-list">${candidates}</ul></details>` : ""}`;
}

function sourceInfo(record) {
  const source = record.source || {};
  const safeRepository = /^https:\/\/github\.com\/[^\s]+$/.test(source.repository || "");
  return `<dl class="metadata-list"><dt>Calculation ID</dt><dd><code>${esc(record.id)}</code></dd><dt>Collection</dt><dd>${esc(source.collection || "Not recorded")}</dd>${safeRepository ? `<dt>Source repository</dt><dd><a href="${esc(source.repository)}" target="_blank" rel="noopener">${esc(source.repository.replace("https://github.com/", ""))} ↗</a></dd>` : ""}${source.archive_commit ? `<dt>Archive commit</dt><dd><code>${esc(source.archive_commit)}</code></dd>` : ""}${source.archive_directory ? `<dt>Source directory</dt><dd><code>${esc(source.archive_directory)}</code></dd>` : ""}<dt>Observable</dt><dd>${esc(record.summary?.observable || "Not recorded")}</dd></dl>`;
}

export function renderMaterial(record, sets) {
  const inputs = filesOf(record, "inputs");
  const results = filesOf(record, "results");
  const logs = filesOf(record, "logs");
  const figureFiles = filesOf(record, "figures");
  const figures = figureFiles.filter(f => /\.(?:svg|png|jpe?g|webp)$/i.test(f.path));
  const figureAttachments = figureFiles.filter(f => !figures.includes(f));
  const structure = inputs.filter(f => /(?:^|__)(STRU(?:\.cif)?|geometry\.in|POSCAR)$|\.cif$/i.test(f.path.split("/").at(-1)));
  const properties = record.properties || [];
  const rpa = properties.filter(p => p.key === "rpa_correlation_energy" && p.status !== "failed");
  const missing = [...(record.missing || [])];
  for (const name of ["abacus", "librpa"]) if (!record.software?.[name]?.commit) missing.push(`${name === "abacus" ? "ABACUS" : "LibRPA"}: full source commit not recorded.`);
  if (!inputs.length) missing.unshift("Calculation input files are not present in this public archive.");
  const missingHtml = [...new Set(missing)].map(value => `<li>${esc(value)}</li>`).join("");
  const limited = restrictedGap(record);
  const validationState = ({ gw_validated: "Validated within the recorded scope", gw_diagnostic: "Archived result — validation incomplete", path_diagnostic: "Restricted path result — not a fundamental gap", pbe_only: "PBE-only evidence", failed: "Failed validation", pending: "Pending evidence", generation_only: "Generation evidence only" })[record.status] || "Status not recorded";
  const scopedObservable = limited && record.summary?.value != null ? `<div class="notice warning"><strong>${esc(record.summary.observable)}</strong><p>${formatField(record.summary.value)} ${esc(record.summary.unit || "")} — selected-state observable only. It is not included in the general GW gap column or gap sorting.</p></div>` : "";
  const overview = `${scopedObservable}<p class="detail-note">${esc(record.summary?.notes || "No additional interpretation is recorded.")}</p>${sourceInfo(record)}${record.summary?.gap_definition ? `<p class="definition-note"><strong>Gap definition</strong> ${esc(record.summary.gap_definition)}</p>` : ""}${record.summary?.scope ? `<p class="definition-note"><strong>Scope</strong> ${esc(record.summary.scope)}</p>` : ""}`;
  const structureHtml = structure.length ? `<p class="section-intro">Original structure files attached to this calculation. Different archived stages remain separate; no missing geometry is reconstructed.</p>${renderFiles(structure, { input: true })}` : '<div class="empty-panel"><h3>Structure file not archived</h3><p>No STRU, CIF, or equivalent structure file is attached to this record. A geometry is not inferred from the formula.</p></div>';
  const bandsHtml = `${figures.length ? `<div class="figure-grid">${figures.map(file => `<figure><a href="${esc(publicPath(file.path))}" target="_blank" rel="noopener"><img loading="lazy" src="${esc(publicPath(file.path))}" alt="${esc(fileName(file))}"></a><figcaption><span>${esc(fileName(file))}</span><a href="${esc(publicPath(file.path))}" download="${esc(file.path.split("/").at(-1))}">Download figure ↓</a></figcaption></figure>`).join("")}</div>` : '<p class="empty-panel">No band figure archived. Available result files are listed below.</p>'}<h3 class="subheading">Numerical result files</h3>${renderFiles(results)}${figureAttachments.length ? `<h3 class="subheading">Figure source &amp; metadata</h3>${renderFiles(figureAttachments)}` : ""}`;
  const propsHtml = `<p class="section-intro">Evidence-linked properties. Empty categories are available for future contributions, not zero-valued results.</p><div class="property-tabs" role="tablist" aria-label="Property categories">${renderPropertyTabs(properties)}</div><div class="property-panel" id="property-panel" role="tabpanel" tabindex="0" aria-labelledby="property-tab-electronic">${renderPropertyPanel(properties)}</div>`;
  const inputsHtml = inputs.length ? `<div class="notice"><strong>${inputs.length} archived input files</strong><p>These files belong to <code>${esc(record.id)}</code>. Their presence is not a complete-run certification. The exact PP / NAO / auxiliary files are linked in the Basis section.</p></div>${renderFiles(inputs, { input: true })}` : '<div class="notice warning"><strong>Inputs not archived</strong><p>This record currently contains results only. No INPUT, KPT, STRU, or LibRPA input is available to view or download. Candidate basis files are not substituted for missing calculation inputs.</p></div>';
  const evidenceHtml = `<div class="software-grid">${softwareInfo(record)}</div>${missingHtml ? `<div class="notice warning"><strong>Missing evidence &amp; limitations</strong><ul>${missingHtml}</ul></div>` : ""}${record.summary?.gates?.length ? `<h3>Recorded validation gates</h3><ul>${record.summary.gates.map(gate => `<li>${formatField(gate)}</li>`).join("")}</ul>` : '<p class="muted">No additional validation gates recorded.</p>'}<h3 class="subheading">Logs</h3>${renderFiles(logs)}`;
  return `<div class="breadcrumb"><a href="#/">Materials</a><span>/</span><span>${esc(record.material)}</span></div>
    <div class="detail-header"><div><div class="detail-tags"><span class="dimension-tag">${esc(record.dimension.toUpperCase())}</span>${chips(methodNames(record))}</div><h1>${esc(record.material)} <small>${esc(record.formula || "")}</small></h1><p class="detail-id">${esc(record.id)}</p></div><button class="primary-button" type="button" data-section="record-inputs">${inputs.length ? `View inputs (${inputs.length})` : "Input availability"}<span aria-hidden="true">↓</span></button></div>
    <p class="record-status">${esc(validationState)}</p><div class="result-strip">${["DFT", "EXX", "GW"].map(method => `<div class="${method === "GW" ? "result-primary" : ""}"><span>${method} band gap</span><strong class="${method === "GW" && limited ? "no-result" : ""}">${method === "GW" && limited ? "Restricted result" : gapText(bandGap(record, method))}</strong></div>`).join("")}<div><span>RPA correlation energy</span><strong class="${rpa.length ? "" : "no-result"}">${rpa.length === 1 ? `${formatField(rpa[0].value)} <small>${esc(rpa[0].unit)}</small>` : "Not reported"}</strong></div></div>
    <div class="detail-layout"><aside class="section-nav"><p class="kicker">IN THIS RECORD</p>${jump("record-overview", "Overview")}${jump("record-structure", "Crystal structure")}${jump("record-bands", "Electronic bands")}${jump("record-properties", "Properties")}${jump("record-inputs", `Input files · ${inputs.length}`)}${jump("record-basis", "Pseudopotentials & basis")}${jump("record-evidence", "Provenance & limitations")}<div class="section-tools"><button type="button" class="text-button" data-expand="true">Expand all</button><button type="button" class="text-button" data-expand="false">Collapse all</button></div></aside>
    <div class="detail-content">${section("record-overview", "01", "Overview", overview, true)}${section("record-structure", "02", "Crystal structure", structureHtml, false, structure.length ? `${structure.length} files` : "Not archived")}${section("record-bands", "03", "Electronic bands", bandsHtml, true, `${figures.length} figures`)}${section("record-properties", "04", "Properties", propsHtml, false, `${properties.length} reported`)}${section("record-inputs", "05", "Input files", inputsHtml, true, inputs.length ? `${inputs.length} files` : "Missing")}${section("record-basis", "06", "Pseudopotentials &amp; basis", basisBindings(record, sets), false)}${section("record-evidence", "07", "Provenance &amp; limitations", evidenceHtml, false)}</div></div>`;
}

export function renderBasis(set, calculations) {
  const linked = calculations.filter(record => (record.species || []).some(s => s.set_id === set.id) || (record.basis_candidates || []).some(s => s.set_id === set.id) || (set.publication?.calculation_ids || []).includes(record.id));
  const payloads = (set.files || []).filter(file => ["pp", "nao", "abf", "for_aux"].includes(file.role));
  const evidence = (set.files || []).filter(file => !payloads.includes(file));
  const published = set.publication?.status === "publishable";
  return `<div class="breadcrumb"><a href="#/basis">Basis library</a><span>/</span><span>${esc(set.element)}</span></div><div class="detail-header"><div><p class="kicker">ELEMENT BASIS RECORD</p><h1>${esc(set.element)} <small>${esc(set.family || "Basis set")}</small></h1><p class="detail-id">${esc(set.id)}</p></div><span class="publication-tag">${published ? "Publishable" : "Archive only"}</span></div>
    <div class="notice ${published ? "" : "warning"}"><strong>${published ? "Published set" : "Not a validated direct-use release"}</strong><p>${esc(set.validation_scope || "Validation scope not recorded.")}</p>${set.notes ? `<p>${esc(set.notes)}</p>` : ""}</div>
    ${section("basis-assets", "01", "Basis files", `<p class="section-intro">Readable download names are separate from immutable storage. A descriptive alias is labelled explicitly when the original filename is unknown. Check the calculation-specific name before using an input file.</p>${renderFiles(payloads)}`, true, `${payloads.length} files`)}
    ${section("basis-calculations", "02", "Linked calculations", linked.length ? `<ul class="linked-records">${linked.map(record => `<li><a href="${materialLink(record)}"><strong>${esc(record.material)}</strong><span>${esc(record.id)}</span></a><span class="dimension-tag">${esc(record.dimension.toUpperCase())}</span><span class="relation-label">${esc(setRelation(record, set.id))}</span></li>`).join("")}</ul>` : '<p class="empty-panel">No calculation is linked to this set. Generation evidence alone is not material-level validation.</p>', true, `${linked.length} records`)}
    ${section("basis-evidence", "03", "Generation evidence &amp; source", `<dl class="metadata-list"><dt>Collection</dt><dd>${esc(set.source?.collection || "Not recorded")}</dd><dt>License</dt><dd>${esc(set.source?.license || "Not recorded in this set; check source terms before redistribution")}</dd><dt>Generation status</dt><dd>${esc(set.generation_provenance?.status || "Not recorded")}</dd></dl>${renderFiles(evidence)}`, false, `${evidence.length} files`)}`;
}

export function installDetailActions(view, getRecord) {
  view.addEventListener("click", event => {
    const anchor = event.target.closest("[data-section]");
    if (anchor) {
      const target = document.getElementById(anchor.dataset.section);
      if (target) { target.open = true; target.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }); }
    }
    const expand = event.target.closest("[data-expand]");
    if (expand) view.querySelectorAll(".detail-section").forEach(section => { section.open = expand.dataset.expand === "true"; });
    const tab = event.target.closest(".property-tab");
    if (tab) activateTab(tab);
  });
  function activateTab(tab) {
    const panel = view.querySelector("#property-panel");
    view.querySelectorAll(".property-tab").forEach(button => { button.setAttribute("aria-selected", String(button === tab)); button.tabIndex = button === tab ? 0 : -1; });
    panel.setAttribute("aria-labelledby", tab.id);
    panel.innerHTML = renderPropertyPanel(getRecord()?.properties || [], tab.dataset.category);
  }
  view.addEventListener("keydown", event => {
    if (!event.target.closest(".property-tab") || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const tabs = [...view.querySelectorAll(".property-tab")];
    const index = tabs.indexOf(event.target);
    const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    event.preventDefault();
    tabs[next].focus();
    activateTab(tabs[next]);
  });
}
