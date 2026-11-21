import { esc, fileUrl, fileMirrorUrl } from "./records.mjs";

// Row vectors throughout; real-space lengths are Å, reciprocal vectors include 2π.
const BOHR = 0.529177210903;
const add = (a, b) => a.map((x, i) => x + b[i]);
const sub = (a, b) => a.map((x, i) => x - b[i]);
const mul = (a, s) => a.map(x => x * s);
const dot = (a, b) => a.reduce((s, x, i) => s + x * b[i], 0);
const cross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
const norm = a => Math.hypot(...a);
const det = a => dot(a[0], cross(a[1], a[2]));
const combine = (f, cell) => cell.reduce((v, a, i) => add(v, mul(a, f[i])), [0, 0, 0]);
const linesOf = text => text.split(/\r?\n/).map(s => s.split(/#|\/\//)[0].trim()).filter(Boolean);
const numeric = s => Number(s.replace(/[dD]/g, "e"));
const xyz = line => {
  const v = (line || "").split(/\s+/).slice(0, 3).map(numeric);
  if (v.length !== 3 || !v.every(Number.isFinite)) throw new Error("Invalid or missing coordinates");
  return v;
};

export function reciprocalCell(cell) {
  if (cell.length !== 3 || !cell.every(a => a.length === 3 && a.every(Number.isFinite))) throw new Error("Three finite lattice vectors are required");
  const volume = det(cell), scale = cell.reduce((s, a) => s * norm(a), 1);
  if (!Number.isFinite(scale) || !scale || Math.abs(volume) < 1e-12 * scale) throw new Error("Singular lattice vectors");
  return [cross(cell[1], cell[2]), cross(cell[2], cell[0]), cross(cell[0], cell[1])].map(v => mul(v, 2*Math.PI/volume));
}

// Setyawan–Curtarolo coordinates in canonical primitive reciprocal bases:
// https://docs.ase-lib.org/_modules/ase/dft/kpoints.html#sc_special_points
const SPECIAL_POINTS = {
  cubic: { X: [0,.5,0], M: [.5,.5,0], R: [.5,.5,.5] },
  fcc: { X: [.5,0,.5], W: [.5,.25,.75], K: [.375,.375,.75], L: [.5,.5,.5], U: [.625,.25,.625] },
  bcc: { H: [.5,-.5,.5], N: [0,0,.5], P: [.25,.25,.25] },
  hexagonal: { M: [.5,0,0], K: [1/3,1/3,0], A: [0,0,.5], L: [.5,0,.5], H: [1/3,1/3,.5] },
  tetragonal: { X: [0,.5,0], M: [.5,.5,0], Z: [0,0,.5], R: [0,.5,.5], A: [.5,.5,.5] },
  orthorhombic: { X: [.5,0,0], Y: [0,.5,0], Z: [0,0,.5], S: [.5,.5,0], T: [0,.5,.5], U: [.5,0,.5], R: [.5,.5,.5] },
};

export function getSpecialPoints(cell) {
  const reciprocal = reciprocalCell(cell);
  const gamma = { label: "Γ", fractional: [0,0,0], position: [0,0,0] };
  const candidates = [];
  const near = (a,b) => Math.abs(a-b) < 1e-6;
  // Recognize metrics under signed axis permutations. Do not assign canonical
  // labels to an unsupported skew or centered setting from its formula alone.
  for (const order of [[0,1,2],[0,2,1],[1,0,2],[1,2,0],[2,0,1],[2,1,0]]) for (let mask = 0; mask < 8; mask++) {
    const signs = order.map((_,i) => mask & (1 << i) ? -1 : 1);
    const basis = order.map((j,i) => mul(cell[j], signs[i]));
    const lengths = basis.map(norm), scale = Math.max(...lengths);
    const equal01 = near(lengths[0]/scale, lengths[1]/scale), equal12 = near(lengths[1]/scale, lengths[2]/scale);
    const cosines = [[0,1],[0,2],[1,2]].map(([i,j]) => dot(basis[i],basis[j])/(lengths[i]*lengths[j]));
    const orthogonal = cosines.every(c => near(c,0));
    candidates.push({ order, signs, matches: {
      cubic: orthogonal && equal01 && equal12,
      fcc: equal01 && equal12 && cosines.every(c => near(c,.5)),
      bcc: equal01 && equal12 && cosines.every(c => near(c,-1/3)),
      hexagonal: equal01 && near(cosines[0],-.5) && near(cosines[1],0) && near(cosines[2],0),
      tetragonal: orthogonal && equal01 && !equal12,
      orthorhombic: orthogonal && lengths[0] <= lengths[1] && lengths[1] <= lengths[2],
    } });
  }
  for (const [type, points] of Object.entries(SPECIAL_POINTS)) {
    const setting = candidates.find(c => c.matches[type]);
    if (!setting) continue;
    return [gamma, ...Object.entries(points).map(([label, f]) => {
      const fractional = [0,0,0];
      setting.order.forEach((j,i) => { fractional[j] = f[i]*setting.signs[i]; });
      return { label, fractional, position: combine(fractional, reciprocal) };
    })];
  }
  return [gamma];
}

export function structureFormat(file) {
  const name = file.path.split("/").at(-1).split("__").at(-1);
  return /^STRU$/i.test(name) ? "stru" : /^geometry\.in$/i.test(name) ? "aims" : /^POSCAR$/i.test(name) ? "poscar" : null;
}

export function parseStructure(text, format) {
  const lines = linesOf(text);
  let cell, sites = [];
  if (format === "stru") {
    const sections = {};
    let key;
    for (const line of lines) {
      if (/^[A-Z][A-Z_]+$/.test(line)) { key = line; sections[key] = []; }
      else if (key) sections[key].push(line);
    }
    const scale = numeric(sections.LATTICE_CONSTANT?.[0]?.split(/\s+/)[0] || "") * BOHR;
    if (!(scale > 0)) throw new Error("Missing positive LATTICE_CONSTANT");
    cell = (sections.LATTICE_VECTORS || []).map(s => mul(xyz(s), scale));
    reciprocalCell(cell);
    const positions = sections.ATOMIC_POSITIONS || [];
    const mode = positions[0]?.toLowerCase();
    if (!["direct", "cartesian", "cartesian_au", "cartesian_angstrom"].includes(mode)) throw new Error("Unsupported STRU coordinate mode");
    for (let i = 1; i < positions.length;) {
      const element = positions[i];
      const count = Number(positions[i + 2]);
      if (!/^[A-Z][a-z]?$/.test(element) || !Number.isInteger(count) || count < 1 || i + 3 + count > positions.length) throw new Error("Incomplete STRU atom block");
      for (const line of positions.slice(i + 3, i + 3 + count)) {
        const v = xyz(line);
        sites.push({ element, position: mode === "direct" ? combine(v, cell) : mul(v, mode === "cartesian" ? scale : mode === "cartesian_au" ? BOHR : 1) });
      }
      i += 3 + count;
    }
  } else if (format === "aims") {
    cell = lines.filter(s => s.startsWith("lattice_vector ") || s.startsWith("lattice_vector\t")).map(s => xyz(s.split(/\s+/).slice(1).join(" ")));
    reciprocalCell(cell);
    for (const line of lines) {
      const [kind, ...fields] = line.split(/\s+/);
      if (["empty", "empty_frac"].includes(kind)) throw new Error("Empty sites are not supported in this preview");
      if (!["atom", "atom_frac"].includes(kind)) continue;
      const v = xyz(fields.join(" ")), element = fields[3];
      if (!/^[A-Z][a-z]?$/.test(element)) throw new Error("Invalid geometry.in species");
      sites.push({ element, position: kind === "atom_frac" ? combine(v, cell) : v });
    }
  } else if (format === "poscar") {
    // VASP 5 style, with one scale (including a negative target volume).
    const scaleFields = lines[1]?.split(/\s+/);
    const scale = numeric(scaleFields?.[0] || "");
    if (scaleFields?.length !== 1 || !scale || !Number.isFinite(scale)) throw new Error("Unsupported POSCAR scale");
    const raw = lines.slice(2, 5).map(xyz);
    reciprocalCell(raw);
    const factor = scale < 0 ? Math.cbrt(-scale / Math.abs(det(raw))) : scale;
    cell = raw.map(a => mul(a, factor));
    const elements = (lines[5] || "").split(/\s+/), counts = (lines[6] || "").split(/\s+/).map(Number);
    if (!elements.every(e => /^[A-Z][a-z]?$/.test(e)) || elements.length !== counts.length || !counts.every(n => Number.isInteger(n) && n > 0)) throw new Error("POSCAR requires explicit species and atom counts");
    let i = /^s/i.test(lines[7]) ? 8 : 7;
    const direct = /^d/i.test(lines[i]), cartesian = /^[ck]/i.test(lines[i]);
    if (!direct && !cartesian) throw new Error("Unsupported POSCAR coordinate mode");
    i++;
    for (let j = 0; j < elements.length; j++) for (let n = 0; n < counts[j]; n++) {
      const v = xyz(lines[i++]);
      sites.push({ element: elements[j], position: direct ? combine(v, cell) : mul(v, factor) });
    }
  } else throw new Error("Preview supports STRU, geometry.in and POSCAR files");
  reciprocalCell(cell);
  if (!sites.length || sites.some(s => !s.position.every(Number.isFinite))) throw new Error("No finite atomic positions");
  return { cell, sites };
}

const unique = points => points.filter((p, i) => !points.slice(0, i).some(q => norm(sub(p, q)) < 1e-8));

// Clip a convex polyhedron by n·x <= h. The cap is sorted in its own plane.
function clip(faces, n, h) {
  const result = [], cap = [];
  for (const face of faces) {
    const polygon = [];
    for (let i = 0; i < face.length; i++) {
      const p = face[i], q = face[(i + 1) % face.length];
      const dp = dot(n, p) - h, dq = dot(n, q) - h;
      if (dp <= 1e-10) polygon.push(p);
      if ((dp < -1e-10 && dq > 1e-10) || (dp > 1e-10 && dq < -1e-10)) {
        const v = add(p, mul(sub(q, p), dp / (dp - dq)));
        polygon.push(v); cap.push(v);
      } else if (Math.abs(dp) <= 1e-10) cap.push(p);
    }
    const clean = unique(polygon);
    if (clean.length >= 3) result.push(clean);
  }
  const points = unique(cap);
  if (points.length >= 3 && faces.some(f => f.some(p => dot(n, p) - h > 1e-10))) {
    const center = mul(points.reduce(add, [0, 0, 0]), 1/points.length);
    const axis = Math.abs(n[0]) < 0.8 ? [1, 0, 0] : [0, 1, 0];
    const u = cross(n, axis), v = cross(n, u);
    points.sort((a, b) => Math.atan2(dot(sub(a, center), v), dot(sub(a, center), u)) - Math.atan2(dot(sub(b, center), v), dot(sub(b, center), u)));
    result.push(points);
  }
  return result;
}

export function brillouinZone(cell) {
  let basis = reciprocalCell(cell);
  // Integer row operations preserve the lattice and keep skew input bases cheap.
  for (let step = 0; step < 60; step++) {
    basis.sort((a, b) => dot(a, a) - dot(b, b));
    let changed = false;
    for (let i = 1; i < 3; i++) for (let j = i - 1; j >= 0; j--) {
      const m = Math.round(dot(basis[i], basis[j]) / dot(basis[j], basis[j]));
      const next = sub(basis[i], mul(basis[j], m));
      if (norm(next) < norm(basis[i]) * (1 - 1e-12)) { basis[i] = next; changed = true; }
    }
    if (!changed) break;
  }
  const scale = Math.max(...basis.map(norm));
  basis = basis.map(v => mul(v, 1/scale));
  const dual = reciprocalCell(basis).map(v => mul(v, 1/(2*Math.PI)));
  // Intersections of the ±basis bisectors bound the zone before any other cut.
  const corners = Array.from({ length: 8 }, (_, mask) => combine(basis.map((b, i) => ((mask >> i) & 1 ? 1 : -1) * dot(b, b)/2), dual));
  const bound = Math.max(...corners.map(norm)) * 1.01;
  const cube = Array.from({ length: 8 }, (_, mask) => [0, 1, 2].map(i => ((mask >> i) & 1 ? 1 : -1) * bound));
  let faces = [[0,1,3,2], [4,6,7,5], [0,4,5,1], [2,3,7,6], [0,2,6,4], [1,5,7,3]].map(f => f.map(i => cube[i]));
  for (const b of basis) for (const sign of [-1, 1]) {
    const n = mul(b, sign/norm(b));
    faces = clip(faces, n, norm(b)/2);
  }
  const radius = Math.max(...faces.flat().map(norm));
  // Any omitted G with |G| > 2R cannot cut a polyhedron inside radius R.
  // Since n_i = G·dual_i, these bounds enumerate every possible cutting plane.
  const limits = dual.map(v => Math.ceil(2 * radius * norm(v) + 1e-9));
  if (limits.reduce((n, m) => n * (2*m + 1), 1) > 100000) throw new Error("Cell is too skewed for an interactive Brillouin-zone preview");
  const neighbors = [];
  for (let i = -limits[0]; i <= limits[0]; i++) for (let j = -limits[1]; j <= limits[1]; j++) for (let k = -limits[2]; k <= limits[2]; k++) {
    if (!i && !j && !k) continue;
    const g = combine([i, j, k], basis), length = norm(g);
    if (length <= 2*radius + 1e-9) neighbors.push({ g, length });
  }
  neighbors.sort((a, b) => a.length - b.length);
  for (const { g, length } of neighbors) faces = clip(faces, mul(g, 1/length), length/2);
  return { faces: faces.map(f => f.map(v => mul(v, scale))), vertices: unique(faces.flat()).map(v => mul(v, scale)), reciprocal: reciprocalCell(cell), specialPoints: getSpecialPoints(cell) };
}

const PALETTE = ["#468bd7", "#f4ad49", "#a88bd5", "#53b5b0", "#dc78a5", "#8bab4b"];
const ELEMENT_COLORS = { O: "#e66b67", Mg: "#6fb78d", C: "#6b829b", H: "#c4d0df", N: "#608cf0", Si: "#c29972", S: "#dbb94c" };
const vectorColors = ["#d97967", "#58aa83", "#6a9fe0"];
const defaultCamera = () => ({ yaw: -0.55, pitch: 0.38, zoom: 1.2 });

export function structureScene(structure) {
  const { cell, sites } = structure, reciprocal = reciprocalCell(cell);
  const center = combine([.5,.5,.5], cell);
  const colors = Object.fromEntries([...new Set(sites.map(s => s.element))].map((e, i) => [e, ELEMENT_COLORS[e] || PALETTE[i % PALETTE.length]]));
  const atoms = [];
  for (const site of sites) {
    const f = reciprocal.map(b => dot(site.position, b)/(2*Math.PI)).map(x => {
      const wrapped = x - Math.floor(x);
      return wrapped < 1e-8 || wrapped > 1 - 1e-8 ? 0 : wrapped;
    });
    const images = f.map(x => x === 0 ? [0,1] : [x]);
    for (const x of images[0]) for (const y of images[1]) for (const z of images[2]) atoms.push({ position: sub(combine([x, y, z], cell), center), element: site.element, color: colors[site.element] });
  }
  const vertices = Array.from({ length: 8 }, (_, m) => sub(combine([0, 1, 2].map(i => (m >> i) & 1), cell), center));
  const edges = [];
  for (let m = 0; m < 8; m++) for (let i = 0; i < 3; i++) if (!(m & (1 << i))) edges.push([vertices[m], vertices[m | (1 << i)]]);
  return { vertices, edges, atoms, colors, axes: cell.map((a, i) => ({ vector: a, label: `a${"₁₂₃"[i]}`, color: vectorColors[i] })) };
}

function zoneScene(zone) {
  return { vertices: zone.vertices, faces: zone.faces, points: zone.specialPoints, atoms: [], axes: zone.reciprocal.map((b, i) => ({ vector: b, label: `b${"₁₂₃"[i]}`, color: vectorColors[i] })) };
}

export function sceneSvg(scene, camera = defaultCamera(), label = "Crystal structure") {
  const rotate = v => {
    const x = v[0]*Math.cos(camera.yaw) + v[2]*Math.sin(camera.yaw), z = -v[0]*Math.sin(camera.yaw) + v[2]*Math.cos(camera.yaw);
    return [x, v[1]*Math.cos(camera.pitch) - z*Math.sin(camera.pitch), v[1]*Math.sin(camera.pitch) + z*Math.cos(camera.pitch)];
  };
  const radius = Math.max(...scene.vertices.map(norm)), factor = 118/radius * camera.zoom;
  const project = v => { const r = rotate(v); return [210+r[0]*factor, 160-r[1]*factor, r[2]]; };
  const path = points => points.map((p, i) => `${i ? "L" : "M"}${project(p).slice(0,2).map(x => x.toFixed(2)).join(",")}`).join(" ");
  const faces = (scene.faces || []).map(f => ({ face: f, depth: f.reduce((s, p) => s+rotate(p)[2], 0)/f.length })).sort((a,b) => a.depth-b.depth).map(({face}) => `<path d="${path(face)}Z" fill="var(--accent)" fill-opacity=".09" stroke="var(--accent)" stroke-width="1.4" stroke-linejoin="round"/>`).join("");
  const edges = (scene.edges || []).map(e => `<path d="${path(e)}" fill="none" stroke="var(--subtle)" stroke-width="1.3"/>`).join("");
  // A fixed-size orientation inset shares the scene rotation, independently of zoom.
  const axes = scene.axes.map(a => {
    const direction = rotate(mul(a.vector, 1/norm(a.vector)));
    const x = direction[0]*30, y = -direction[1]*30, length = Math.hypot(x,y);
    const arrow = length > 1 ? ` M${x-5*x/length+3*y/length},${y-5*y/length-3*x/length}L${x},${y}L${x-5*x/length-3*y/length},${y-5*y/length+3*x/length}` : "";
    return `<path d="M0,0L${x},${y}${arrow}" fill="none" stroke="${a.color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><text x="${x+(x < -5 ? -6 : x > 5 ? 6 : 0)}" y="${y+(y < 0 ? -7 : 9)}" text-anchor="${x < -5 ? "end" : x > 5 ? "start" : "middle"}" dominant-baseline="middle" fill="${a.color}" font-weight="600">${a.label}</text>`;
  }).join("");
  const orientation = `<g class="structure-orientation" transform="translate(62 266)">${axes}<circle r="2" fill="var(--subtle)"/></g>`;
  const atoms = scene.atoms.map(a => ({...a, p: project(a.position)})).sort((a,b) => a.p[2]-b.p[2]).map(a => {
    const r = Math.min(13, Math.max(3, 0.25*factor));
    return `<g><title>${esc(a.element)}</title><circle cx="${a.p[0]}" cy="${a.p[1]}" r="${r}" fill="${a.color}" stroke="var(--panel)" stroke-width="1"/><circle cx="${a.p[0]-r*.26}" cy="${a.p[1]-r*.3}" r="${r*.28}" fill="white" fill-opacity=".4"/></g>`;
  }).join("");
  const projected = (scene.points || []).map(p => ({ ...p, screen: project(p.position) }));
  const labels = [];
  const points = projected.map(p => {
    const [x,y] = p.screen, width = 10*p.label.length;
    const offsets = [[10,-12],[10,16],[-12,-12],[-12,16],[24,0],[-24,0],[0,-26],[0,28],[28,-20],[-28,24]];
    const overlaps = (a,b) => a.x < b.x+b.w && a.x+a.w > b.x && a.y < b.y+b.h && a.y+a.h > b.y;
    const boxes = offsets.map(([dx,dy]) => ({ x: x+dx-width/2-3, y: y+dy-12, w: width+6, h: 18, dx, dy }));
    const box = boxes.find(b => b.x >= 3 && b.y >= 3 && b.x+b.w <= 417 && b.y+b.h <= 317 && !overlaps(b,{x:10,y:220,w:104,h:90}) && !labels.some(l => overlaps(b,l)) && !projected.some(q => overlaps(b,{x:q.screen[0]-4,y:q.screen[1]-4,w:8,h:8}))) || boxes[0];
    labels.push(box);
    return `<g data-special-point="${esc(p.label)}"><circle cx="${x}" cy="${y}" r="3.2" fill="var(--heading)"/><text x="${x+box.dx}" y="${y+box.dy}" text-anchor="middle" fill="var(--heading)" font-weight="600" paint-order="stroke" stroke="var(--raised)" stroke-width="3" stroke-linejoin="round">${esc(p.label)}</text></g>`;
  }).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 320" role="img" aria-label="${esc(label)}"><g font-family="system-ui,sans-serif" font-size="14">${faces}${edges}${atoms}${points}${orientation}</g></svg>`;
}

// Cell and sites rounded to 1e-4 Å, sites sorted, so two files that describe
// the same crystal compare equal even when their text differs (a stripped
// ABFS_ORBITAL block, a rewritten asset path, a different vacuum layer in a
// slab). Lattice orientation is not normalised: a permuted cell counts as a
// different preview, because deciding that two settings are equivalent is a
// scientific judgement this code must not make silently.
export function structureFingerprint(structure) {
  const q = value => Math.round(value * 1e4);
  const cell = structure.cell.map(row => row.map(q).join(",")).join(";");
  const sites = structure.sites.map(site => `${site.element}@${site.position.map(q).join(",")}`).sort().join(";");
  return `${cell}|${sites}`;
}

export function structurePreview(file, { sameAs = null } = {}) {
  if (!structureFormat(file)) return "";
  // A file that repeats a structure already previewed above keeps its download
  // row but gets a pointer instead of a second identical pair of drawings.
  if (sameAs) return `<p class="structure-duplicate"><span aria-hidden="true">↳</span> Same structure as <code>${esc(sameAs.name)}</code>${sameAs.reason === "sha256" ? " (byte-identical file)" : ""}; its preview is shown there.</p>`;
  return `<div class="structure-preview" data-structure-path="${esc(file.path)}"><p class="structure-status" role="status" hidden></p><button type="button" class="text-button" data-structure-retry hidden>Retry preview</button><div class="structure-plots"></div></div>`;
}

// A reader has to be able to tell which file the pointer refers to. Labels are
// often just "STRU" for several stages, so a label that repeats among the
// structure files is qualified by the stage carried in the path.
export function structureLabels(files) {
  const plain = file => file.display_name || file.label || file.path.split("/").at(-1).split("__").at(-1);
  const counts = new Map();
  for (const file of files) { const name = plain(file); counts.set(name, (counts.get(name) || 0) + 1); }
  const labels = new Map();
  for (const file of files) {
    const name = plain(file);
    if ((counts.get(name) || 0) < 2) { labels.set(file.path, name); continue; }
    // Spell the path the way the download row already reads: stage folders and
    // the "stage__FILE" convention both become " / " segments.
    const parts = file.path.split("/");
    const stem = parts.at(-1).split("__");
    const qualified = stem.length > 1 ? stem.join(" / ") : [parts.at(-2), stem[0]].filter(Boolean).join(" / ");
    labels.set(file.path, qualified || name);
  }
  return labels;
}

// Static first pass: identical bytes are the same structure without downloading
// anything. The caller passes the structure files in display order and gets
// back, per file, either a preview marker or the earlier file it repeats.
export function groupStructureFiles(files) {
  const labels = structureLabels(files), seen = new Map(), groups = [];
  for (const file of files) {
    if (!structureFormat(file)) { groups.push({ file, preview: false, sameAs: null }); continue; }
    const key = /^[a-f0-9]{64}$/.test(file.sha256 || "") ? file.sha256 : `path:${file.path}`;
    const first = seen.get(key);
    if (first) { groups.push({ file, preview: false, sameAs: { name: first.name, reason: "sha256" } }); continue; }
    seen.set(key, { file, name: labels.get(file.path) });
    groups.push({ file, preview: true, sameAs: null });
  }
  return groups;
}

export async function loadStructureFile(file, fetcher = fetch) {
  if (!/^[a-f0-9]{64}$/.test(file.sha256 || "")) throw new Error("Missing structure SHA-256");
  const urls = [...new Set([fileUrl(file), fileMirrorUrl(file)].filter(Boolean))];
  let lastError;
  for (const url of urls) {
    try {
      const response = await fetcher(url, { signal: AbortSignal.timeout(15000), referrerPolicy: "no-referrer" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const bytes = await response.arrayBuffer();
      const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(v => v.toString(16).padStart(2, "0")).join("");
      if (digest !== file.sha256) throw new Error("Structure SHA-256 mismatch");
      return parseStructure(new TextDecoder("utf-8", { fatal: true }).decode(bytes), structureFormat(file));
    } catch (error) { lastError = error; }
  }
  throw lastError || new Error("Structure URL unavailable");
}

export function installStructurePreview(view, getRecord) {
  const states = new WeakMap();
  // fingerprint -> { root, name } of the first preview that drew that crystal,
  // so a later file describing the identical structure does not draw it again.
  const drawn = new Map();
  const draw = (root, kind) => {
    const state = states.get(root), panel = root.querySelector(`[data-structure-panel="${kind}"]`);
    if (!state?.scenes[kind] || !panel) return;
    panel.querySelector(".structure-canvas").innerHTML = sceneSvg(state.scenes[kind], state.cameras[kind], kind === "cell" ? "Crystal structure" : "First Brillouin zone");
  };
  const panel = (kind, title) => `<article class="structure-plot" data-structure-panel="${kind}"><div class="structure-plot-heading"><h3>${title}</h3><div class="structure-view-actions"><button type="button" data-structure-camera="out" aria-label="Zoom out ${title}">−</button><button type="button" data-structure-camera="in" aria-label="Zoom in ${title}">+</button><button type="button" data-structure-camera="reset" aria-label="Reset ${title} view">Reset</button></div></div><div class="structure-canvas" tabindex="0" role="group" aria-label="${title}. Drag or use arrow keys to rotate; plus and minus to zoom; Home to reset."></div></article>`;
  // Same disambiguation as the static pass, so a pointer never says
  // "Same structure as STRU" when three files are called STRU.
  const nameMap = () => structureLabels(getRecord()?.files?.inputs || []);
  const displayName = file => nameMap().get(file.path) || file.path.split("/").at(-1);
  // Replace this preview with a pointer to the one that already rendered the
  // same crystal. The download row above it stays, so the file is still reachable.
  const collapse = (root, file, target) => {
    states.delete(root);
    root.dataset.structureDuplicateOf = target.root.dataset.structurePath || "";
    root.className = "structure-duplicate";
    root.innerHTML = `<span aria-hidden="true">↳</span> Same structure as <code>${esc(target.name)}</code>; its preview is shown there.<span class="structure-duplicate-file">${esc(displayName(file))} differs only in file contents.</span>`;
  };
  const load = async root => {
    const files = getRecord()?.files?.inputs || [], path = root.dataset.structurePath;
    const file = files.find(f => f.path === path);
    const token = {};
    states.set(root, { token });
    const status = root.querySelector(".structure-status"), plots = root.querySelector(".structure-plots");
    root.querySelector("[data-structure-retry]").hidden = true;
    status.hidden = false; status.textContent = "Loading structure…"; plots.innerHTML = "";
    try {
      if (!file) throw new Error("Structure file unavailable");
      const structure = await loadStructureFile(file);
      if (!root.isConnected || states.get(root)?.token !== token) return;
      // Byte-different files can still describe the same crystal. Look for an
      // earlier preview that already drew it before spending a second drawing.
      const fingerprint = structureFingerprint(structure);
      const earlier = drawn.get(fingerprint);
      if (earlier && earlier.root !== root) {
        // A preview from a previous record leaves the page behind; drop the
        // stale entry instead of pointing the reader at nothing.
        if (earlier.root.isConnected) { collapse(root, file, earlier); return; }
        drawn.delete(fingerprint);
      }
      drawn.set(fingerprint, { root, name: displayName(file) });
      root.dataset.structureFingerprint = fingerprint;
      const state = { token, scenes: { cell: structureScene(structure) }, cameras: { cell: defaultCamera(), bz: defaultCamera() } };
      states.set(root, state);
      let zoneError;
      try { state.scenes.bz = zoneScene(brillouinZone(structure.cell)); } catch (e) { zoneError = e; }
      plots.innerHTML = `<div class="structure-grid">${panel("cell", "Crystal structure")}${panel("bz", "First Brillouin zone")}</div><div class="structure-legend">${Object.entries(state.scenes.cell.colors).map(([element, color]) => `<span><i style="background:${color}"></i>${esc(element)}</span>`).join("")}</div><p class="structure-metrics">${structure.sites.length} atoms per input cell · a, b, c = ${structure.cell.map(a => norm(a).toFixed(4)).join(", ")} Å · volume ${Math.abs(det(structure.cell)).toFixed(4)} Å³</p>`;
      status.textContent = ""; status.hidden = true;
      draw(root, "cell");
      if (zoneError) plots.querySelector('[data-structure-panel="bz"] .structure-canvas').textContent = `Brillouin-zone preview unavailable: ${zoneError.message}`;
      else draw(root, "bz");
    } catch (error) {
      if (root.isConnected && states.get(root)?.token === token) {
        status.textContent = `Preview unavailable: ${error.message}.`;
        root.querySelector("[data-structure-retry]").hidden = false;
        states.delete(root);
      }
    }
  };
  view.addEventListener("toggle", event => {
    if (event.target.id !== "record-structure" || !event.target.open) return;
    // Load in display order: the first structure in the section keeps the
    // preview, and later files describing the same crystal point back at it.
    // Loading concurrently would let whichever download finishes first win, so
    // the retained preview could change between page loads.
    (async () => {
      for (const root of event.target.querySelectorAll(".structure-preview")) {
        if (!states.has(root)) await load(root);
      }
    })();
  }, true);
  const moveCamera = (root, kind, action) => {
    const state = states.get(root);
    if (!state?.cameras) return;
    if (action === "reset") state.cameras[kind] = defaultCamera();
    else state.cameras[kind].zoom = Math.max(.5, Math.min(3, state.cameras[kind].zoom * (action === "in" ? 1.15 : 1/1.15)));
    draw(root, kind);
  };
  view.addEventListener("click", event => {
    const root = event.target.closest(".structure-preview");
    if (!root) return;
    if (event.target.closest("[data-structure-retry]")) load(root);
    const button = event.target.closest("[data-structure-camera]");
    if (button) moveCamera(root, button.closest("[data-structure-panel]").dataset.structurePanel, button.dataset.structureCamera);
  });
  view.addEventListener("keydown", event => {
    const canvas = event.target.closest(".structure-canvas");
    if (!canvas || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "+", "=", "-", "Home"].includes(event.key)) return;
    const root = canvas.closest(".structure-preview"), kind = canvas.closest("[data-structure-panel]").dataset.structurePanel, state = states.get(root);
    if (!state?.cameras) return;
    event.preventDefault();
    if (["+", "=", "-", "Home"].includes(event.key)) moveCamera(root, kind, event.key === "Home" ? "reset" : event.key === "-" ? "out" : "in");
    else { state.cameras[kind][["ArrowLeft", "ArrowRight"].includes(event.key) ? "yaw" : "pitch"] += ["ArrowLeft", "ArrowUp"].includes(event.key) ? -.12 : .12; draw(root, kind); }
  });
  let drag;
  view.addEventListener("pointerdown", event => {
    const canvas = event.target.closest(".structure-canvas");
    if (!canvas || event.button !== 0 || !states.get(canvas.closest(".structure-preview"))?.cameras) return;
    drag = { canvas, x: event.clientX, y: event.clientY, id: event.pointerId };
    canvas.setPointerCapture(event.pointerId);
  });
  view.addEventListener("pointermove", event => {
    if (!drag || drag.id !== event.pointerId) return;
    const root = drag.canvas.closest(".structure-preview"), kind = drag.canvas.closest("[data-structure-panel]").dataset.structurePanel, state = states.get(root);
    if (!state?.cameras) return;
    state.cameras[kind].yaw += (event.clientX-drag.x)*.01;
    state.cameras[kind].pitch += (event.clientY-drag.y)*.01;
    drag.x = event.clientX; drag.y = event.clientY; draw(root, kind);
  });
  for (const event of ["pointerup", "pointercancel", "lostpointercapture"]) view.addEventListener(event, () => { drag = null; });
}
