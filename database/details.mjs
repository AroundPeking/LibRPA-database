import { esc, publicPath, fileName, downloadName, filesOf, bandGap, archivedBandGap, paperGap, boundFiles, methodNames, setRelation, restrictedGap } from "./records.mjs";
import { renderFiles } from "./files.mjs";
import { radialSection } from "./radial.mjs";
import { renderPropertyPanel, renderPropertyTabs } from "./properties.mjs";

const gapText = (value, precision = 3) => value === null ? "Not reported" : `${value.toFixed(precision)} <small>eV</small>`;

function paperText(record, value, kind) {
  if (!/[\u3400-\u9fff]/.test(value || "")) return value;
  if (kind === "notes") return `Table ${record.dimension === "3d" ? "IV" : "I"} has no EXX main column. EXX remains an archived historical/path result; original spectra, properties and summaries are retained. It is not a paper benchmark and missing values are not replaced by zero.${record.id === "mos2-table-gw" ? " The 6.25292 eV value from another MoS2 EXX convergence series is not the main-table value of this case and does not replace its archived EXX result." : ""}`;
  if (record.dimension === "3d") return "The main ABACUS PBE and ABACUS+LibRPA G0W0@PBE columns of Table IV, not the FHI-aims reference column. They do not replace archived path spectra or certify full-spectrum acceptance.";
  const paths = {
    "cuinp2se6-table-gw": "Γ–Γ. Low-energy path diagnostic for the restored producer structure; not full-spectrum benchmark effective masses.",
    "gate-table-gw": "K–Γ interior → M. Explicitly rejected diagnostic in the paper: the full empty-state spectrum has nonfinite/collapsed branches; the finite low-energy gap is retained only for traceability.",
    "gete-table-gw": "Γ–X–S–Y–Γ. Provisional path diagnostic, not an accepted benchmark.",
    "in2se3-table-gw": "Γ–M interior → Γ.",
    "inse-table-gw": "K–Γ interior → Γ.",
    "mos2-table-gw": "K–K.",
    "mos2_ws2-table-gw": "PBE Γ–K → GW Γ–Q. Application path diagnostic for the AA′ six-atom heterobilayer; the same result is reported to three decimals in Fig. 10 of the 3D paper.",
    "mose2-table-gw": "K–K. The displayed near-gap windows of the first three TMDCs are reported as converged in the text; this does not establish acceptance of the full empty-state spectrum.",
    "mote2-table-gw": "PBE K–K → GW K–Q. Near-gap path diagnostic, not an accepted benchmark.",
    "phosphorene-table-gw": "Γ–Γ.",
    "snse-table-gw": "Sampled path. Provisional path diagnostic, not an accepted benchmark.",
    "tis3-table-gw": "Γ–Γ. Explicitly rejected diagnostic in the paper: the full empty-state spectrum has nonfinite/collapsed branches; the finite low-energy gap is retained only for traceability.",
    "ws2-table-gw": "K–K.",
    "wse2-table-gw": "K–K. The text displays only the near-gap region with stable Padé continuation; it is not a full-spectrum benchmark claim.",
    "hbn-tzdp10-fgext-20261008": "PBE K–K; GW K–Γ raw-band-5 frontier diagnostic. Not a converged full-spectrum fundamental gap; the PBE valley ordering is incorrect and higher-state intrusion persists. The new Table I footnote uses a 10-au GTH-PBE 3s3p2d physical orbital, a smooth 1f1g-extended ABF, no empty atoms, and a 12×12×1 response mesh. PBE Ec(K)−Ec(Γ)=−0.2602 eV; GW 6.94183 eV is a raw-band-5 frontier path gap, not an accepted full-spectrum fundamental gap."
  };
  if (!paths[record.id]) throw new Error("English paper scope not recorded for this case");
  return `Table I: scalar-relativistic, no-SOC ABACUS PBE and ABACUS+LibRPA G0W0@PBE. Reported path: ${paths[record.id]} Finite main-table values do not promote the archived path, full empty-state spectrum or current record status.`;
}

function paperValuesInfo(record) {
  const paper = record.paper_values;
  const methods = ["DFT", "GW"].filter(method => paperGap(record, method));
  if (!methods.length) return "";
  const source = paper.source;
  const evidenceUrl = publicPath(paper.evidence);
  const rows = methods.map(method => {
    const reported = paperGap(record, method);
    const archived = archivedBandGap(record, method);
    return `<tr><th scope="row">${method === "DFT" ? "PBE / DFT" : "GW"}</th><td>${esc(reported.value.toFixed(reported.precision))} eV<br><small>${esc(reported.column)}</small></td><td>${archived === null ? "Not reported / restricted" : `${esc(archived.toFixed(5))} eV`}</td></tr>`;
  }).join("");
  const scopes = [...new Set(methods.map(method => paperGap(record, method).scope).filter(Boolean))];
  const scopeHtml = scopes.map(scope => `<p class="definition-note"><strong>Reported scope</strong> ${esc(paperText(record, scope, "scope"))}</p>`).join("");
  return `<div class="notice paper-values"><strong>Paper-reported values</strong><p>${esc(source.title)} · PDF p. ${esc(source.pdf_page)} · Table ${esc(source.table)}${source.doi ? ` · DOI ${esc(source.doi)}` : ""}</p><p>The headline and list prefer the paper's own PBE/GW columns. Archived path values and original bands remain separate; paper values do not certify these archived files or change scientific status.</p><div class="table-wrap"><table class="property-table"><thead><tr><th>Method</th><th>Paper-reported</th><th>Archived / path value</th></tr></thead><tbody>${rows}</tbody></table></div>${scopeHtml}<p>${esc(paperText(record, paper.notes || "EXX is not a main-table column; any displayed EXX value is from the original archive.", "notes"))}</p><p>${evidenceUrl ? `<a href="${esc(evidenceUrl)}" target="_blank" rel="noopener">Download paper-value extract ↗</a>` : ""} · Document SHA-256 <code>${esc(source.document_sha256)}</code></p></div>`;
}
const materialLink = record => `#/material/${encodeURIComponent(record.id)}`;
const basisLink = set => `#/basis/${encodeURIComponent(set.id)}`;
const section = (id, number, title, body, open = false, badge = "") => `<details class="detail-section" id="${id}" ${open ? "open" : ""}><summary><span class="section-number">${number}</span><h2>${title}</h2>${badge ? `<span class="section-badge">${badge}</span>` : ""}<span class="expand-mark" aria-hidden="true">+</span></summary><div class="section-body">${body}</div></details>`;
const jump = (id, title) => `<button type="button" data-section="${id}">${title}</button>`;
const chips = methods => methods.map(method => `<span class="method-tag method-${method.toLowerCase()}">${method}</span>`).join("");
const formatField = value => esc(typeof value === "object" ? JSON.stringify(value) : value ?? "Not recorded");
const figureGrid = files => `<div class="figure-grid">${files.map(file => {
  const url = publicPath(file.path);
  if (!url) return '<div class="notice warning">Invalid archive path; figure link disabled.</div>';
  const diagnostic = file.scientific_status === "archived_diagnostic";
  return `<figure><a href="${esc(url)}" target="_blank" rel="noopener"><img loading="lazy" src="${esc(url)}" alt="${esc(fileName(file))}"></a><figcaption><span>${esc(fileName(file))}${diagnostic ? '<br><strong class="missing-value">Archived diagnostic · not an accepted result</strong>' : ""}</span><a href="${esc(url)}" download="${esc(downloadName(file))}">Download figure ↓</a></figcaption></figure>`;
}).join("")}</div>`;

function softwareInfo(record) {
  return ["abacus", "librpa"].map(name => {
    const app = record.software?.[name] || {};
    const fullCommit = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/i.test(app.commit || "");
    const url = /^https:\/\/github\.com\/[^\s]+$/.test(app.source_url || "") && fullCommit ? `${app.source_url.replace(/\/$/, "")}/commit/${app.commit}` : null;
    return `<div class="software-entry"><h3>${name === "abacus" ? "ABACUS" : "LibRPA"}</h3>${app.commit ? `<code>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(app.commit)}</a>` : esc(app.commit)}</code>` : ""}${!fullCommit ? '<span class="missing-value">Full commit not recorded</span>' : ""}${app.identity_note || app.missing_reason ? `<p>${esc(app.identity_note || app.missing_reason)}</p>` : ""}</div>`;
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
  const primaryFigures = figures.filter(file => file.display_priority === "primary");
  const mainFigures = primaryFigures.length ? primaryFigures : figures;
  const originalFigures = primaryFigures.length ? figures.filter(file => file.display_priority !== "primary") : [];
  const figureAttachments = figureFiles.filter(f => !figures.includes(f));
  const structure = inputs.filter(f => /(?:^|__)(STRU(?:\.cif)?|geometry\.in|POSCAR)$|\.cif$/i.test(f.path.split("/").at(-1)));
  const properties = record.properties || [];
  const rpa = properties.filter(p => p.key === "rpa_correlation_energy" && p.status !== "failed");
  const missing = [...(record.missing || [])];
  for (const name of ["abacus", "librpa"]) if (!/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/i.test(record.software?.[name]?.commit || "")) missing.push(`${name === "abacus" ? "ABACUS" : "LibRPA"}: full source commit not recorded.`);
  if (!inputs.length) missing.unshift("Calculation input files are not present in this public archive.");
  const missingHtml = [...new Set(missing)].map(value => `<li>${esc(value)}</li>`).join("");
  const completeness = record.archive_completeness;
  const completenessState = completeness?.status === "incomplete" ? "Upload incomplete · CI blocked" : completeness?.status === "complete" ? "Upload complete · archive checks passed" : "Upload completeness not recorded";
  const completenessIssues = (completeness?.issues || []).map(issue => `<li>${esc(issue)}</li>`).join("");
  const completenessHtml = `<details class="archive-completeness"><summary>Archive completeness <span class="completeness-label">· ${completenessState}</span></summary><div class="notice ${completeness?.status === "incomplete" ? "warning" : ""}"><strong>${completenessState}</strong><p>Archive completeness checks the uploaded evidence; it is not a scientific-validation certification.</p>${completenessIssues ? `<ul>${completenessIssues}</ul>` : ""}</div>${missingHtml ? `<div class="notice warning"><strong>Missing evidence &amp; limitations</strong><ul>${missingHtml}</ul></div>` : ""}<div class="completeness-gates">${record.summary?.gates?.length ? `<h3 class="subheading">Recorded validation gates</h3><ul>${record.summary.gates.map(gate => `<li>${formatField(gate)}</li>`).join("")}</ul>` : '<p class="muted">No additional validation gates recorded.</p>'}</div></details>`;
  const limited = restrictedGap(record);
  const validationState = ({ gw_validated: "Validated within the recorded scope", gw_diagnostic: "Archived result — validation incomplete", path_diagnostic: "Restricted path result — not a fundamental gap", pbe_only: "PBE-only evidence", failed: "Failed validation", pending: "Pending evidence", generation_only: "Generation evidence only" })[record.status] || "Status not recorded";
  const scopedObservable = limited && record.summary?.value != null ? `<div class="notice warning"><strong>${esc(record.summary.observable)}</strong><p>${formatField(record.summary.value)} ${esc(record.summary.unit || "")} — selected-state observable only. ${paperGap(record) ? "The headline and list show the cited paper value, labelled as restricted; numerical sorting uses that reported value, not a certified fundamental gap." : "Without a cited paper value, this raw-state separation is excluded from the headline GW value and sorting."}</p></div>` : "";
  const diagnostics = Array.isArray(record.method_diagnostics) ? record.method_diagnostics : [];
  const diagnosticsHtml = diagnostics.length ? `<div class="notice warning"><strong>Method diagnostics · not an accepted gap</strong><ul>${diagnostics.map(item => `<li><strong>${esc(item.method || "Method")}</strong> — ${esc(item.message || item.reason || "Diagnostic evidence recorded; no ordinary gap is reported.")}${Number.isFinite(item.full_raw_path_gap_ev) ? `<br>Full raw path CBM − VBM: ${esc(item.full_raw_path_gap_ev)} eV.` : ""}${Number.isFinite(item.frozen_window_path_gap_ev) ? `<br>Frozen-window path value: ${esc(item.frozen_window_path_gap_ev)} eV.` : ""}${item.sidecar_selected_window_matches === false && Number.isFinite(item.sidecar_path_gap_ev) ? `<br>Archived sidecar path value: ${esc(item.sidecar_path_gap_ev)} eV (does not match the recomputed frozen window).` : ""}</li>`).join("")}</ul></div>` : "";
  const overview = `${scopedObservable}${paperValuesInfo(record)}${diagnosticsHtml}<p class="detail-note">${esc(record.summary?.notes || "No additional interpretation is recorded.")}</p>${sourceInfo(record)}${record.summary?.gap_definition ? `<p class="definition-note"><strong>Gap definition</strong> ${esc(record.summary.gap_definition)}</p>` : ""}${record.summary?.scope ? `<p class="definition-note"><strong>Scope</strong> ${esc(record.summary.scope)}</p>` : ""}${completenessHtml}`;
  const structureHtml = structure.length ? `<p class="section-intro">Original structure files attached to this calculation. Different archived stages remain separate; no missing geometry is reconstructed.</p>${renderFiles(structure, { input: true })}` : '<div class="empty-panel"><h3>Structure file not archived</h3><p>No STRU, CIF, or equivalent structure file is attached to this record. A geometry is not inferred from the formula.</p></div>';
  const bandsHtml = `<p class="section-intro">Figure style and data contracts: <a href="../references/plotting.md">plotting reference</a> · <a href="https://github.com/AroundPeking/abacus-librpa-gw-database/blob/main/scripts/generate_band_figures.py" target="_blank" rel="noopener">reusable band-figure script ↗</a>. Each method uses its own occupied path VBM. The y range shows the full extent of the already-selected curves, without adding bands; this does not imply scientific acceptance.</p>${mainFigures.length ? `${figureGrid(mainFigures)}<p class="definition-note">Band figures follow the archived k-path. A path gap is not automatically the global fundamental gap; refer to the recorded definition and scope in Overview.</p>` : '<p class="empty-panel">No band figure archived. Available result files are listed below.</p>'}${originalFigures.length ? `<details class="original-figures"><summary>Original archived figures · ${originalFigures.length}</summary>${figureGrid(originalFigures)}</details>` : ""}<h3 class="subheading">Numerical result files</h3>${renderFiles(results)}${figureAttachments.length ? `<h3 class="subheading">Figure source &amp; metadata</h3>${renderFiles(figureAttachments)}` : ""}`;
  const propsHtml = `<p class="section-intro">Evidence-linked properties. Empty categories are available for future contributions, not zero-valued results.</p><div class="property-tabs" role="tablist" aria-label="Property categories">${renderPropertyTabs(properties)}</div><div class="property-panel" id="property-panel" role="tabpanel" tabindex="0" aria-labelledby="property-tab-electronic">${renderPropertyPanel(properties)}</div>`;
  const partialInputNotice = record.source?.stage_input_receipt ? `<div class="notice warning"><strong>Partial stage inputs · not a complete rerun bundle</strong><p>Recovered controls remain separated by their source stage. Complete stage execution, runtime payloads and exact basis bindings are not certified by this attachment. Any private-path redaction is recorded with the original SHA-256.</p><a href="${esc(publicPath(record.source.stage_input_receipt))}" target="_blank" rel="noopener">View stage-input receipt ↗</a>${record.source.producer_assets_receipt ? `<p>Exact PP/NAO/ABF names and payload hashes were recovered separately from original STRU and producer manifests. This does not prove the complete runtime handoff.</p><a href="${esc(publicPath(record.source.producer_assets_receipt))}" target="_blank" rel="noopener">View separate producer-assets receipt ↗</a>` : ""}</div>` : "";
  const inputsHtml = inputs.length ? `${partialInputNotice}<div class="notice"><strong>${inputs.length} archived input files</strong><p>These files belong to <code>${esc(record.id)}</code>. Their presence is not a complete-run certification. Exact PP / NAO / auxiliary bindings, when verified, are linked in the Basis section.</p></div>${renderFiles(inputs, { input: true })}` : '<div class="notice warning"><strong>Inputs not archived</strong><p>This record currently contains results only. No INPUT, KPT, STRU, or LibRPA input is available to view or download. Candidate basis files are not substituted for missing calculation inputs.</p></div>';
  const evidenceHtml = `<p class="section-intro">Recorded source commits identify the software used for this calculation. Archive completeness and validation gates are listed in Overview.</p><div class="software-grid">${softwareInfo(record)}</div><h3 class="subheading">Logs</h3>${renderFiles(logs)}`;
  const supersededNotice = record.id === "hbn-table-gw" ? '<div class="notice warning"><strong>Superseded hBN archive · hidden from default browsing</strong><p>Use the replacement hBN for the current paper result.</p><a href="#/material/hbn-tzdp10-fgext-20261008">Open replacement hBN · GW 6.94183 eV</a><p>Historical results remain unchanged; this display choice is not an archive completeness exemption.</p></div>' : "";
  return `${supersededNotice}<div class="breadcrumb"><a href="#/">Materials</a><span>/</span><span>${esc(record.material)}</span></div>
    <div class="detail-header"><div><div class="detail-tags"><span class="dimension-tag">${esc(record.dimension.toUpperCase())}</span>${chips(methodNames(record))}</div><h1>${esc(record.material)} <small>${esc(record.formula || "")}</small></h1><p class="detail-id">${esc(record.id)}</p></div><button class="primary-button" type="button" data-section="record-inputs">${inputs.length ? `View inputs (${inputs.length})` : "Input availability"}<span aria-hidden="true">↓</span></button></div>
    <p class="record-status">${esc(validationState)}${completeness?.status === "incomplete" ? ` · ${completenessState}` : ""}</p><div class="result-strip">${["DFT", "EXX", "GW"].map(method => {
      const paper = paperGap(record, method);
      const unavailableRestricted = method === "GW" && limited && !paper;
      const label = paper ? `${method} · paper-reported` : `${method} band gap`;
      return `<div class="${method === "GW" ? "result-primary" : ""}"><span>${label}</span><strong class="${unavailableRestricted ? "no-result" : ""}">${unavailableRestricted ? "Restricted result" : gapText(bandGap(record, method), paper?.precision ?? 3)}</strong>${method === "GW" && limited && paper ? '<small class="gap-scope">Restricted path · not an accepted fundamental gap</small>' : ""}</div>`;
    }).join("")}<div><span>RPA correlation energy</span><strong class="${rpa.length ? "" : "no-result"}">${rpa.length === 1 ? `${formatField(rpa[0].value)} <small>${esc(rpa[0].unit)}</small>` : "Not reported"}</strong></div></div>
    <div class="detail-layout"><aside class="section-nav"><p class="kicker">IN THIS RECORD</p>${jump("record-overview", "Overview")}${jump("record-structure", "Crystal structure")}${jump("record-bands", "Electronic bands")}${jump("record-properties", "Properties")}${jump("record-inputs", `Input files · ${inputs.length}`)}${jump("record-basis", "Pseudopotentials & basis")}${jump("record-evidence", "Source commits")}<div class="section-tools"><button type="button" class="text-button" data-expand="true">Expand all</button><button type="button" class="text-button" data-expand="false">Collapse all</button></div></aside>
    <div class="detail-content">${section("record-overview", "01", "Overview", overview, true)}${section("record-structure", "02", "Crystal structure", structureHtml, false, structure.length ? `${structure.length} files` : "Not archived")}${section("record-bands", "03", "Electronic bands", bandsHtml, true, `${figures.length} figures`)}${section("record-properties", "04", "Properties", propsHtml, false, `${properties.length} reported`)}${section("record-inputs", "05", "Input files", inputsHtml, true, inputs.length ? `${inputs.length} files` : "Missing")}${section("record-basis", "06", "Pseudopotentials &amp; basis", basisBindings(record, sets), false)}${section("record-evidence", "07", "Source commits", evidenceHtml, false)}</div></div>`;
}

export function renderBasis(set, calculations) {
  const linked = calculations.filter(record => (record.species || []).some(s => s.set_id === set.id) || (record.basis_candidates || []).some(s => s.set_id === set.id) || (set.publication?.calculation_ids || []).includes(record.id));
  const payloads = (set.files || []).filter(file => ["pp", "nao", "abf", "for_aux"].includes(file.role));
  const evidence = (set.files || []).filter(file => !payloads.includes(file));
  const published = set.publication?.status === "publishable";
  return `<div class="breadcrumb"><a href="#/basis">Basis library</a><span>/</span><span>${esc(set.element)}</span></div><div class="detail-header"><div><p class="kicker">ELEMENT BASIS RECORD</p><h1>${esc(set.element)} <small>${esc(set.family || "Basis set")}</small></h1><p class="detail-id">${esc(set.id)}</p></div><span class="publication-tag">${published ? "Publishable" : "Archive only"}</span></div>
    <div class="notice ${published ? "" : "warning"}"><strong>${published ? "Published set" : "Not a validated direct-use release"}</strong><p>${esc(set.validation_scope || "Validation scope not recorded.")}</p>${set.notes ? `<p>${esc(set.notes)}</p>` : ""}</div>
    ${section("basis-assets", "01", "Basis files", `<p class="section-intro">Readable download names are separate from immutable storage. A descriptive alias is labelled explicitly when the original filename is unknown. Check the calculation-specific name before using an input file.</p>${renderFiles(payloads)}`, true, `${payloads.length} files`)}
    ${section("basis-radial", "02", "Radial orbitals by angular momentum", radialSection(set), true, "NAO / ABF")}
    ${section("basis-calculations", "03", "Linked calculations", linked.length ? `<ul class="linked-records">${linked.map(record => `<li><a href="${materialLink(record)}"><strong>${esc(record.material)}</strong><span>${esc(record.id)}</span></a><span class="dimension-tag">${esc(record.dimension.toUpperCase())}</span><span class="relation-label">${esc(setRelation(record, set.id))}</span></li>`).join("")}</ul>` : '<p class="empty-panel">No calculation is linked to this set. Generation evidence alone is not material-level validation.</p>', true, `${linked.length} records`)}
    ${section("basis-evidence", "04", "Generation evidence &amp; source", `<dl class="metadata-list"><dt>Collection</dt><dd>${esc(set.source?.collection || "Not recorded")}</dd><dt>License</dt><dd>${esc(set.source?.license || "Not recorded in this set; check source terms before redistribution")}</dd><dt>Generation status</dt><dd>${esc(set.generation_provenance?.status || "Not recorded")}</dd></dl>${renderFiles(evidence)}`, false, `${evidence.length} files`)}`;
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
