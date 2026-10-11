const statusNames = {
  gw_validated: "GW validated",
  gw_diagnostic: "GW diagnostic",
  path_diagnostic: "Path diagnostic",
  pbe_only: "PBE only",
  generation_only: "Generation only",
  failed: "Failed gate",
  pending: "Pending"
};

const state = { calculations: [], sets: [], dimension: "all", status: "all", sort: "material", query: "" };
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const link = file => `<a href="../${encodeURI(file.path)}">${esc(file.label || file.path.split("/").pop())}</a>`;
const statusLabel = value => statusNames[value] || value || "Unclassified";

function render() {
  const rows = state.calculations.filter(c => {
    const basisEntries = [
      ...(c.species || []).map(s => ({ ...s, relation: "matched" })),
      ...(c.basis_candidates || []).map(s => ({ ...s, relation: "candidate" }))
    ];
    const text = [c.material, c.formula, c.id, c.status, ...basisEntries.map(s => `${s.element} ${s.set_id || ""} ${s.scope || ""}`), c.summary?.text,
      c.basis_comparison?.conclusion,
      c.software?.abacus?.commit, c.software?.librpa?.commit].join(" ").toLowerCase();
    return (state.dimension === "all" || c.dimension === state.dimension) &&
      (state.status === "all" || c.status === state.status) && text.includes(state.query);
  }).sort((a, b) => state.sort === "status"
    ? statusLabel(a.status).localeCompare(statusLabel(b.status)) || a.material.localeCompare(b.material)
    : a.material.localeCompare(b.material) || a.id.localeCompare(b.id));

  const sets = new Map(state.sets.map(s => [s.id, s]));
  document.querySelector("#result-count").textContent = `${rows.length} of ${state.calculations.length} calculations`;
  document.querySelector("#empty").hidden = rows.length !== 0;
  document.querySelector("#records").innerHTML = rows.map((c, index) => {
    const basisEntries = [
      ...(c.species || []).map(s => ({ ...s, relation: "matched" })),
      ...(c.basis_candidates || []).map(s => ({ ...s, relation: "candidate" }))
    ];
    const species = basisEntries.length
      ? basisEntries.map(s => `${esc(s.element)}${s.set_id ? ` · ${esc(s.set_id)}` : " · assets not linked"}${s.relation === "candidate" ? ` <small>(candidate: ${esc(s.scope || "contextual")})</small>` : ""}`).join("<br>")
      : "No basis linkage recorded";
    const payloads = basisEntries.map(s => sets.get(s.set_id)).filter(Boolean)
      .flatMap(s => s.files || []).filter(f => ["pp", "nao", "abf"].includes(f.role));
    const uniqueFiles = [...new Map(payloads.map(f => [f.path, f])).values()];
    const files = Object.entries(c.files || {}).flatMap(([kind, items]) => (items || []).map(file => ({ ...file, kind })));
    const plot = (c.files?.figures || []).find(f => /\.(png|jpe?g|webp)$/i.test(f.path));
    const result = c.summary || {};
    const gap = result.value == null ? "" : ` ${esc(result.value)} ${esc(result.unit || "eV")}`;
    const comparison = c.basis_comparison;
    const accepted = (comparison?.accepted_candidates || []).map(item => item.label || item.id || item);
    const failed = (comparison?.failed_candidates || []).map(item => item.label || item.id || item);
    const comparisonHtml = comparison ? `<dt>Basis comparison</dt><dd>${esc(comparison.conclusion || "")}${accepted.length ? `<br>Accepted candidates: ${esc(accepted.join(", "))}` : ""}${failed.length ? `<br>Failed candidates: ${esc(failed.join(", "))}` : ""}</dd>` : "";
    const detail = `<details><summary>Record</summary><div class="details-body"><dl>
      <dt>Record ID</dt><dd>${esc(c.id)}</dd><dt>Basis linkage</dt><dd>${species}</dd>
      <dt>ABACUS</dt><dd>${esc(c.software?.abacus?.commit || "commit not recorded")}</dd>
      <dt>LibRPA</dt><dd>${esc(c.software?.librpa?.commit || "commit not recorded")}</dd>
      <dt>Gates</dt><dd>${esc((result.gates || []).join("; ") || "not summarized")}</dd>
      <dt>Notes</dt><dd>${esc(result.notes || "")}</dd>${comparisonHtml}</dl>
      ${plot ? `<a href="../${encodeURI(plot.path)}"><img class="preview" loading="lazy" src="../${encodeURI(plot.path)}" alt="${esc(c.material)} band plot"></a>` : ""}
      <ul>${files.map(f => `<li>${esc(f.kind)}: ${link(f)}</li>`).join("")}</ul></div></details>`;
    return `<tr data-index="${index}"><td>${esc(c.material)}<span class="formula">${esc(c.formula || "")}</span></td>
      <td>${esc(c.dimension.toUpperCase())}</td><td><span class="badge ${esc(c.status)}">${esc(statusLabel(c.status))}</span></td>
      <td class="result-text">${esc(result.observable || "")}<strong>${gap}</strong><br>${esc(result.notes || "")}</td>
      <td class="file-links">${uniqueFiles.length ? uniqueFiles.map(link).join("<br>") : "No matched asset files"}</td>
      <td>${detail}</td></tr>`;
  }).join("");
}

async function start() {
  try {
    const response = await fetch("data.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    state.calculations = data.calculations || [];
    state.sets = data.basis_sets || [];
    const statusSelect = document.querySelector("#status-filter");
    [...new Set(state.calculations.map(c => c.status))].sort().forEach(status => {
      const option = document.createElement("option"); option.value = status; option.textContent = statusLabel(status); statusSelect.append(option);
    });
    document.querySelector("#search").addEventListener("input", e => { state.query = e.target.value.trim().toLowerCase(); render(); });
    document.querySelector("#status-filter").addEventListener("change", e => { state.status = e.target.value; render(); });
    document.querySelector("#sort").addEventListener("change", e => { state.sort = e.target.value; render(); });
    document.querySelectorAll("input[name=dimension]").forEach(r => r.addEventListener("change", e => { state.dimension = e.target.value; render(); }));
    render();
  } catch (error) {
    document.querySelector("#result-count").textContent = `Database could not be loaded: ${error.message}`;
  }
}
start();
