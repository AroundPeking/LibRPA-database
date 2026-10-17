// Headless physics harness for the cover canvas scene.
// Stubs just enough DOM/canvas for cover.mjs to run, pumps rAF frames with
// fixed timestamps, and asserts the polarization-bubble dynamics: bubbles
// stay finite and confined, never interpenetrate (mutual repulsion), get
// visibly shoved outward when a screening-ring wavefront sweeps past them,
// and a background click on the cover fires a fresh manual ring.
import test from "node:test";
import assert from "node:assert/strict";

// Deterministic Math.random so spawn radii/velocities are reproducible.
let seed = 42;
const rand = () => (seed = (seed * 1664525 + 1013904223) >>> 0, seed / 2 ** 32);
globalThis.Math.random = rand;

const makeCtx = () => ({
  arcs: [],
  path: [],
  setTransform() {}, clearRect() {}, translate() {},
  beginPath() { this.path = []; },
  arc(x, y, r) { this.path.push([x, y, r]); },
  fill() { this.arcs.push(...this.path.map(a => [...a, "fill"])); },
  stroke() { this.arcs.push(...this.path.map(a => [...a, "stroke"])); },
  fillRect() {}, drawImage() {},
  setLineDash() {}, createRadialGradient: () => ({ addColorStop() {} }),
  strokeStyle: "", fillStyle: "", lineWidth: 1, lineDashOffset: 0,
  globalAlpha: 1, globalCompositeOperation: "source-over"
});

const spriteCanvas = { width: 0, height: 0, getContext: () => makeCtx() };
const ctx = makeCtx();
const canvas = { width: 0, height: 0, style: {}, getContext: () => ctx };
const wrap = { getBoundingClientRect: () => ({ left: 484, top: 330, width: 400, height: 400 }) };
const landing = { isConnected: true, hidden: false };
const handlers = {};
const cover = {
  querySelector: sel => (sel === ".cover-canvas" ? canvas : sel === ".cover-stage-wrap" ? wrap : null),
  closest: () => landing,
  addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn); },
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 1368, height: 1050 })
};

globalThis.document = {
  hidden: false,
  documentElement: { dataset: {} },
  createElement: () => spriteCanvas,
  addEventListener() {}
};
globalThis.window = { devicePixelRatio: 1, addEventListener() {} };
globalThis.matchMedia = () => ({ matches: false });
let rafCb = null;
globalThis.requestAnimationFrame = cb => { rafCb = cb; return 1; };

const { startCoverCanvas } = await import("../database/cover.mjs");

// 1368x1050 viewport, stage centered at (684, 530), coreR = 210, 7 bubbles.
const N = 7, CX = 684, CY = 530, DT = 1 / 60;
const frames = [];
const step = t => {
  const mark = ctx.arcs.length;
  const cb = rafCb;
  rafCb = null;
  cb(t);
  frames.push(ctx.arcs.slice(mark));
};
startCoverCanvas(cover);
for (let t = 16.7; t <= 6900; t += 16.7) step(t);

// Tap point inside the emblem's core exclusion zone: bubbles never center
// within ~288px of the cover center, so arcs centered at the tap point can
// only be the tap ripple, never a bubble.
const TAPX = 600, TAPY = 500;
const atTap = ([x, y]) => Math.hypot(x - TAPX, y - TAPY) < 3;

// A click landing on a link (emblem / enter button) must not emit a ripple.
handlers.click.forEach(fn => fn({ clientX: TAPX, clientY: TAPY, target: { closest: () => ({}) } }));
step(6916.7);
assert.ok(!frames[frames.length - 1].some(arc => arc[3] === "stroke" && atTap(arc)), "link clicks do not fire ripples");

// A background click fires a manual ripple centered on the tapped point
// (expanding at 110px/s from r0=14, so r stays well under 150 in the window).
handlers.click.forEach(fn => fn({ clientX: TAPX, clientY: TAPY, target: { closest: () => null } }));
let manualRing = false;
for (let t = 6933.4; t <= 10000; t += 16.7) {
  step(t);
  if (t <= 7600 && frames[frames.length - 1].some(arc => arc[3] === "stroke" && atTap(arc) && arc[2] > 8 && arc[2] < 160)) manualRing = true;
}
assert.ok(manualRing, "background click fires a ripple at the tapped point");

// Each frame draws N bubble rings (r 52-94) plus screening-ring circles
// (r >= 210), so r < 150 isolates the bubbles.
const bubbleFrames = frames.map(arcs => arcs.filter(([, , r, op], i) => r < 150 && op === "stroke" && !atTap(arcs[i])));
for (const arcs of bubbleFrames) assert.equal(arcs.length, N, "all bubbles drawn every frame");

const first = bubbleFrames[10].map(([x, y]) => [x, y]);
const last = bubbleFrames[bubbleFrames.length - 1];
let moved = 0;
for (let i = 0; i < N; i++) {
  const d = Math.hypot(last[i][0] - first[i][0], last[i][1] - first[i][1]);
  if (d > 25) moved += 1;
  for (const [x, y] of bubbleFrames.map(a => a[i])) {
    assert.ok(Number.isFinite(x) && Number.isFinite(y), "bubble coordinates stay finite");
    assert.ok(Math.hypot(x - CX, y - CY) > 150, "bubbles never collapse onto the emblem core");
    assert.ok(x > -50 && x < 1420 && y > -50 && y < 1100, "bubbles stay on the canvas");
  }
}
assert.ok(moved >= 4, `bubbles are in motion, moved=${moved}/${N}`);

// Mutual repulsion: physics enforces base-radius separation, drawn radii
// breathe up to +8% and one integration step can re-penetrate a few px, so
// the bound normalizes the breath — real interpenetration fails outright.
for (const arcs of bubbleFrames) {
  for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
    const d = Math.hypot(arcs[i][0] - arcs[j][0], arcs[i][1] - arcs[j][1]);
    const need = (arcs[i][2] + arcs[j][2]) * .92 - 4;
    assert.ok(d >= need, `bubbles repel on contact (d=${d.toFixed(1)}, need=${need.toFixed(1)})`);
  }
}

// Wavefront kick: when a screening ring sweeps past, the bubble's radial
// speed spikes well above the ambient drift.
let kicked = 0;
for (let i = 0; i < N; i++) {
  let maxRadial = 0;
  for (let f = 1; f < bubbleFrames.length; f++) {
    const [x0, y0] = bubbleFrames[f - 1][i];
    const [x1, y1] = bubbleFrames[f][i];
    const r0 = Math.hypot(x0 - CX, y0 - CY), r1 = Math.hypot(x1 - CX, y1 - CY);
    maxRadial = Math.max(maxRadial, Math.abs(r1 - r0) / DT);
  }
  if (maxRadial >= 25) kicked += 1;
}
assert.ok(kicked >= 5, `screening rings shove bubbles outward, kicked=${kicked}/${N}`);

test("cover bubble physics: repulsion, confinement, ring kicks, click emission", () => {
  assert.ok(frames.length > 500, "animation ran for the full 10s window");
});
