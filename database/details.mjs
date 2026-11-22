import { esc, formulaHtml, publicPath, fileUrl, fileMirrorUrl, isExternalFile, filesByPath, fileName, downloadName, filesOf, bandGap, paperGap, boundFiles, methodNames, methodTag, socTag, spinPolTag, setRelation, restrictedGap, recordType, recordTypeLabel, atomCount, sampledGridGap, performanceSummary, frontendLabel, workflowFrontend, workflowLabel, sameStructureRecords, crossFrontendRecords, primaryResult } from "./records.mjs";
import { renderFiles } from "./files.mjs";
import { radialSection } from "./radial.mjs";
import { renderPropertyPanel, renderPropertyTabs, getPropertyCategories } from "./properties.mjs";
import { recordJsonUrl, recordPageUrl } from "./explorer.mjs";
import { citationBox, installCitationActions, paperEvidenceUrl } from "./citation.mjs";
import { structurePreview, groupStructureFiles } from "./structure.mjs";

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
    "hbn-tzdp10-fgext-20261008": "PBE K–K; GW K–Γ. The Table I calculation uses a 10-au GTH-PBE 3s3p2d physical orbital, a smooth 1f1g-extended ABF, no empty atoms, and a 12×12×1 response mesh."
  };
  if (!paths[record.id]) throw new Error("English paper scope not recorded for this case");
  return `Table I: scalar-relativistic, no-SOC ABACUS PBE and ABACUS+LibRPA G0W0@PBE. Reported path: ${paths[record.id]} Values retain the definition and scope of the source calculation.`;
}

function referenceInfo(record) {
  const paper = record.paper_values;
  const methods = ["DFT", "GW"].filter(method => paperGap(record, method));
  if (!methods.length) return "";
  const source = paper.source;
  const evidenceUrl = paperEvidenceUrl(record);
  const scopes = [...new Set(methods.map(method => paperGap(record, method).scope).filter(Boolean))];
  const scopeHtml = scopes.map(scope => `<p class="definition-note"><strong>Source scope</strong> ${esc(paperText(record, scope, "scope"))}</p>`).join("");
  return `<details class="reference-source"><summary>Reference &amp; source evidence <span>Table ${esc(source.table)}</span></summary><div class="reference-body"><p>${esc(source.title)} · PDF p. ${esc(source.pdf_page)} · Table ${esc(source.table)}${source.doi ? ` · DOI ${esc(source.doi)}` : ""}</p><p>The database values are shown once above. This reference records their source; original result files and scientific status remain unchanged.</p>${scopeHtml}<p>${esc(paperText(record, paper.notes || "EXX is archive-derived; the reference has no EXX main column.", "notes"))}</p><p>${evidenceUrl ? `<a href="${esc(evidenceUrl)}" target="_blank" rel="noopener">Download source extract ↗</a>` : paper.evidence ? `Download source extract: see the file links in the <a href="${esc(recordJsonUrl(record))}">full record JSON</a>.` : ""}</p></div></details>`;
}
// The same record, as an agent or a script reads it: the MCP calls that
// return it and the static JSON URL behind them. Band tables are offered only
// when the record archives an ABACUS band export the server can parse.
const apiBox = record => {
  const id = JSON.stringify(record.id);
  const calls = [`get_material {"record_id": ${id}}`, `list_files {"record_id": ${id}}`];
  if (filesOf(record, "results").some(file => /(?:^|\/)(?:KS|EXX|GW)_band(?:s|_spin_1)\.dat$/.test(file.path || ""))) calls.push(`get_band_table {"record_id": ${id}, "method": "GW"}`);
  if (gapsListed(record)) calls.push(`compare_gaps {"material": ${JSON.stringify(record.material)}}`);
  const url = recordJsonUrl(record);
  return `<details class="api-box" id="record-api"><summary>API &amp; agent access</summary><div class="api-body"><p>This record is plain JSON. Agents connected to the <a href="#/agents">LibRPA MCP server</a> can call these read-only tools; scripts can fetch the same file over HTTPS and verify each payload's SHA-256.</p><div class="code-block"><button type="button" class="copy-button" data-copy>Copy</button><pre><code>${esc(calls.join("\n"))}</code></pre></div><div class="code-block"><button type="button" class="copy-button" data-copy>Copy</button><pre><code>curl -sL ${esc(url)} -o record.json</code></pre></div><p class="api-url"><span>Record JSON</span><a href="${esc(url)}" target="_blank" rel="noopener">${esc(url)}</a></p></div></details>`;
};
const gapsListed = record => ["DFT", "EXX", "GW"].some(method => bandGap(record, method) !== null);
const jsonLd = record => {
  const ld = { "@context": "https://schema.org", "@type": "Dataset", name: `${record.material} — LibRPA Materials Database`, description: record.summary?.observable, license: record.source?.license, isAccessibleForFree: true, url: recordPageUrl(record), identifier: record.id, variableMeasured: (record.properties || []).map(p => p.label).filter(Boolean).slice(0, 10) };
  // Script contents are raw text, not HTML entities. Escape '<' to prevent
  // a record title from terminating the script without changing JSON values.
  return `<script type="application/ld+json" data-jsonld>${JSON.stringify(ld).replace(/</g, "\\u003c")}</script>`;
};
const compareTable = (record, peers) => {
  if (!peers.length) return "";
  const val = r => { const p = primaryResult(r); return p && typeof p.value === "number" ? `${p.value.toFixed(5)} <small>${esc(p.unit)}</small>` : "—"; };
  const rows = [record, ...peers].map(r => `<tr${r === record ? ' class="compare-self"' : ""}><th scope="row"><a href="${materialLink(r)}">${esc(r.material)}</a><span class="table-description">${esc(r.id)} · ${esc(recordTypeLabel(r))}</span></th><td>${esc(workflowLabel(r))}</td><td class="numeric">${val(r)}</td></tr>`).join("");
  return `<div class="compare-panel"><table class="compare-table"><caption class="sr-only">Comparison across related calculations</caption><thead><tr><th scope="col">Material</th><th scope="col">Software</th><th scope="col">Primary result</th></tr></thead><tbody>${rows}</tbody></table></div>`;
};
const bulkDownloadButton = record => {
  const allFiles = [...filesOf(record, "inputs"), ...filesOf(record, "results"), ...filesOf(record, "logs"), ...filesOf(record, "figures")];
  const unique = [...new Map(allFiles.map(f => [f.path, f])).values()];
  return `<button type="button" class="outline-button bulk-download" data-bulk-download data-file-count="${unique.length}">Download all files (${unique.length}) <span aria-hidden="true">↓</span></button>`;
};
const materialLink = record => `#/material/${encodeURIComponent(record.id)}`;
const basisLink = set => `#/basis/${encodeURIComponent(set.id)}`;
const section = (id, number, title, body, open = false, badge = "") => `<details class="detail-section" id="${id}" ${open ? "open" : ""}><summary><span class="section-number">${number}</span><h2>${title}</h2>${badge ? `<span class="section-badge">${badge}</span>` : ""}<span class="expand-mark" aria-hidden="true">+</span></summary><div class="section-body">${body}</div></details>`;
const jump = (id, title) => `<button type="button" data-section="${id}">${title}</button>`;
const chips = methods => methods.map(methodTag).join("");
const formatField = value => esc(typeof value === "object" ? JSON.stringify(value) : value ?? "—");
const figureGrid = files => `<div class="figure-grid">${files.map(file => {
  const url = fileUrl(file);
  if (!url) return '<div class="notice warning">Figure link unavailable.</div>';
  const mirror = fileMirrorUrl(file);
  const external = isExternalFile(file);
  // When the primary archive cannot serve the image (for example on
  // networks that cannot route to it), retry once through the mirror.
  const fallback = mirror ? ` onerror="this.onerror=null;this.src='${esc(mirror)}'"` : "";
  return `<figure><a href="${esc(url)}" target="_blank" rel="noopener"><img loading="lazy" decoding="async" src="${esc(url)}"${fallback} alt="${esc(fileName(file))}"></a><figcaption><span>${esc(fileName(file))}</span><a href="${esc(url)}" download="${esc(downloadName(file))}"${external ? ' data-blob-download="1" rel="noreferrer"' : ""}>Download figure ↓</a></figcaption></figure>`;
}).join("")}</div>`;

function softwareInfo(record) {
  const frontend = workflowFrontend(record);
  const frontendName = frontendLabel(record);
  // List the codes the record actually names. An exciton record carries LibBSE
  // beside the front end and LibRPA, and omitting it would leave the code that
  // produced the spectrum uncredited.
  const apps = [frontend, "librpa", "libbse"].filter(name => record.software?.[name]);
  return apps.map(name => {
    const app = record.software?.[name] || {};
    const fullCommit = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/i.test(app.commit || "");
    const url = /^https:\/\/github\.com\/[^\s]+$/.test(app.source_url || "") && fullCommit ? `${app.source_url.replace(/\/$/, "")}/commit/${app.commit}` : null;
    const identity = url ? `<a href="${esc(url)}" target="_blank" rel="noopener">Source code ↗</a>` : '<span>Calculation software</span>';
    const displayName = name === frontend ? frontendName
      : name === "libbse" ? "LibBSE" : "LibRPA";
    return `<div class="software-entry"><h3>${displayName}</h3>${identity}${app.identity_note ? `<p>${esc(app.identity_note)}</p>` : ""}</div>`;
  }).join("");
}

function basisBindings(record, sets) {
  const byId = new Map(sets.map(s => [s.id, s]));
  const aimsNote = workflowFrontend(record) === "fhi_aims" ? '<p class="definition-note"><strong>Species defaults</strong> FHI-aims species-default tiers (for example intermediate_gw) are FHI-aims\' own classification, inlined in this calculation\'s archived control.in. They are recorded as per-calculation evidence and are not catalogued in the basis library, which indexes ABACUS pseudopotential, physical-orbital, and auxiliary-basis records.</p>' : "";
  const exact = (record.species || []).map(species => {
    const set = byId.get(species.set_id);
    if (!set) {
      const label = workflowFrontend(record) === "fhi_aims" ? "FHI-aims species defaults" : "Basis record not published";
      return `<div class="binding-card"><div class="binding-heading"><h3>${esc(species.element)} <span>${esc(label)}</span></h3></div><p class="binding-id">${esc(species.linkage || "Species defaults are inlined in this calculation's control.in.")}</p></div>`;
    }
    const files = boundFiles(set, species).filter(f => ["pp", "nao", "abf", "for_aux"].includes(f.role));
    // A calculation page names the basis the same way the basis page does: what
    // it contains, then the id as bookkeeping. Two pages describing one basis in
    // two different languages is how the id became the only thing readers saw.
    const facts = set.label ? `${esc(set.label.sentence)}` : `<p class="binding-id">${esc(set.id)}</p>`;
    return `<div class="binding-card"><div class="binding-heading"><h3>${esc(set.element)} <span>${esc(set.family || "Basis set")}</span></h3><a href="${basisLink(set)}">Basis record ↗</a></div><p class="binding-facts">${facts}</p><p class="binding-id">${esc(set.id)}</p>${renderFiles(files)}</div>`;
  }).join("");
  const candidates = (record.basis_candidates || []).map(candidate => {
    const set = byId.get(candidate.set_id);
    const name = `${esc(candidate.element)} · ${esc(set?.family || candidate.set_id)}`;
    const heading = set ? `<a href="#/basis/${encodeURIComponent(candidate.set_id)}">${name}</a>` : `<span>${name}</span>`;
    return `<li>${heading}<span>${esc(candidate.scope || "Related basis data")}</span></li>`;
  }).join("");
  return `${aimsNote}<p class="section-intro">Recorded calculation filenames are used for downloads when available.</p>${exact}${candidates ? `<details class="candidate-section"><summary>Related basis records (${record.basis_candidates.length})</summary><ul class="candidate-list">${candidates}</ul></details>` : ""}`;
}

function sameStructureNotice(record, allRecords) {
  const peers = sameStructureRecords(record, allRecords);
  if (!peers.length) return "";
  return `<div class="notice same-structure"><strong>Same-structure calculations</strong><p>This structure has ${peers.length === 1 ? "1 other" : `${peers.length} other`} independent calculation${peers.length > 1 ? "s" : ""} in the database. Compare gap values directly:</p>${compareTable(record, peers)}</div>`;
}

function crossFrontendNotice(record, allRecords) {
  const peers = crossFrontendRecords(record, allRecords);
  if (!peers.length) return "";
  return `<div class="notice cross-frontend"><strong>Same material across frontends</strong><p>This material is also covered by ${peers.length === 1 ? "1 other record from" : `${peers.length} other records from`} the ${esc(frontendLabel(peers[0]))} frontend. Those runs set their structures independently, so the values are cross-frontend reference points:</p>${compareTable(record, peers)}</div>`;
}

function sourceInfo(record) {
  const source = record.source || {};
  const safeRepository = /^https:\/\/github\.com\/[^\s]+$/.test(source.repository || "");
  return `<dl class="metadata-list"><dt>Calculation ID</dt><dd><code>${esc(record.id)}</code></dd><dt>Collection</dt><dd>${esc(source.collection || "—")}</dd>${safeRepository ? `<dt>Source repository</dt><dd><a href="${esc(source.repository)}" target="_blank" rel="noopener">${esc(source.repository.replace("https://github.com/", ""))} ↗</a></dd>` : ""}<dt>Observable</dt><dd>${esc(record.summary?.observable || "—")}</dd></dl>`;
}

function archiveCompletenessNotice(record) {
  const state = record.archive_completeness;
  if (!state || state.status !== "incomplete" || !Array.isArray(state.issues) || !state.issues.length) return "";
  const items = state.issues.map(issue => {
    const separator = issue.indexOf(": ");
    const text = separator >= 0 ? issue.slice(separator + 2) : issue;
    return `<li>${esc(text)}</li>`;
  }).join("");
  return `<div class="notice"><strong>Archive completeness: incomplete</strong><p>This record is retained with the missing-evidence items below; they are tracked in the <a href="missing-evidence.html">missing-evidence checklist</a> and do not alter the archived numerical results.</p><ul>${items}</ul></div>`;
}

export function renderMaterial(record, sets, allRecords = [], { cite = false } = {}) {
  const inputs = filesOf(record, "inputs");
  const results = filesOf(record, "results");
  const logs = filesOf(record, "logs");
  const figureFiles = filesOf(record, "figures");
  const figures = figureFiles.filter(f => /\.(?:svg|png|jpe?g|webp)$/i.test(f.path));
  const primaryFigures = figures.filter(file => file.display_priority === "primary");
  const mainFigures = primaryFigures.length ? primaryFigures : figures;
  // One results layer: numerical outputs, every archived figure (primary
  // render plus additional source figures and sidecars), and run logs live
  // together so the page presents exactly three file layers - inputs, basis
  // payloads, and results. The band section renders primary figures only.
  const resultsFiles = (() => {
    const seen = new Set();
    return [...results, ...figureFiles, ...logs].filter(file => {
      if (typeof file?.path !== "string" || seen.has(file.path)) return false;
      seen.add(file.path);
      return true;
    });
  })();
  const structure = inputs.filter(f => /(?:^|__)(STRU(?:\.cif)?|geometry\.in|POSCAR)$|\.cif$/i.test(f.path.split("/").at(-1)));
  const properties = record.properties || [];
  const visibleProperties = properties.filter(property => property.status !== "failed");
  const rpa = visibleProperties.filter(p => p.key === "rpa_correlation_energy");
  const limited = restrictedGap(record);
  const type = recordType(record);
  const largeSystem = type === "large_system_gw";
  const rpaEnergy = type === "rpa_energy";
  const readerConversion = type === "reader_conversion";
  const validationState = readerConversion ? (record.associated_gw_run?.scheduler_state === "COMPLETED" ? "Reader-format provenance with linked GW completion audit" : "Reader-format provenance record") : largeSystem ? "Large-system GW calculation" : type === "rpa_energy" ? "RPA energy calculation" : "GW calculation";
  // The uploaded record is the record. Do not re-litigate its scope above the
  // headline: the gap definition note in Overview already states what the value is.
  const scopedObservable = "";
  const overview = `${scopedObservable}${sameStructureNotice(record, allRecords)}${crossFrontendNotice(record, allRecords)}${archiveCompletenessNotice(record)}${referenceInfo(record)}<p class="detail-note">Calculation data, methods, and provenance are organized in the sections below.</p>${sourceInfo(record)}${record.summary?.gap_definition ? `<p class="definition-note"><strong>Gap definition</strong> ${esc(record.summary.gap_definition)}</p>` : ""}`;
  // Several archived files often describe the same crystal: a recovered STRU
  // copied into two stage directories, or the same cell written for SCF and for
  // the band path. Byte-identical files are grouped here without any download;
  // files that differ only in text (stripped orbitals, rewritten asset paths)
  // collapse in installStructurePreview once their parsed structures match.
  const structureGroups = groupStructureFiles(structure);
  const structureHtml = structure.length ? structureGroups.map(({ file, preview, sameAs }) => `<div class="structure-attachment">${renderFiles([file], { input: true })}${preview ? structurePreview(file) : structurePreview(file, { sameAs })}</div>`).join("") : '<div class="empty-panel"><h3>Structure data</h3><p>This record presents the calculation results and attached provenance files; no separate STRU, CIF, or equivalent structure file is listed.</p></div>';
  const bandsHtml = `<p class="section-intro">Figure style and data contracts: <a href="../references/plotting.md">plotting reference</a> · <a href="https://github.com/AroundPeking/LibRPA-database/blob/main/scripts/generate_band_figures.py" target="_blank" rel="noopener">reusable band-figure script ↗</a>. Each method uses its own occupied path VBM. The y range shows the full extent of the selected curves without adding bands.</p>${mainFigures.length ? `${figureGrid(mainFigures)}<p class="definition-note">Band figures follow the recorded k-path; refer to the definition and scope in Overview.</p>` : '<p class="empty-panel">No band figures are recorded; the archived result files are listed under Results files.</p>'}`;
  const sampledPbe = sampledGridGap(record, "PBE");
  const sampledGw = sampledGridGap(record, "G0W0");
  const resultsHtml = `<div class="notice"><strong>Regular-grid quasiparticle result</strong><p>This calculation completed the recorded quasiparticle table without a band-path input. These gaps are sampled Γ-point observables and are not presented as global fundamental gaps.</p></div><div class="metric-grid"><div><span>Sampling</span><strong>${esc(record.workflow?.sampling_label || "Γ point on the regular grid")}</strong></div><div><span>QP states</span><strong>${esc(record.computational_scale?.state_count ?? "—")}</strong></div><div><span>Occupied states</span><strong>${esc(record.computational_scale?.occupied_states ?? "—")}</strong></div><div><span>Unoccupied states</span><strong>${esc(record.computational_scale?.unoccupied_states ?? "—")}</strong></div></div>`;
  const primary = primaryResult(record);
  const deltaSternheimer = record?.workflow?.response === "delta_sternheimer";
  const rpaHeadline = primary?.label || "RPA correlation energy";
  const rpaNoticeBody = deltaSternheimer
    ? "This record archives a Delta-Sternheimer RPA campaign: the linear response of the production system and of its atom references is solved by the Sternheimer scheme, and the headline energy is assembled from those archived runs. Its definition and evidence files are documented in the Properties section."
    : "This calculation completed the recorded RPA correlation task on the production cluster. The value is an energetic observable of the whole supercell, not a band gap; its definition and evidence file are documented in the Properties section.";
  const rpaResultsHtml = `<div class="notice"><strong>${esc(rpaHeadline)}</strong><p>${rpaNoticeBody}</p></div><div class="metric-grid"><div><span>Observable</span><strong>${esc(rpaHeadline)}</strong></div><div><span>Value</span><strong class="${primary ? "" : "no-result"}">${primary ? `${formatField(primary.value)} <small>${esc(primary.unit)}</small>` : "—"}</strong></div><div><span>Workflow task</span><strong>${esc(record.workflow?.task === "rpa_correlation" ? "RPA correlation" : "RPA")}</strong></div></div>${primary?.scope ? `<p class="definition-note"><strong>Definition</strong> ${esc(primary.scope)}</p>` : ""}`;
  const conversion = record.conversion || {};
  const associatedGw = record.associated_gw_run || {};
  const associatedGwCompleted = associatedGw.scheduler_state === "COMPLETED";
  const gapInfo = associatedGw.gap || {};
  const ksGapAvailable = gapInfo.ks_available && typeof gapInfo.ks_value === "number" && Number.isFinite(gapInfo.ks_value);
  const gwGapAvailable = gapInfo.g0w0_available && typeof gapInfo.g0w0_value === "number" && Number.isFinite(gapInfo.g0w0_value);
  const gapAvailable = ksGapAvailable && gwGapAvailable;
  const associatedGwHtml = associatedGwCompleted ? `<h3 class="subheading">Associated historical GW run</h3><div class="notice"><strong>Original GW output provenance</strong><p>${gapAvailable ? "The historical run completed and the complete QP output is verified on the production cluster. Frontier states 4096 and 4097 are present, yielding sampled Γ gaps below." : "The historical run completed, but the archived evidence does not verify both sampled Γ frontier gaps."} ${gapAvailable ? "1464 high-energy unoccupied states have nonfinite QP values; the full-spectrum finite-table contract is not satisfied." : "Only independently available KS/GW values are shown; missing values require their corresponding frontier rows."} The skipped k-path is a separate limitation.</p><p><strong>${esc(associatedGw.fermi_energy?.value ?? "—")} ${esc(associatedGw.fermi_energy?.unit || "")}</strong> is the recorded Fermi energy, not a gap.</p></div><div class="metric-grid"><div><span>GW wall time</span><strong>${esc(Number.isInteger(associatedGw.elapsed_seconds) ? `${Math.floor(associatedGw.elapsed_seconds / 3600)}:${String(Math.floor((associatedGw.elapsed_seconds % 3600) / 60)).padStart(2, "0")}:${String(associatedGw.elapsed_seconds % 60).padStart(2, "0")}` : "—")}</strong></div><div><span>Nodes</span><strong>${esc(associatedGw.nodes ?? "—")}</strong></div><div><span>CPUs</span><strong>${esc(associatedGw.cpus ?? "—")}</strong></div><div><span>Band path</span><strong>Not available</strong></div><div><span>Sampled Γ PBE gap</span><strong class="${ksGapAvailable ? "" : "no-result"}">${ksGapAvailable ? `${gapInfo.ks_value.toFixed(5)} <small>eV</small>` : "Unavailable"}</strong></div><div><span>Sampled Γ G0W0 gap</span><strong class="${gwGapAvailable ? "" : "no-result"}">${gwGapAvailable ? `${gapInfo.g0w0_value.toFixed(5)} <small>eV</small>` : "Unavailable"}</strong></div></div>` : "";
  const conversionHtml = `<div class="notice"><strong>${associatedGwCompleted ? "Reader-v1 conversion with linked GW completion audit" : "Reader-v1 conversion only"}</strong><p>${esc(record.scientific_scope?.statement || "This record documents data-format conversion and does not claim a completed RPA or GW calculation.")}</p></div><div class="metric-grid"><div><span>Atoms</span><strong>${esc(atomCount(record) ?? "—")}</strong></div><div><span>Matrix rows</span><strong>${esc(record.computational_scale?.matrix_rows ?? "—")}</strong></div><div><span>Matrix columns</span><strong>${esc(record.computational_scale?.matrix_columns ?? "—")}</strong></div><div><span>Conversion wall time</span><strong>${esc(Number.isInteger(conversion.elapsed_seconds) ? `${Math.floor(conversion.elapsed_seconds / 60)}m ${conversion.elapsed_seconds % 60}s` : "—")}</strong></div></div>${associatedGwHtml}`;
  const performance = performanceSummary(record);
  const scaleHtml = `<p class="section-intro">Recorded system size and execution resources for this immutable run.</p><div class="metric-grid"><div><span>Atoms</span><strong>${esc(atomCount(record) ?? "—")}</strong></div><div><span>Atomic orbitals</span><strong>${esc(record.computational_scale?.ao_count ?? "—")}</strong></div>${performance.map(item => `<div><span>${esc(item.label)}</span><strong>${esc(item.value)}</strong></div>`).join("")}</div>${record.auxiliary_basis?.mode === "pca_generated" ? `<p class="definition-note"><strong>Auxiliary basis</strong> Generated from NAO products by PCA with threshold ${esc(record.auxiliary_basis.threshold)}. No explicit .abfs payload is claimed for this run.</p>` : ""}`;
  const propertyDefault = getPropertyCategories(visibleProperties).find(category => visibleProperties.some(property => property?.category === category.slug))?.slug ?? "electronic";
  const propertyFiles = filesByPath(record);
  const propsHtml = `<p class="section-intro">Evidence-linked properties. Empty categories are available for future contributions, not zero-valued results.</p><div class="property-tabs" role="tablist" aria-label="Property categories">${renderPropertyTabs(visibleProperties, propertyDefault)}</div><div class="property-panel" id="property-panel" role="tabpanel" tabindex="0" aria-labelledby="property-tab-${esc(propertyDefault)}">${renderPropertyPanel(visibleProperties, propertyDefault, propertyFiles)}</div>`;
  const declaredUrl = (record, rawPath) => {
    // Receipt paths are record metadata; resolve them through the declared
    // file entries so referenced tiers link to the external archive.
    const entry = filesByPath(record).get(rawPath);
    return entry ? fileUrl(entry) : publicPath(rawPath);
  };
  const partialInputNotice = record.source?.stage_input_receipt ? `<div class="notice"><strong>Stage-resolved calculation inputs</strong><p>Controls are organized by their original calculation stage. File transformations are recorded in the accompanying receipt.</p><a href="${esc(declaredUrl(record, record.source.stage_input_receipt))}" target="_blank" rel="noopener">View stage-input receipt ↗</a>${record.source.producer_assets_receipt ? `<p>PP/NAO/ABF names are documented separately from the original STRU and producer manifests.</p><a href="${esc(declaredUrl(record, record.source.producer_assets_receipt))}" target="_blank" rel="noopener">View producer-assets receipt ↗</a>` : ""}</div>` : "";
  const inputsHtml = inputs.length ? `${partialInputNotice}<div class="notice"><strong>${inputs.length} calculation input files</strong><p>These files belong to <code>${esc(record.id)}</code>. Associated PP / NAO / auxiliary data are linked in the Basis section.</p></div>${renderFiles(inputs, { input: true })}` : '<div class="notice"><strong>Calculation results</strong><p>Numerical results and provenance are available in the other sections of this record.</p></div>';
  const evidenceHtml = `<p class="section-intro">Software identities recorded for this run. Calculation logs and numerical outputs are listed under Results files.</p><div class="software-grid">${softwareInfo(record)}</div>`;
  const resultsFilesHtml = resultsFiles.length
    ? `<p class="section-intro">All archived output files for this record: numerical results, figure sources and metadata, and calculation logs. Inputs and basis payloads are listed in their own sections.</p>${renderFiles(resultsFiles)}`
    : '<div class="empty-panel"><h3>Results files</h3><p>This record lists no separate result files.</p></div>';
  const resultStrip = readerConversion ? (associatedGwCompleted ? ((ksGapAvailable || gwGapAvailable) ? `<div><span>Atoms</span><strong>${esc(atomCount(record) ?? "—")}</strong></div><div><span>Reader-v1 states</span><strong>${esc(record.computational_scale?.matrix_rows ?? "—")}</strong></div><div><span>Sampled Γ PBE gap</span><strong class="${ksGapAvailable ? "" : "no-result"}">${ksGapAvailable ? `${gapInfo.ks_value.toFixed(5)} <small>eV</small>` : "Unavailable"}</strong></div><div class="result-primary"><span>Sampled Γ G0W0 gap</span><strong class="${gwGapAvailable ? "" : "no-result"}">${gwGapAvailable ? `${gapInfo.g0w0_value.toFixed(5)} <small>eV</small>` : "Unavailable"}</strong><small class="gap-scope">${gapAvailable ? "Frontier states verified; not a full-spectrum finite-table result" : "Only available frontier values are shown; the archived evidence is incomplete"}</small></div>` : `<div><span>Atoms</span><strong>${esc(atomCount(record) ?? "—")}</strong></div><div><span>Reader-v1 states</span><strong>${esc(record.computational_scale?.matrix_rows ?? "—")}</strong></div><div><span>Sampled Γ PBE gap</span><strong class="no-result">Unavailable</strong></div><div class="result-primary"><span>Sampled Γ G0W0 gap</span><strong class="no-result">Unavailable</strong><small class="gap-scope">Frontier rows not archived</small></div>`) : `<div><span>Atoms</span><strong>${esc(atomCount(record) ?? "—")}</strong></div><div><span>Reader-v1 matrix</span><strong>${esc(record.computational_scale?.matrix_rows ?? "—")} × ${esc(record.computational_scale?.matrix_columns ?? "—")}</strong></div><div><span>RPA result</span><strong class="no-result">Not claimed</strong></div><div class="result-primary"><span>GW result</span><strong class="no-result">Not claimed</strong><small class="gap-scope">Conversion record</small></div>`) : largeSystem ? `<div><span>Atoms</span><strong>${esc(atomCount(record) ?? "—")}</strong></div><div><span>QP states</span><strong>${esc(record.computational_scale?.state_count ?? "—")}</strong></div><div><span>Sampled Γ PBE gap</span><strong class="${sampledPbe ? "" : "no-result"}">${sampledPbe ? gapText(sampledPbe.value) : "—"}</strong></div><div class="result-primary"><span>Sampled Γ G0W0 gap</span><strong class="${sampledGw ? "" : "no-result"}">${sampledGw ? gapText(sampledGw.value, 5) : "—"}</strong><small class="gap-scope">Regular-grid observable</small></div>` : `${["DFT", "EXX", "GW"].map(method => {
    const paper = paperGap(record, method);
    const unavailableRestricted = method === "GW" && limited && !paper;
    return `<div class="${method === "GW" ? "result-primary" : ""}"><span>${method} band gap</span><strong class="${unavailableRestricted ? "no-result" : ""}">${unavailableRestricted ? "—" : gapText(bandGap(record, method), paper?.precision ?? 3)}</strong></div>`;
  }).join("")}<div><span>RPA correlation energy</span><strong class="${rpa.length ? "" : "no-result"}">${rpa.length === 1 ? `${formatField(rpa[0].value)} <small>${esc(rpa[0].unit)}</small>` : "—"}</strong></div>`;
  const resultId = readerConversion ? "record-conversion" : (largeSystem || rpaEnergy) ? "record-results" : "record-bands";
  const resultTitle = readerConversion ? (associatedGwCompleted ? "Reader-v1 conversion &amp; GW audit evidence" : "Reader-v1 conversion evidence") : (largeSystem || rpaEnergy) ? "Results &amp; evidence" : "Electronic bands";
  const resultBadge = readerConversion ? (associatedGwCompleted ? (gapAvailable ? "Γ gaps verified" : (ksGapAvailable || gwGapAvailable) ? "Γ gap partially available" : "Γ gaps unavailable") : `${record.computational_scale?.matrix_rows ?? "—"} states`) : largeSystem ? `${record.computational_scale?.state_count ?? "—"} QP states` : rpaEnergy ? (primary ? (deltaSternheimer ? "Delta-ST RPA energy" : "RPA energy") : "No value") : `${figures.length} figures`;
  // Optical response is its own section, never a gap column: an excitonic
  // spectrum and an exciton binding energy are not quasiparticle gaps. The test
  // is "does this record carry optical data", not "is the method called BSE",
  // so a future TDDFT or GW-BSE variant lands here without a code change.
  const opticalProperties = visibleProperties.filter(property => property.category === "optical");
  // Match the file's own name and label, never the whole path: the path
  // contains the record id, and a record called "...-exciton-..." would then
  // pull every one of its band figures into this section.
  const opticalFigures = figureFiles.filter(file => /\.(?:svg|png|jpe?g|webp)$/i.test(file.path)
    && /bse|opti|absorp|exciton|dielectric|spectrum/i.test(`${fileName(file)} ${file.label || ""}`));
  const bseFigures = opticalFigures.filter(file => file.display_priority === "primary");
  const showOptical = opticalProperties.length > 0 || opticalFigures.length > 0;
  const opticalHtml = `<p class="section-intro">Excitonic and optical response recorded for this calculation. Values keep the definition and unit of the source run; a binding energy is not a band gap.</p>${opticalFigures.length ? figureGrid(bseFigures.length ? bseFigures : opticalFigures) : ""}${opticalProperties.length ? `<div class="metric-grid">${opticalProperties.map(property => `<div><span>${esc(property.label || property.key)}${property.method ? ` · ${esc(property.method)}` : ""}</span><strong>${formatField(property.value)}${property.unit ? ` <small>${esc(property.unit)}</small>` : ""}</strong></div>`).join("")}</div>` : ""}`;
  const opticalBadge = opticalProperties.length ? `${opticalProperties.length} values` : `${opticalFigures.length} figures`;
  const sourceScopeHtml = `<p class="section-intro">This is a provenance record for a completed format conversion.${associatedGwCompleted ? (gapAvailable ? " The complete QP output is verified on the production cluster; frontier states are present and sampled Γ gaps are available." : " It also preserves a bounded audit of a separate completed historical GW run without promoting an unavailable numerical gap.") : " It is intentionally separate from RPA/GW result records."}</p>${sourceInfo(record)}<p class="definition-note"><strong>Scientific scope</strong> ${esc(record.scientific_scope?.statement || "No scientific result is claimed.")}</p>`;
  // Sections are an ordered list rather than a chain of nested ternaries: each
  // entry names its id, the title shown in the outline, the title shown in the
  // body, and its body. Numbering follows the array, so inserting the optical
  // section renumbers everything after it automatically.
  const sections = readerConversion ? [
    { id: "record-overview", nav: "Overview", title: "Overview", html: overview, open: true },
    { id: "record-conversion", nav: associatedGwCompleted ? "Conversion & GW audit" : "Conversion evidence", title: resultTitle, html: conversionHtml, open: true, badge: resultBadge },
    { id: "record-inputs", nav: `Input files · ${inputs.length}`, title: "Input files", html: inputsHtml, open: true, badge: inputs.length ? `${inputs.length} files` : "No inputs" },
    { id: "record-results-files", nav: `Results files · ${resultsFiles.length}`, title: "Results files", html: resultsFilesHtml, badge: resultsFiles.length ? `${resultsFiles.length} files` : "No files" },
    { id: "record-source", nav: "Source & scope", title: "Source &amp; scientific scope", html: sourceScopeHtml, open: true, badge: associatedGwCompleted ? (gapAvailable ? "GW gaps verified" : "GW audit linked") : "Conversion only" },
    { id: "record-evidence", nav: "Software", title: "Software", html: evidenceHtml },
  ] : [
    { id: "record-overview", nav: "Overview", title: "Overview", html: overview, open: true },
    { id: "record-structure", nav: "Crystal structure", title: "Crystal structure", html: structureHtml, badge: structure.length ? `${structure.length} files` : "Structure" },
    ...(largeSystem || rpaEnergy
      ? [{ id: "record-results", nav: "Results & evidence", title: resultTitle, html: largeSystem ? resultsHtml : rpaResultsHtml, open: true, badge: resultBadge }]
      : [
          { id: "record-bands", nav: "Electronic bands", title: resultTitle, html: bandsHtml, open: true, badge: resultBadge },
          ...(showOptical ? [{ id: "record-optical", nav: "Excitons & optical", title: "Excitons &amp; optical response", html: opticalHtml, open: true, badge: opticalBadge }] : []),
        ]),
    ...(largeSystem || rpaEnergy ? [{ id: "record-scale", nav: "Computational scale", title: "Computational scale &amp; performance", html: scaleHtml, open: true, badge: `${atomCount(record) ?? "—"} atoms` }] : []),
    { id: "record-properties", nav: "Properties", title: "Properties", html: propsHtml, badge: `${visibleProperties.length} values` },
    { id: "record-inputs", nav: `Input files · ${inputs.length}`, title: "Input files", html: inputsHtml, open: true, badge: inputs.length ? `${inputs.length} files` : "Results record" },
    { id: "record-basis", nav: "Pseudopotentials & basis", title: "Pseudopotentials &amp; basis", html: basisBindings(record, sets) },
    { id: "record-results-files", nav: `Results files · ${resultsFiles.length}`, title: "Results files", html: resultsFilesHtml, badge: resultsFiles.length ? `${resultsFiles.length} files` : "No files" },
    { id: "record-evidence", nav: "Software", title: "Software", html: evidenceHtml },
  ];
  const nav = sections.map(item => jump(item.id, item.nav)).join("");
  const body = sections.map((item, index) => section(item.id, String(index + 1).padStart(2, "0"), item.title, item.html, item.open === true, item.badge || "")).join("");
  return `<div class="breadcrumb"><a href="#/materials">Materials</a><span>/</span><span>${esc(record.material)}</span></div>
    <div class="detail-header"><div><div class="detail-tags"><span class="dimension-tag">${esc(record.dimension.toUpperCase())}</span><span class="record-type-tag">${esc(recordTypeLabel(record))}</span><span class="frontend-tag">${esc(workflowLabel(record))}</span>${chips(methodNames(record))}${spinPolTag(record)}${socTag(record)}</div><h1>${formulaHtml(record.material)}${record.formula && record.formula !== record.material ? ` <small>${formulaHtml(record.formula)}</small>` : ""}</h1><p class="detail-id"><code>${esc(record.id)}</code><button type="button" class="copy-id" data-copy="${esc(record.id)}" aria-label="Copy record ID ${esc(record.id)}">Copy ID</button><a href="${materialLink(record)}?cite=1" data-section="record-citation">Cite this record</a></p></div><div class="detail-header-actions"><button class="primary-button" type="button" data-section="${readerConversion ? "record-inputs" : "record-inputs"}">${readerConversion ? (inputs.length ? `View inputs (${inputs.length})` : "Input availability") : inputs.length ? `View inputs (${inputs.length})` : "Input availability"}<span aria-hidden="true">↓</span></button>${bulkDownloadButton(record)}<button class="outline-button" type="button" data-section="record-api">API <span aria-hidden="true">{ }</span></button></div></div>
    <p class="record-status">${esc(validationState)}</p><div class="result-strip">${resultStrip}</div>
    ${citationBox(record, cite)}<div class="detail-layout"><aside class="section-nav"><p class="kicker">IN THIS RECORD</p>${nav}<div class="section-tools"><button type="button" class="text-button" data-expand="true">Expand all</button><button type="button" class="text-button" data-expand="false">Collapse all</button></div></aside><div class="detail-content">${body}</div></div>${apiBox(record)}${jsonLd(record)}`;
}

// The facts a reader needs first: how many electrons are in the valence, how
// big each basis is, and what this set has already produced. The id stays in
// the header as bookkeeping.
function basisFactBlock(set, linked) {
  const label = set.label;
  if (!label) {
    return '<div class="notice"><strong>Size facts not derived yet</strong><p>This record has no derived label. Run <code>scripts/basis_labels.py --write</code> to compute the valence count, the orbital and auxiliary dimensions, and the linked results from the payload bytes.</p></div>';
  }
  // Every size is per atom, and the page says so instead of leaving the reader
  // to guess whether "697" means the set or the structure.
  const figures = [
    ["Valence electrons", label.valence_electrons === null || label.valence_electrons === undefined ? "not declared" : String(label.valence_electrons)],
    ["Numerical orbital", label.orbital ? `${label.orbital.shells} · ${label.orbital.dimension_per_atom} functions per atom` : "none"],
    ["Auxiliary basis", label.auxiliary ? `${label.auxiliary.shells} · ${label.auxiliary.dimension_per_atom} functions per atom` : "none"],
  ];
  const definition = label.size_definition ? `<p class="table-description">${esc(label.size_definition)}</p>` : "";
  const results = (label.uses || []).map(use => `<li><a href="#/material/${encodeURIComponent(use.record_id)}">${esc(use.material || use.record_id)}</a>${use.formula && use.formula !== use.material ? ` <span class="table-description">${esc(use.formula)}</span>` : ""}${use.result ? ` — ${esc(use.result)}` : ' <span class="not-reported">no reported result</span>'}</li>`).join("");
  return `<div class="basis-facts-panel"><dl class="metadata-list">${figures.map(([term, value]) => `<dt>${esc(term)}</dt><dd>${esc(value)}</dd>`).join("")}</dl>${definition}<p class="basis-facts-usage">${results ? `Already used by ${label.uses.length} calculation${label.uses.length === 1 ? "" : "s"}:<ul class="linked-records">${results}</ul>` : "No calculation in the archive has used this set yet."}</p></div>`;
}

export function renderBasis(set, calculations) {
  const linked = calculations.filter(record => (record.species || []).some(s => s.set_id === set.id) || (record.basis_candidates || []).some(s => s.set_id === set.id));
  const payloads = (set.files || []).filter(file => ["pp", "nao", "abf", "for_aux"].includes(file.role));
  const evidence = (set.files || []).filter(file => !payloads.includes(file));
  return `<div class="breadcrumb"><a href="#/basis">Basis library</a><span>/</span><span>${esc(set.element)}</span></div><div class="detail-header"><div><p class="kicker">ELEMENT BASIS RECORD</p><h1>${esc(set.element)} <small>${esc(set.family || "Basis set")}</small></h1><p class="detail-id">${esc(set.id)}</p></div></div>
    ${basisFactBlock(set, linked)}
    <div class="notice"><strong>Basis data record</strong><p>${esc(set.validation_scope || "Basis data and provenance")}</p>${set.notes ? `<p>${esc(set.notes)}</p>` : ""}</div>
    ${section("basis-assets", "01", "Basis files", `<p class="section-intro">Readable download names are separate from immutable storage. Descriptive aliases are labelled explicitly; calculation-specific filenames are used where available.</p>${renderFiles(payloads)}`, true, `${payloads.length} files`)}
    ${section("basis-radial", "02", "Radial orbitals by angular momentum", radialSection(set), true, "NAO / ABF")}
    ${section("basis-calculations", "03", "Linked calculations", linked.length ? `<ul class="linked-records">${linked.map(record => `<li><a href="${materialLink(record)}"><strong>${esc(record.material)}</strong><span>${esc(record.id)}</span></a><span class="dimension-tag">${esc(record.dimension.toUpperCase())}</span><span class="relation-label">${esc(setRelation(record, set.id))}</span></li>`).join("")}</ul>` : '<p class="empty-panel">This basis record currently presents generation data independently from material calculations.</p>', true, `${linked.length} records`)}
    ${section("basis-evidence", "04", "Generation evidence &amp; source", `<dl class="metadata-list"><dt>Collection</dt><dd>${esc(set.source?.collection || "—")}</dd><dt>License</dt><dd>${esc(set.source?.license || "See the source collection terms")}</dd><dt>Generation status</dt><dd>${esc(set.generation_provenance?.status || "—")}</dd></dl>${renderFiles(evidence)}`, false, `${evidence.length} files`)}`;
}

export function installDetailActions(view, getRecord) {
  installCitationActions(view);
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
    const bulkBtn = event.target.closest("[data-bulk-download]");
    if (bulkBtn) { bulkBtn.disabled = true; const orig = bulkBtn.innerHTML; bulkBtn.innerHTML = "Preparing downloads…"; const record = getRecord(); if (record) { const allFiles = [...filesOf(record, "inputs"), ...filesOf(record, "results"), ...filesOf(record, "logs"), ...filesOf(record, "figures")]; const unique = [...new Map(allFiles.map(f => [f.path, f])).values()]; let done = 0; const next = async () => { if (done >= unique.length || bulkBtn.dataset.cancelled) { bulkBtn.disabled = false; bulkBtn.innerHTML = orig; return; } const file = unique[done++]; try { const url = fileUrl(file); if (!url) { next(); return; } const isExt = isExternalFile(file); if (isExt) { const resp = await fetch(url, { referrerPolicy: "no-referrer" }); if (!resp.ok) throw new Error(`HTTP ${resp.status}`); const blob = await resp.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = downloadName(file); a.click(); URL.revokeObjectURL(a.href); } else { const a = document.createElement("a"); a.href = url; a.download = downloadName(file); a.click(); } } catch { /* mirror fallback already in files.mjs */ } bulkBtn.innerHTML = `Downloading ${done}/${unique.length}…`; setTimeout(next, 400); }; next(); } }
  });
  function activateTab(tab) {
    const panel = view.querySelector("#property-panel");
    view.querySelectorAll(".property-tab").forEach(button => { button.setAttribute("aria-selected", String(button === tab)); button.tabIndex = button === tab ? 0 : -1; });
    panel.setAttribute("aria-labelledby", tab.id);
    panel.innerHTML = renderPropertyPanel(getRecord()?.properties || [], tab.dataset.category, filesByPath(getRecord()));
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
