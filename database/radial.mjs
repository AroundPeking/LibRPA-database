import { esc, publicPath, fileName } from "./records.mjs";

const LETTERS = "SPDFGHIJKLMNO";
const COLORS = ["#8ce0c6", "#a0c9f6", "#eed09c", "#e2a8d8", "#b9b2ff", "#f4ad9b", "#a8dadd", "#d2db93"];
const number = token => Number(token.replace(/[dD]/g, "e"));

export function parseRadial(text, { allowHeaderMismatch = false } = {}) {
  const field = (pattern, label) => {
    const matches = [...text.matchAll(pattern)];
    if (matches.length !== 1) throw new Error(`Missing or ambiguous ${label}`);
    return matches[0][1];
  };
  const element = field(/^Element\s+([A-Z][a-z]?)\s*$/gm, "element");
  const mesh = number(field(/^Mesh\s+(\d+)\s*$/gm, "mesh"));
  const dr = number(field(/^dr\s+([^\s]+)\s*$/gm, "dr"));
  const cutoff = number(field(/^Radius Cutoff\(a\.u\.\)\s+(\S+)\s*$/gm, "cutoff"));
  const lmax = number(field(/^Lmax\s+(\d+)\s*$/gm, "Lmax"));
  if (!Number.isInteger(mesh) || mesh < 3 || mesh > 100000 || !(dr > 0) || !Number.isFinite(dr) || !(cutoff > 0) || !Number.isFinite(cutoff) || lmax >= LETTERS.length) throw new Error("Invalid radial grid/header");
  const declarations = [...text.matchAll(/^Number of ([A-Z])orbital-->\s+(\d+)\s*$/gm)];
  const counts = new Map(declarations.map(m => [LETTERS.indexOf(m[1]), Number(m[2])]));
  if (counts.size !== declarations.length || counts.size !== lmax + 1 || [...counts.keys()].some(l => l < 0 || l > lmax)) throw new Error("Angular header counts disagree");
  const blocks = [...text.matchAll(/Type\s+L\s+N\s*\n\s*(\d+)\s+(\d+)\s+(\d+)\s*\n([\s\S]*?)(?=\s*Type\s+L\s+N|$)/g)];
  const channels = [];
  const identities = new Set();
  for (const block of blocks) {
    const [type, l, n] = block.slice(1, 4).map(Number);
    if (type !== 0 || !counts.has(l) || (!allowHeaderMismatch && n >= counts.get(l)) || identities.has(`${l}/${n}`)) throw new Error("Unexpected or duplicate radial channel");
    const tokens = block[4].trim().split(/\s+/);
    const values = tokens.map(number);
    if (values.length !== mesh || values.some(x => !Number.isFinite(x)) || tokens.some(t => !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?$/.test(t))) throw new Error(`Invalid samples for l=${l}, N=${n}`);
    identities.add(`${l}/${n}`);
    const derivative = values.map((v, i) => i === 0 ? (-3 * v + 4 * values[1] - values[2]) / (2 * dr) : i === mesh - 1 ? (3 * v - 4 * values[i - 1] + values[i - 2]) / (2 * dr) : (values[i + 1] - values[i - 1]) / (2 * dr));
    const peak = Math.max(...values.map(Math.abs));
    channels.push({ l, n, values, derivative, peak, endpoint: values.at(-1), endpoint_slope: derivative.at(-1), relative_endpoint: peak ? Math.abs(values.at(-1)) / peak : 0 });
  }
  const actualCounts = Object.fromEntries([...counts.keys()].map(l => [l, channels.filter(c => c.l === l).length]));
  const headerMismatch = [...counts].some(([l, count]) => actualCounts[l] !== count);
  if (headerMismatch && !allowHeaderMismatch) throw new Error("Radial blocks do not match declared channel counts");
  channels.sort((a, b) => a.l - b.l || a.n - b.n);
  return { element, mesh, dr, cutoff, lmax, counts: Object.fromEntries(counts), actual_counts: actualCounts, header_mismatch: headerMismatch, channels, last_radius: (mesh - 1) * dr };
}

export function radialSvg(radial, l, { selected = null, mode = "raw", tail = false } = {}) {
  const channels = radial.channels.filter(c => c.l === l && (!selected || selected.includes(c.n)));
  const start = tail ? Math.max(0, Math.floor((radial.mesh - 1) * 0.8)) : 0;
  const slices = channels.map(c => ({ c, values: (mode === "derivative" ? c.derivative : c.values).slice(start) }));
  let lo = 0, hi = 0;
  for (const { values } of slices) for (const v of values) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  const margin = (hi - lo || 1) * 0.08;
  lo -= margin; hi += margin;
  const x0 = start * radial.dr, x1 = radial.last_radius;
  const x = r => 78 + (r - x0) / (x1 - x0) * 584;
  const y = v => 292 - (v - lo) / (hi - lo) * 246;
  const label = mode === "derivative" ? "dR / dr (finite difference)" : "R(r) · original stored amplitude";
  let grid = "";
  for (let i = 0; i <= 4; i++) {
    const r = x0 + (x1 - x0) * i / 4, v = lo + (hi - lo) * i / 4;
    grid += `<path d="M${x(r)} 46V292 M78 ${y(v)}H662" stroke="#2a3947" fill="none"/><text x="${x(r)}" y="315" fill="#9daebd" text-anchor="middle">${r.toFixed(2)}</text><text x="68" y="${y(v) + 4}" fill="#9daebd" text-anchor="end">${v.toPrecision(3)}</text>`;
  }
  const paths = slices.map(({ c, values }) => `<path data-channel="${c.n}" d="${values.map((v, i) => `${i ? "L" : "M"}${x((i + start) * radial.dr).toFixed(3)},${y(v).toFixed(3)}`).join(" ")}" stroke="${COLORS[c.n % COLORS.length]}" stroke-dasharray="${c.n >= COLORS.length ? "5 3" : "none"}" stroke-width="1.5" fill="none"><title>l=${l}, original N=${c.n}</title></path>`).join("");
  const diagnostic = radial.header_mismatch ? '<text x="78" y="374" fill="#eed09c">Header metadata differs from the parsed channel blocks.</text><text x="78" y="394" fill="#eed09c">The plot preserves the source header and every stored sample.</text>' : "";
  const height = radial.header_mismatch ? 410 : 355;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 ${height}" role="img" aria-label="${esc(radial.element)} l=${l} ${esc(label)}${tail ? " cutoff-tail view" : ""}${radial.header_mismatch ? " · header mismatch diagnostic" : ""}"><rect width="700" height="${height}" fill="#141d27"/><g font-family="system-ui,sans-serif" font-size="12"><text x="78" y="26" fill="#e5edf4">${esc(radial.element)} · l=${l} (${LETTERS[l].toLowerCase()}) · ${esc(label)}</text>${grid}<path d="M78 46V292H662" stroke="#9daebd" fill="none"/>${paths}<text x="370" y="341" text-anchor="middle" fill="#e5edf4">r (bohr)${tail ? " · last 20% of original grid" : ""}</text>${diagnostic}</g></svg>`;
}

export function radialSection(set) {
  const files = (set.files || []).filter(f => ["nao", "abf", "for_aux"].includes(f.role));
  return `<div class="radial-view" data-element="${esc(set.element)}"><p class="section-intro">One plot per populated angular momentum, preserving every source mesh sample and radial index N. Curves are shown without smoothing, interpolation, or renormalization. Derivatives are second-order finite differences rather than stored producer derivatives.</p>${files.length ? files.map(f => `<details class="radial-file" ${f.role === "nao" ? "open" : ""} data-radial-path="${esc(f.path)}" data-radial-sha="${esc(f.sha256)}"><summary>${esc(f.role === "nao" ? "Physical NAO" : f.role === "abf" ? "Auxiliary basis" : "For-aux generation orbitals")} · ${esc(fileName(f))}</summary><div class="radial-content"><button class="text-button" data-radial-load>Load verified radial plots</button><p class="radial-status" role="status">Source file SHA-256 is checked before plotting.</p></div></details>`).join("") : '<p class="empty-panel">This set has no listed radial NAO or auxiliary file.</p>'}<p class="definition-note">These plots describe radial shape and endpoint behavior. Periodic overlap, RI conditioning, EXX/GW accuracy, and basis completeness are separate calculation-level properties. Source header metadata is shown as recorded.</p></div>`;
}

export function installRadial(view) {
  const parsed = new WeakMap();
  const draw = card => {
    const file = card.closest(".radial-file"), data = parsed.get(file);
    const selected = [...card.querySelectorAll("input[data-radial-n]:checked")].map(e => Number(e.dataset.radialN));
    card.querySelector(".radial-chart").innerHTML = radialSvg(data, Number(card.dataset.radialL), { selected, mode: card.querySelector("select").value, tail: card.querySelector("input[data-radial-tail]").checked });
  };
  view.addEventListener("click", async event => {
    const load = event.target.closest("[data-radial-load]");
    if (load) {
      const file = load.closest(".radial-file"), content = file.querySelector(".radial-content");
      load.disabled = true;
      file.querySelector(".radial-status").textContent = "Loading original radial samples and checking SHA-256…";
      try {
        const url = publicPath(file.dataset.radialPath);
        if (!url || !/^[0-9a-f]{64}$/.test(file.dataset.radialSha)) throw new Error("Invalid data identity");
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const bytes = await response.arrayBuffer();
        const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(x => x.toString(16).padStart(2, "0")).join("");
        if (digest !== file.dataset.radialSha) throw new Error("Original radial SHA-256 mismatch");
        const data = parseRadial(new TextDecoder("utf-8", { fatal: true }).decode(bytes), { allowHeaderMismatch: true });
        parsed.set(file, data);
        const mismatch = data.element !== file.closest(".radial-view").dataset.element;
        const metadataNotes = `${mismatch ? " Header metadata note: the source element differs from the catalog element; source bytes are preserved." : ""}${data.header_mismatch ? ` Header metadata note: declared angular counts ${JSON.stringify(data.counts)} differ from parsed blocks ${JSON.stringify(data.actual_counts)}. Plots include every source block and retain the recorded header.` : ""}`;
        content.innerHTML = `<p class="radial-status ${mismatch || data.header_mismatch ? "name-warning" : ""}" role="status">SHA-256 verified · header element ${esc(data.element)} · mesh ${data.mesh} · dr ${data.dr} bohr · declared cutoff ${data.cutoff} bohr · last grid radius ${data.last_radius.toFixed(5)} bohr.${esc(metadataNotes)}</p><details class="file-integrity"><summary>Source file &amp; SHA-256</summary><code>${esc(file.dataset.radialPath)}</code><code>${digest}</code></details>${[...new Set(data.channels.map(c => c.l))].map(l => {
          const channels = data.channels.filter(c => c.l === l);
          return `<article class="radial-card" data-radial-l="${l}"><h3>l=${l} · ${LETTERS[l].toLowerCase()} · ${channels.length} radial functions</h3><div class="radial-controls"><label>Plot <select aria-label="Plot mode for l=${l}"><option value="raw">Original R(r)</option><option value="derivative">Finite-difference dR/dr</option></select></label><label><input type="checkbox" data-radial-tail> Cutoff-tail zoom</label><button class="text-button" data-radial-download>Download this SVG</button></div><div class="radial-channels">${channels.map(c => `<label style="--channel:${COLORS[c.n % COLORS.length]}"><input type="checkbox" data-radial-n="${c.n}" checked> N=${c.n}</label>`).join("")}</div><div class="radial-chart">${radialSvg(data, l)}</div><details class="radial-metrics"><summary>Endpoint values by original N</summary><div class="table-wrap"><table><thead><tr><th>N</th><th>max |R|</th><th>R(last)</th><th>|R(last)| / max |R|</th><th>dR/dr(last)</th></tr></thead><tbody>${channels.map(c => `<tr><td>${c.n}</td>${[c.peak, c.endpoint, c.relative_endpoint, c.endpoint_slope].map(v => `<td>${v.toExponential(5)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details></article>`;
        }).join("")}`;
      } catch (error) {
        file.querySelector(".radial-status").textContent = `Radial plots unavailable (${error.message}). Plots are displayed only after source integrity is confirmed.`;
        load.disabled = false;
      }
    }
    const download = event.target.closest("[data-radial-download]");
    if (download) {
      const card = download.closest(".radial-card"), file = card.closest(".radial-file");
      const blob = new Blob([card.querySelector("svg").outerHTML], { type: "image/svg+xml" });
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url; link.download = `radial-${file.dataset.radialSha.slice(0, 12)}-l${card.dataset.radialL}.svg`; link.click(); URL.revokeObjectURL(url);
    }
  });
  view.addEventListener("change", event => { const card = event.target.closest(".radial-card"); if (card) draw(card); });
}
