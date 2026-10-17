// Headless physics harness for the cover canvas scene.
// Stubs just enough DOM/canvas for cover.mjs to run, pumps rAF frames with
// fixed timestamps, and asserts the polarization-bubble dynamics: bubbles
// stay finite and confined, never interpenetrate (mutual repulsion), and get
// visibly shoved outward when a screening-ring wavefront sweeps past them.
import test from "node:test";
import assert from "node:assert/strict";

// Deterministic Math.random so spawn radii/velocities are reproducible.
let seed = 42;
const rand = () => (seed = (seed * 1664525 + 1013904223) >>> 0, seed / 2 ** 32);
globalThis.Math.random = rand;

const makeCtx = () => ({
  arcs: [],
  setTransform() {}, clearRect() {}, translate() {}, beginPath() {},
  arc(x, y, r) { this.arcs.push([x, y, r]); },
  stroke() {}, fillRect() {}, drawImage() {},
  setLineDash() {}, createRadialGradient: () => ({ addColorStop() {} }),
  strokeStyle: "", fillStyle: "", lineWidth: 1, lineDashOffset: 0,
  globalAlpha: 1, globalCompositeOperation: "source-over"
});

const spriteCanvas = { width: 0, height: 0, getContext: () => makeCtx() };
const ctx = makeCtx();
const canvas = { width: 0, height: 0, style: {}, getContext: () => ctx };
const wrap = { getBoundingClientRect: () => ({ left: 484, top: 330, width: 400, height: 400 }) };
const landing = { isConnected: true, hidden: false };
const cover = {
  querySelector: sel => (sel === ".cover-canvas" ? canvas : sel === ".cover-stage-wrap" ? wrap : null),
  closest: () => landing,
  addEventListener() {},
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

// 1368x1050 viewport, stage centered at (684, 530), coreR = 210.
const CX = 684, CY = 530, DT = 1 / 60;
const frames = [];
startCoverCanvas(cover);
for (let t = 16.7; t <= 10000; t += 16.7) {
  const mark = ctx.arcs.length;
  const cb = rafCb;
  rafCb = null;
  cb(t);
  frames.push(ctx.arcs.slice(mark));
}

// Each frame draws 4 bubble rings (r 52-94) plus screening-ring circles
// (r >= 210), so r < 150 isolates the bubbles.
const bubbleFrames = frames.map(arcs => arcs.filter(([, , r]) => r < 150));
for (const arcs of bubbleFrames) assert.equal(arcs.length, 4, "four bubbles drawn every frame");

const first = bubbleFrames[10].map(([x, y]) => [x, y]);
const last = bubbleFrames[bubbleFrames.length - 1];
let moved = 0;
for (let i = 0; i < 4; i++) {
  const d = Math.hypot(last[i][0] - first[i][0], last[i][1] - first[i][1]);
  if (d > 25) moved += 1;
  for (const [x, y] of bubbleFrames.map(a => a[i])) {
    assert.ok(Number.isFinite(x) && Number.isFinite(y), "bubble coordinates stay finite");
    assert.ok(Math.hypot(x - CX, y - CY) > 150, "bubbles never collapse onto the emblem core");
    assert.ok(x > -50 && x < 1420 && y > -50 && y < 1100, "bubbles stay on the canvas");
  }
}
assert.ok(moved >= 3, `bubbles are in motion, moved=${moved}`);

// Mutual repulsion: drawn radii breathe +/-8%, physics uses base radii, so
// allow a small tolerance — but real interpenetration would fail outright.
for (const arcs of bubbleFrames) {
  for (let i = 0; i < 4; i++) for (let j = i + 1; j < 4; j++) {
    const d = Math.hypot(arcs[i][0] - arcs[j][0], arcs[i][1] - arcs[j][1]);
    assert.ok(d >= arcs[i][2] + arcs[j][2] - 14, `bubbles repel on contact (d=${d.toFixed(1)})`);
  }
}

// Wavefront kick: when a screening ring sweeps past, the bubble's radial
// speed spikes well above the ambient drift.
let kicked = 0;
for (let i = 0; i < 4; i++) {
  let maxRadial = 0;
  for (let f = 1; f < bubbleFrames.length; f++) {
    const [x0, y0] = bubbleFrames[f - 1][i];
    const [x1, y1] = bubbleFrames[f][i];
    const r0 = Math.hypot(x0 - CX, y0 - CY), r1 = Math.hypot(x1 - CX, y1 - CY);
    maxRadial = Math.max(maxRadial, Math.abs(r1 - r0) / DT);
  }
  if (maxRadial >= 25) kicked += 1;
}
assert.ok(kicked >= 2, `screening rings shove bubbles outward, kicked=${kicked}`);

test("cover bubble physics: repulsion, confinement, and ring kicks", () => {
  assert.ok(frames.length > 500, "animation ran for the full 10s window");
});
