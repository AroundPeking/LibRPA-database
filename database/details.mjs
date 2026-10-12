import { esc, publicPath, fileName, downloadName, filesOf, bandGap, paperGap, boundFiles, methodNames, setRelation, restrictedGap } from "./records.mjs";
import { renderFiles } from "./files.mjs";
import { radialSection } from "./radial.mjs";
import { renderPropertyPanel, renderPropertyTabs } from "./properties.mjs";

const gapText = (value, precision = 3) => value === null ? "—" : `${value.toFixed(precision)} <small>eV</small>`;

function paperText(record, value, kind) {
  if (!/[\u3400-\u9fff]/.test(value || "")) return value;
  if (kind === "notes") return `Table ${record.dimension === "3d" ? "IV" : "I"} has no EXX main column. EXX values shown here come from the associated calculation data and retain their recorded path definition.${record.id === "mos2-table-gw" ? " The 6.25292 eV value belongs to a separate MoS2 EXX convergence series and is not used for this record." : ""}`;
  if (record.dimension === "3d") return "The main ABACUS PBE and ABACUS+LibRPA G0W0@PBE columns of Table IV; the FHI-aims reference column is recorded separately in the source paper.";
  const paths = {
    "cuinp2se6-table-gw": "Γ–Γ. Low-energy path observable for the recorded producer structure.",
    "gate-table-gw": "K–Γ interior → M. The reported value describes the finite low-energy window; the full empty-state spectrum includes nonfinite or collapsed branches.",
    "gete-table-gw": "Γ–X–S–Y–Γ path observable.",
    "in2se3-table-gw": "Γ–M interior → Γ.",
    "inse-table-gw": "K–Γ interior → Γ.",
    "mos2-table-gw": "K–K.",
    "mos2_ws2-table-gw": "PBE Γ–K → GW Γ–Q. Application path diagnostic for the AA′ six-atom heterobilayer; the same result is reported to three decimals in Fig. 10 of the 3D paper.",
    "mose2-table-gw": "K–K. The source text reports convergence of the displayed near-gap windows for the first three TMDCs.",
    "mote2-table-gw": "PBE K–K → GW K–Q near-gap path observable.",
    "phosphorene-table-gw": "Γ–Γ.",
    "snse-table-gw": "Sampled-path observable.",
    "tis3-table-gw": "Γ–Γ. The reported value describes the finite low-energy window; the full empty-state spectrum includes nonfinite or collapsed branches.",
    "ws2-table-gw": "K–K.",
    "wse2-table-gw": "K–K. The source text displays the near-gap region with stable Padé continuation.",
    "hbn-tzdp10-fgext-20261008": "PBE K–K; GW K–Γ raw-band-5 frontier path observable. The Table I calculation uses a 10-au GTH-PBE 3s3p2d physical orbital, a smooth 1f1g-extended ABF, no empty atoms, and a 12×12×1 response mesh. PBE Ec(K)−Ec(Γ)=−0.2602 eV; the recorded GW path value is 6.94183 eV."
  };
  if (!paths[record.id]) throw new Error("English paper scope not recorded for this case");
  return `Table I: scalar-relativistic, no-SOC ABACUS PBE and ABACUS+LibRPA G0W0@PBE. Reported path: ${paths[record.id]} Values retain the definition and scope of the source calculation.`;
}

function referenceInfo(record) {
  const paper = record.paper_values;
  const methods = ["DFT", "GW"].filter(method => paperGap(record, method));
  if (!methods.length) return "";
  const source = paper.source;
  const evidenceUrl = publicPath(paper.evidence);
  const scopes = [...new Set(methods.map(method => paperGap(record, method).scope).filter(Boolean))];
  const scopeHtml = scopes.map(scope => `<p class="definition-note"><strong>Source scope</strong> ${esc(paperText(record, scope, "scope"))}</p>`).join("");
  return `<details class="reference-source"><summary>Reference &amp; source evidence <span>Table ${esc(source.table)}</span></summary><div class="reference-body"><p>${esc(source.title)} · PDF p. ${esc(source.pdf_page)} · Table ${esc(source.table)}${source.doi ? ` · DOI ${esc(source.doi)}` : ""}</p><p>The database values are shown once above. This reference records their source; original result files and scientific status remain unchanged.</p>${scopeHtml}<p>${esc(paperText(record, paper.notes || "EXX is archive-derived; the reference has no EXX main column.", "notes"))}</p><p>${evidenceUrl ? `<a href="${esc(evidenceUrl)}" target="_blank" rel="noopener">Download source extract ↗</a>` : ""}</p><p>Document SHA-256 <code>${esc(source.document_sha256)}</code></p></div></details>`;
}
const materialLink = record => `#/material/${encodeURIComponent(record.id)}`;
const basisLink = set => `#/basis/${encodeURIComponent(set.id)}`;
const section = (id, number, title, body, open = false, badge = "") => `<details class="detail-section" id="${id}" ${open ? "open" : ""}><summary><span class="section-number">${number}</span><h2>${title}</h2>${badge ? `<span class="section-badge">${badge}</span>` : ""}<span class="expand-mark" aria-hidden="true">+</span></summary><div class="section-body">${body}</div></details>`;
const jump = (id, title) => `<button type="button" data-section="${id}">${title}</button>`;
const chips = methods => methods.map(method => `<span class="method-tag method-${method.toLowerCase()}">${method}</span>`).join("");
const formatField = value => esc(typeof value === "object" ? JSON.stringify(value) : value ?? "—");
const figureGrid = files => `<div class="figure-grid">${files.map(file => {
  const url = publicPath(file.path);
  if (!url) return '<div class="notice warning">Figure link unavailable.</div>';
  const diagnostic = file.scientific_status === "archived_diagnostic";
  return `<figure><a href="${esc(url)}" target="_blank" rel="noopener"><img loading="lazy" src="${esc(url)}" alt="${esc(fileName(file))}"></a><figcaption><span>${esc(fileName(file))}${diagnostic ? '<br><strong>Diagnostic figure</strong>' : ""}</span><a href="${esc(url)}" download="${esc(downloadName(file))}">Download figure ↓</a></figcaption></figure>`;
}).join("")}</div>`;

function softwareInfo(record) {
  return ["abacus", "librpa"].map(name => {
    const app = record.software?.[name] || {};
    const fullCommit = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/i.test(app.commit || "");
    const url = /^https:\/\/github\.com\/[^\s]+$/.test(app.source_url || "") && fullCommit ? `${app.source_url.replace(/\/$/, "")}/commit/${app.commit}` : null;
    return `<div class="software-entry"><h3>${name === "abacus" ? "ABACUS" : "LibRPA"}</h3>${app.commit ? `<code>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(app.commit)}</a>` : esc(app.commit)}</code>` : '<span>Calculation software</span>'}${app.identity_note ? `<p>${esc(app.identity_note)}</p>` : ""}</div>`;
  }).join("");
}

function basisBindings(record, sets) {
  const byId = new Map(sets.map(s => [s.id, s]));
  const exact = (record.species || []).map(species => {
    const set = byId.get(species.set_id);
    if (!set) return "";
    const files = boundFiles(set, species).filter(f => ["pp", "nao", "abf", "for_aux"].includes(f.role));
    return `<div class="binding-card"><div class="binding-heading"><h3>${esc(set.element)} <span>${esc(set.family || "Basis set")}</span></h3><a href="${basisLink(set)}">Basis record ↗</a></div><p class="binding-id">${esc(set.id)}</p>${renderFiles(files)}</div>`;
  }).join("");
  const candidates = (record.basis_candidates || []).map(candidate => `<li><a href="#/basis/${encodeURIComponent(candidate.set_id)}">${esc(candidate.element)} · ${esc(byId.get(candidate.set_id)?.family || candidate.set_id)}</a><span>${esc(candidate.scope || "Related basis data")}</span></li>`).join("");
  return `<p class="section-intro">Each file retains its immutable data path and SHA-256. Recorded calculation filenames are used for downloads when available.</p>${exact}${candidates ? `<details class="candidate-section"><summary>Related basis records (${record.basis_candidates.length})</summary><ul class="candidate-list">${candidates}</ul></details>` : ""}`;
}

function sourceInfo(record) {
  const source = record.source || {};
  const safeRepository = /^https:\/\/github\.com\/[^\s]+$/.test(source.repository || "");
  return `<dl class="metadata-list"><dt>Calculation ID</dt><dd><code>${esc(record.id)}</code></dd><dt>Collection</dt><dd>${esc(source.collection || "—")}</dd>${safeRepository ? `<dt>Source repository</dt><dd><a href="${esc(source.repository)}" target="_blank" rel="noopener">${esc(source.repository.replace("https://github.com/", ""))} ↗</a></dd>` : ""}${source.archive_commit ? `<dt>Data revision</dt><dd><code>${esc(source.archive_commit)}</code></dd>` : ""}${source.archive_directory ? `<dt>Source directory</dt><dd><code>${esc(source.archive_directory)}</code></dd>` : ""}<dt>Observable</dt><dd>${esc(record.summary?.observable || "—")}</dd></dl>`;
}

export function renderMaterial(record, sets) {
  const inputs = filesOf(record, "inputs");
  const results = filesOf(record, "results");
  const logs = filesOf(record, "logs");
  const figureFiles = filesOf(record, "figures");
  const figures = figureFiles.filter(f => /\.(?:svg|png|jpe?g|webp)$/i.test(f.path));
  const primaryFigures = figures.filter(file => file.display_priority === "primary");
  const mainFigures = primaryFigures.length ? primaryFigures : figures;
  const originalFigures = primaryFigures.length ? figures.filter(file => file.display_priority !== "primary") : [];
  const figureAttachments = figureFiles.filter(f => !figures.includes(f));
  const structure = inputs.filter(f => /(?:^|__)(STRU(?:\.cif)?|geometry\.in|POSCAR)$|\.cif$/i.test(f.path.split("/").at(-1)));
  const properties = record.properties || [];
  const visibleProperties = properties.filter(property => property.status !== "failed");
  const rpa = visibleProperties.filter(p => p.key === "rpa_correlation_energy");
  const limited = restrictedGap(record);
  const validationState = ({ gw_validated: "GW calculation", gw_diagnostic: "GW diagnostic calculation", path_diagnostic: "Path-resolved GW calculation", pbe_only: "DFT calculation", failed: "Diagnostic calculation", pending: "Calculation record", generation_only: "Basis-generation record" })[record.status] || "Calculation record";
  const scopedObservable = limited && record.summary?.value != null ? `<div class="notice"><strong>${esc(record.summary.observable)}</strong><p>Path-resolved selected-state observable. ${paperGap(record) ? "The database displays the referenced path value with its recorded definition." : "The numerical result remains available in the associated data files."}</p></div>` : "";
  const overview = `${scopedObservable}${referenceInfo(record)}<p class="detail-note">Calculation data, methods, and provenance are organized in the sections below.</p>${sourceInfo(record)}${record.summary?.gap_definition ? `<p class="definition-note"><strong>Gap definition</strong> ${esc(record.summary.gap_definition)}</p>` : ""}`;
  const structureHtml = structure.length ? `<p class="section-intro">Structure files attached to this calculation. Files from different calculation stages remain separately identified.</p>${renderFiles(structure, { input: true })}` : '<div class="empty-panel"><h3>Structure data</h3><p>This record presents the calculation results and attached provenance files; no separate STRU, CIF, or equivalent structure file is listed.</p></div>';
  const bandsHtml = `<p class="section-intro">Figure style and data contracts: <a href="../references/plotting.md">plotting reference</a> · <a href="https://github.com/AroundPeking/abacus-librpa-gw-database/blob/main/scripts/generate_band_figures.py" target="_blank" rel="noopener">reusable band-figure script ↗</a>. Each method uses its own occupied path VBM. The y range shows the full extent of the selected curves without adding bands.</p>${mainFigures.length ? `${figureGrid(mainFigures)}<p class="definition-note">Band figures follow the recorded k-path; refer to the definition and scope in Overview.</p>` : '<p class="empty-panel">Numerical result files are listed below.</p>'}${originalFigures.length ? `<details class="original-figures"><summary>Additional source figures · ${originalFigures.length}</summary>${figureGrid(originalFigures)}</details>` : ""}<h3 class="subheading">Numerical result files</h3>${renderFiles(results)}${figureAttachments.length ? `<h3 class="subheading">Figure source &amp; metadata</h3>${renderFiles(figureAttachments)}` : ""}`;
  const propsHtml = `<p class="section-intro">Evidence-linked properties. Empty categories are available for future contributions, not zero-valued results.</p><div class="property-tabs" role="tablist" aria-label="Property categories">${renderPropertyTabs(visibleProperties)}</div><div class="property-panel" id="property-panel" role="tabpanel" tabindex="0" aria-labelledby="property-tab-electronic">${renderPropertyPanel(visibleProperties)}</div>`;
  const partialInputNotice = record.source?.stage_input_receipt ? `<div class="notice"><strong>Stage-resolved calculation inputs</strong><p>Controls are organized by their original calculation stage. File transformations and source hashes are recorded in the accompanying receipt.</p><a href="${esc(publicPath(record.source.stage_input_receipt))}" target="_blank" rel="noopener">View stage-input receipt ↗</a>${record.source.producer_assets_receipt ? `<p>PP/NAO/ABF names and payload hashes are documented separately from the original STRU and producer manifests.</p><a href="${esc(publicPath(record.source.producer_assets_receipt))}" target="_blank" rel="noopener">View producer-assets receipt ↗</a>` : ""}</div>` : "";
  const inputsHtml = inputs.length ? `${partialInputNotice}<div class="notice"><strong>${inputs.length} calculation input files</strong><p>These files belong to <code>${esc(record.id)}</code>. Associated PP / NAO / auxiliary data are linked in the Basis section.</p></div>${renderFiles(inputs, { input: true })}` : '<div class="notice"><strong>Calculation results</strong><p>Numerical results and provenance are available in the other sections of this record.</p></div>';
  const evidenceHtml = `<p class="section-intro">Software identifiers and calculation logs associated with this record.</p><div class="software-grid">${softwareInfo(record)}</div><h3 class="subheading">Logs</h3>${renderFiles(logs)}`;
  const supersededNotice = record.id === "hbn-table-gw" ? '<div class="notice"><strong>Previous hBN calculation</strong><p>The current paper result is available in the updated hBN record.</p><a href="#/material/hbn-tzdp10-fgext-20261008">Open current hBN · GW 6.94183 eV</a></div>' : "";
  return `${supersededNotice}<div class="breadcrumb"><a href="#/">Materials</a><span>/</span><span>${esc(record.material)}</span></div>
    <div class="detail-header"><div><div class="detail-tags"><span class="dimension-tag">${esc(record.dimension.toUpperCase())}</span>${chips(methodNames(record))}</div><h1>${esc(record.material)} <small>${esc(record.formula || "")}</small></h1><p class="detail-id">${esc(record.id)}</p></div><button class="primary-button" type="button" data-section="record-inputs">${inputs.length ? `View inputs (${inputs.length})` : "Input availability"}<span aria-hidden="true">↓</span></button></div>
    <p class="record-status">${esc(validationState)}</p><div class="result-strip">${["DFT", "EXX", "GW"].map(method => {
      const paper = paperGap(record, method);
      const unavailableRestricted = method === "GW" && limited && !paper;
      const label = `${method} band gap`;
      return `<div class="${method === "GW" ? "result-primary" : ""}"><span>${label}</span><strong class="${unavailableRestricted ? "no-result" : ""}">${unavailableRestricted ? "Path-resolved" : gapText(bandGap(record, method), paper?.precision ?? 3)}</strong>${method === "GW" && limited && paper ? '<small class="gap-scope">Path-resolved value</small>' : ""}</div>`;
    }).join("")}<div><span>RPA correlation energy</span><strong class="${rpa.length ? "" : "no-result"}">${rpa.length === 1 ? `${formatField(rpa[0].value)} <small>${esc(rpa[0].unit)}</small>` : "—"}</strong></div></div>
    <div class="detail-layout"><aside class="section-nav"><p class="kicker">IN THIS RECORD</p>${jump("record-overview", "Overview")}${jump("record-structure", "Crystal structure")}${jump("record-bands", "Electronic bands")}${jump("record-properties", "Properties")}${jump("record-inputs", `Input files · ${inputs.length}`)}${jump("record-basis", "Pseudopotentials & basis")}${jump("record-evidence", "Software & logs")}<div class="section-tools"><button type="button" class="text-button" data-expand="true">Expand all</button><button type="button" class="text-button" data-expand="false">Collapse all</button></div></aside>
    <div class="detail-content">${section("record-overview", "01", "Overview", overview, true)}${section("record-structure", "02", "Crystal structure", structureHtml, false, structure.length ? `${structure.length} files` : "Structure")}${section("record-bands", "03", "Electronic bands", bandsHtml, true, `${figures.length} figures`)}${section("record-properties", "04", "Properties", propsHtml, false, `${visibleProperties.length} reported`)}${section("record-inputs", "05", "Input files", inputsHtml, true, inputs.length ? `${inputs.length} files` : "Results record")}${section("record-basis", "06", "Pseudopotentials &amp; basis", basisBindings(record, sets), false)}${section("record-evidence", "07", "Software &amp; logs", evidenceHtml, false)}</div></div>`;
}

export function renderBasis(set, calculations) {
  const linked = calculations.filter(record => (record.species || []).some(s => s.set_id === set.id) || (record.basis_candidates || []).some(s => s.set_id === set.id) || (set.publication?.calculation_ids || []).includes(record.id));
  const payloads = (set.files || []).filter(file => ["pp", "nao", "abf", "for_aux"].includes(file.role));
  const evidence = (set.files || []).filter(file => !payloads.includes(file));
  const published = set.publication?.status === "publishable";
  return `<div class="breadcrumb"><a href="#/basis">Basis library</a><span>/</span><span>${esc(set.element)}</span></div><div class="detail-header"><div><p class="kicker">ELEMENT BASIS RECORD</p><h1>${esc(set.element)} <small>${esc(set.family || "Basis set")}</small></h1><p class="detail-id">${esc(set.id)}</p></div><span class="publication-tag">${published ? "Published set" : "Basis record"}</span></div>
    <div class="notice"><strong>${published ? "Published basis set" : "Basis data record"}</strong><p>${esc(set.validation_scope || "Basis data and provenance")}</p>${set.notes ? `<p>${esc(set.notes)}</p>` : ""}</div>
    ${section("basis-assets", "01", "Basis files", `<p class="section-intro">Readable download names are separate from immutable storage. Descriptive aliases are labelled explicitly; calculation-specific filenames are used where available.</p>${renderFiles(payloads)}`, true, `${payloads.length} files`)}
    ${section("basis-radial", "02", "Radial orbitals by angular momentum", radialSection(set), true, "NAO / ABF")}
    ${section("basis-calculations", "03", "Linked calculations", linked.length ? `<ul class="linked-records">${linked.map(record => `<li><a href="${materialLink(record)}"><strong>${esc(record.material)}</strong><span>${esc(record.id)}</span></a><span class="dimension-tag">${esc(record.dimension.toUpperCase())}</span><span class="relation-label">${esc(setRelation(record, set.id))}</span></li>`).join("")}</ul>` : '<p class="empty-panel">This basis record currently presents generation data independently from material calculations.</p>', true, `${linked.length} records`)}
    ${section("basis-evidence", "04", "Generation evidence &amp; source", `<dl class="metadata-list"><dt>Collection</dt><dd>${esc(set.source?.collection || "—")}</dd><dt>License</dt><dd>${esc(set.source?.license || "See the source collection terms")}</dd><dt>Generation status</dt><dd>${esc(set.generation_provenance?.status || "—")}</dd></dl>${renderFiles(evidence)}`, false, `${evidence.length} files`)}`;
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
