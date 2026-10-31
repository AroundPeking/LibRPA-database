// Headless harness for the cover water scene.
// Stubs just enough DOM/canvas for cover.mjs to run, pumps rAF frames with
// fixed timestamps, and asserts the wave behaviour: ripple trains stay finite
// and on the canvas, crests stay on screen, the emblem emits drops on a
// schedule, a background click drops a stone at the tapped point, and a click on
// a link does not. The scene is drawn through a recording 2d context, so a
// drawing call that throws (a renamed variable, a missing gradient) fails here
// instead of silently freezing the animation in a browser.
import test from "node:test";
import assert from "node:assert/strict";

// Deterministic Math.random so drop seeds/reach are reproducible.
let seed = 42;
const rand = () => (seed = (seed * 1664525 + 1013904223) >>> 0, seed / 2 ** 32);
globalThis.Math.random = rand;

const makeGradient = () => ({ stops: [], addColorStop(offset, color) { this.stops.push([offset, color]); } });
const makeCtx = () => ({
  calls: [],
  path: [],
  setTransform() {}, clearRect() {}, translate() {}, rotate() {}, scale() {},
  save() {}, restore() {}, closePath() {}, fill() {},
  stroke() { this.calls.push({ type: "stroke", style: this.strokeStyle, w: this.lineWidth, shadow: this.shadowBlur }); },
  beginPath() { this.path = []; },
  arc(x, y, r) { this.path.push([x, y, r]); },
  ellipse(x, y, rx, ry, rot, a0, a1) {
    this.path.push([x, y, rx, ry]);
    this.calls.push({ type: "ellipse", x, y, rx, ry, a0, a1, w: this.lineWidth, style: this.strokeStyle });
  },
  moveTo(x, y) { this.path.push([x, y]); this.calls.push({ type: "moveTo", x, y }); },
  lineTo(x, y) { this.path.push([x, y]); this.calls.push({ type: "lineTo", x, y }); },
  fillRect() {}, putImageData() {}, drawImage() {},
  createImageData: (w, h) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }),
  createLinearGradient: () => { const g = makeGradient(); gradients.push(g); return g; },
  createRadialGradient: () => { const g = makeGradient(); gradients.push(g); return g; },
  createPattern: () => ({ setTransform() {} }),
  setLineDash() {}, getImageData: (x, y, w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }),
  strokeStyle: "", fillStyle: "", lineWidth: 1, lineDashOffset: 0, lineCap: "butt",
  shadowColor: "", shadowBlur: 0, globalAlpha: 1, globalCompositeOperation: "source-over"
});
const gradients = [];

const spriteCanvas = { width: 0, height: 0, getContext: () => makeCtx() };
const ctx = makeCtx();
const canvas = { width: 0, height: 0, style: {}, getContext: () => ctx };
const wrap = { getBoundingClientRect: () => ({ left: 440, top: 330, width: 400, height: 400 }) };
const landing = { isConnected: true, hidden: false };
const handlers = {};
const cover = {
  querySelector: sel => (sel === ".cover-canvas" ? canvas : sel === ".cover-stage-wrap" ? wrap : null),
  closest: () => landing,
  addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn); },
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 1280, height: 1000 })
};

globalThis.document = {
  hidden: false,
  documentElement: { dataset: { theme: "dark" } },
  createElement: () => spriteCanvas,
  addEventListener() {}
};
globalThis.window = { devicePixelRatio: 1, addEventListener() {} };
globalThis.matchMedia = () => ({ matches: false });
let rafCb = null;
globalThis.requestAnimationFrame = cb => { rafCb = cb; return 1; };

const { startCoverCanvas } = await import("../database/cover.mjs");

// 1280x1000 canvas, stage centred at (640, 530), coreR = 210.
const CX = 640, CY = 530, DT = 1 / 60;

const frames = [];
const step = t => {
  const mark = ctx.calls.length;
  const cb = rafCb;
  rafCb = null;
  assert.equal(typeof cb, "function", "the animation loop keeps requesting frames");
  cb(t);
  frames.push(ctx.calls.slice(mark));
};
startCoverCanvas(cover);

// A wavefront is drawn as one closed path: a moveTo followed by a run of
// lineTo points. Splitting a frame's calls into those runs gives one entry per
// crest, so each crest's centre and radii can be measured separately.
const crestsOf = calls => {
  const loops = [];
  let current = null;
  for (const c of calls) {
    if (c.type === "moveTo") { current = [[c.x, c.y]]; loops.push(current); }
    else if (c.type === "lineTo" && current) current.push([c.x, c.y]);
  }
  return loops.filter(pts => pts.length >= 24).map(pts => {
    let minx = Infinity, maxx = -Infinity, miny = Infinity, maxy = -Infinity, sx = 0, sy = 0;
    for (const [x, y] of pts) {
      if (x < minx) minx = x;
      if (x > maxx) maxx = x;
      if (y < miny) miny = y;
      if (y > maxy) maxy = y;
      sx += x; sy += y;
    }
    return { cx: sx / pts.length, cy: sy / pts.length, rx: (maxx - minx) / 2, ry: (maxy - miny) / 2 };
  });
};

// A tap well outside the emblem's exclusion zone (coreR = 210 around y=530).
const TAPX = 220, TAPY = 250;
const nearTap = calls => crestsOf(calls).some(c => Math.hypot(c.cx - TAPX, c.cy - TAPY) < 80);

// A click landing on a link (emblem / enter button) must not drop a stone.
handlers.click.forEach(fn => fn({ clientX: TAPX, clientY: TAPY, target: { closest: () => ({}) } }));
let tapFired = false;
let framesRun = 0;
const crests = [];
for (let t = 16.7; t <= 9000; t += 16.7) {
  const mark = ctx.calls.length;
  step(t);
  framesRun += 1;
  const frame = ctx.calls.slice(mark);
  if (nearTap(frame)) tapFired = true;
  crests.push(...crestsOf(frame));
}
assert.ok(!tapFired, "link clicks do not drop a stone");
assert.ok(framesRun > 500, "the animation survives the full 9s window");

// A background click drops a stone at the tapped point.
handlers.click.forEach(fn => fn({ clientX: TAPX, clientY: TAPY, target: { closest: () => null } }));
let manualDrop = false;
for (let t = 9016.7; t <= 9800; t += 16.7) {
  const mark = ctx.calls.length;
  step(t);
  if (nearTap(ctx.calls.slice(mark))) manualDrop = true;
}
assert.ok(manualDrop, "a background click stamps a ripple at the tapped point");

// Crest geometry: finite, positive, on canvas, and squashed to the water plane
// (wider than tall) rather than drawn as a screen-space circle.
assert.ok(crests.length > 100, `crests are drawn, saw ${crests.length}`);
for (const c of crests) {
  assert.ok(Number.isFinite(c.rx) && Number.isFinite(c.ry), "crest radii stay finite");
  assert.ok(c.rx > 0 && c.ry > 0 && c.ry < c.rx, `crest is squashed, not a circle (rx=${c.rx.toFixed(0)}, ry=${c.ry.toFixed(0)})`);
  assert.ok(c.rx < 1300 && c.ry < 700, `crest stays on the canvas (rx=${c.rx.toFixed(0)}, ry=${c.ry.toFixed(0)})`);
  assert.ok(c.cx > -80 && c.cx < 1360 && c.cy > -80 && c.cy < 1080, "crest centres stay on the canvas");
}

// A crest must travel: the largest crest seen covers a good part of the canvas.
const widest = Math.max(...crests.map(c => c.rx));
assert.ok(widest > 500, `a crest crosses most of the canvas (widest=${widest.toFixed(0)})`);

// Crests thin out as they travel: the highlight is a vertical gradient whose
// top stop is the bright lip and whose bottom stop fades to nothing. A crest
// gradient must exist and must fade, otherwise the wave reads as a drawn oval.
const crestStops = gradients
  .map(g => g.stops)
  .filter(stops => stops.length >= 3 && stops.some(s => String(s[1]).includes("rgba")))
  .map(stops => stops.map(s => Number(/([\d.]+)\)$/.exec(String(s[1]))?.[1])).filter(Number.isFinite));
assert.ok(crestStops.length > 20, `crests carry a shaded highlight, saw ${crestStops.length}`);
const allTop = crestStops.map(s => s[0]).filter(Number.isFinite);
const allBottom = crestStops.map(s => s[s.length - 1]).filter(Number.isFinite);
assert.ok(Math.max(...allTop) > 0, "crest gradients start bright");
assert.ok(Math.min(...allBottom) <= 0.02, "crest gradients fade out at the far edge");

test("cover water scene: crest trains, confinement, click drops, link clicks ignored", () => {
  assert.ok(frames.length > 550, "animation ran for the full window");
});
