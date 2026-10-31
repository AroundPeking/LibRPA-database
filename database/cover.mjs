// Cover choreography for the landing screen.
//
// Three things happen here:
//   * the emblem floats on a water surface: pointer parallax, orbit acceleration,
//     and a slow swell that lifts and tilts it;
//   * the canvas paints that surface — shallow-water caustic light, elliptical
//     ripple trains spreading from the emblem, a soft wake behind the pointer,
//     and a stone dropped wherever the visitor clicks;
//   * entering the database dives *through* the surface instead of flying the
//     emblem away: ripples surge, the water closes over the viewport, and the
//     catalog rises out of the blur.
//
// Everything here is a progressive enhancement — reduced-motion visitors and
// browsers without the needed APIs get plain hash navigation, and the CSS
// animation remains the no-JS fallback for the orbit.
const reduced = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const nextFrame = () => new Promise(resolve => requestAnimationFrame(() => resolve()));

export function replayCoverEntrance(cover) {
  if (reduced || !cover) return;
  const stack = cover.querySelector(".cover-stack");
  if (!stack) return;
  stack.style.animation = "none";
  void stack.offsetWidth;
  stack.style.animation = "";
}

let diving = false;

export function installCoverEffects(cover) {
  if (!cover) return;
  cover.addEventListener("click", event => {
    const link = event.target.closest('a[href="#/materials"]');
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    enterWithDive(event);
  });
  if (reduced) return;
  const wrap = cover.querySelector(".cover-stage-wrap");
  const orbit = cover.querySelector(".cover-orbit");
  const tile = cover.querySelector(".cover-emblem");
  if (!wrap || !orbit || !tile) return;
  let orbitAnim = null;
  if (typeof orbit.animate === "function") {
    orbit.style.animation = "none";
    orbitAnim = orbit.animate(
      [{ transform: "rotate(0deg)", opacity: .4 }, { transform: "rotate(180deg)", opacity: .7 }, { transform: "rotate(360deg)", opacity: .4 }],
      { duration: 46000, iterations: Infinity, easing: "linear" }
    );
  }
  let targetX = 0, targetY = 0, curX = 0, curY = 0, rate = 1, targetRate = 1, hovering = false, ticking = false, lastT = 0;
  const tick = now => {
    const dt = Math.min(.064, (now - lastT) / 1000);
    lastT = now;
    const k = 1 - Math.pow(.0025, dt);
    curX += (targetX - curX) * k;
    curY += (targetY - curY) * k;
    rate += (targetRate - rate) * k;
    if (orbitAnim) orbitAnim.playbackRate = rate;
    // the swell only rides along with a moving pointer: an element that never
    // stops moving can no longer be clicked or focused by assistive tooling
    const swell = Math.sin(now / 1000 * .62) * .9 * Math.min(1, Math.abs(curX) + Math.abs(curY));
    wrap.style.transform = `translate3d(${(curX * 10).toFixed(2)}px, ${(curY * 8 + swell).toFixed(2)}px, 0)`;
    orbit.style.translate = `${(-curX * 18).toFixed(2)}px ${(-curY * 14).toFixed(2)}px`;
    tile.style.transform = `perspective(900px) rotateX(${(-curY * 3.5 + swell * .4).toFixed(2)}deg) rotateY(${(curX * 3.5).toFixed(2)}deg)${hovering ? " translateY(-4px) scale(1.02)" : ""}`;
    const settled = Math.abs(targetX - curX) < .002 && Math.abs(targetY - curY) < .002 && Math.abs(targetRate - rate) < .01;
    if (settled && targetX === 0 && targetY === 0 && targetRate === 1 && !hovering) { ticking = false; return; }
    requestAnimationFrame(tick);
  };
  const wake = () => { if (!ticking) { ticking = true; lastT = performance.now(); requestAnimationFrame(tick); } };
  cover.addEventListener("pointermove", event => {
    const box = cover.getBoundingClientRect();
    if (!box.width || !box.height) return;
    targetX = Math.max(-1, Math.min(1, (event.clientX - (box.left + box.width / 2)) / (box.width / 2)));
    targetY = Math.max(-1, Math.min(1, (event.clientY - (box.top + box.height / 2)) / (box.height / 2)));
    wake();
  });
  cover.addEventListener("pointerleave", () => { targetX = 0; targetY = 0; wake(); });
  tile.addEventListener("pointerenter", () => { hovering = true; targetRate = 6; wake(); });
  tile.addEventListener("pointerleave", () => { hovering = false; targetRate = 1; wake(); });
  document.addEventListener("visibilitychange", wake);
  window.addEventListener("hashchange", wake);
  wake();
}

// ---------------------------------------------------------------------------
// Dive transition: the emblem sinks, the water closes over the viewport, and the
// catalog surfaces out of the blur. Roughly 1.2s, skipped entirely for
// reduced-motion visitors (they get the plain hash navigation).
async function enterWithDive(event) {
  if (reduced || diving) return;
  const cover = document.querySelector("#landing-cover");
  const tile = document.querySelector(".cover-emblem");
  if (!cover || !tile || typeof tile.animate !== "function") return;
  event.preventDefault();
  diving = true;
  const orbit = cover.querySelector(".cover-orbit");
  const header = document.querySelector(".site-header");
  const veil = document.createElement("div");
  veil.className = "cover-dive";
  veil.setAttribute("aria-hidden", "true");
  // The dive has to pass *through* the surface, so the last painted frame of the
  // water is carried onto the veil and zoomed past the camera. A plain colour
  // fade reads as a screen wipe, not as sinking.
  const surface = document.createElement("div");
  surface.className = "cover-dive-surface";
  const waterCanvas = cover.querySelector(".cover-canvas");
  if (waterCanvas && typeof waterCanvas.toDataURL === "function") {
    try {
      surface.style.backgroundImage = `url(${waterCanvas.toDataURL()})`;
    } catch { /* tainted or unsupported: the gradient veil alone still works */ }
  }
  veil.appendChild(surface);
  document.body.appendChild(veil);
  if (header) header.style.transition = "none";
  tile.style.pointerEvents = "none";
  if (canvasState && canvasState.burst) canvasState.burst();
  const running = [];
  const run = (node, frames, options) => {
    if (!node || typeof node.animate !== "function") return Promise.resolve();
    const anim = node.animate(frames, options);
    running.push(anim);
    return anim.finished.catch(() => {});
  };
  try {
    // 1. a stone lands: the emblem dips under the surface and dissolves into it
    run(tile, [
      { transform: "translateY(0) scale(1)", opacity: 1, filter: "blur(0px)" },
      { transform: "translateY(-14px) scale(1.05)", opacity: 1, filter: "blur(0px)", offset: .2 },
      { transform: "translateY(120px) scale(.72)", opacity: .04, filter: "blur(11px)" }
    ], { duration: 1000, easing: "cubic-bezier(.34,.04,.5,1)", fill: "forwards" });
    run(orbit, [
      { transform: "scale(1) rotate(0deg)", opacity: .5 },
      { transform: "scale(2.8) rotate(70deg)", opacity: .12, offset: .7 },
      { transform: "scale(3.6) rotate(104deg)", opacity: 0 }
    ], { duration: 960, easing: "cubic-bezier(.18,.8,.25,1)", fill: "forwards" });
    run(cover, [
      { transform: "scale(1)", filter: "blur(0px)" },
      { transform: "scale(1.12)", filter: "blur(2px)" }
    ], { duration: 1100, easing: "cubic-bezier(.3,.05,.5,1)", fill: "forwards" });
    // 2. the camera sinks: the water surface rushes past and closes overhead
    run(veil, [{ opacity: 0 }, { opacity: 1, offset: .34 }, { opacity: 1 }],
      { duration: 1020, easing: "cubic-bezier(.4,.05,.45,1)", fill: "forwards" });
    run(surface, [
      { transform: "scale(1)", opacity: 1, filter: "blur(0px)" },
      { transform: "scale(1.55)", opacity: .8, filter: "blur(5px)", offset: .5 },
      { transform: "scale(2.4)", opacity: 0, filter: "blur(16px)" }
    ], { duration: 1020, easing: "cubic-bezier(.3,.1,.4,1)", fill: "forwards" });
    await new Promise(resolve => setTimeout(resolve, 560));
    location.hash = "#/materials";
    await new Promise(resolve => window.addEventListener("hashchange", resolve, { once: true }));
    await nextFrame();
    // 3. surfacing: the catalog rises out of the water while the veil lifts
    const home = document.querySelector("#home-view");
    run(veil, [{ opacity: 1, transform: "scale(1)", filter: "blur(0px)" }, { opacity: 0, transform: "scale(1.04)", filter: "blur(7px)" }],
      { duration: 660, easing: "cubic-bezier(.3,.55,.3,1)", fill: "forwards" });
    await run(home, [
      { opacity: 0, transform: "translateY(26px) scale(.99)", filter: "blur(8px)" },
      { opacity: 1, transform: "none", filter: "blur(0px)" }
    ], { duration: 720, delay: 80, easing: "cubic-bezier(.2,.7,.2,1)", fill: "both" });
  } finally {
    for (const anim of running) { try { anim.cancel(); } catch { /* already finished */ } }
    veil.remove();
    tile.style.pointerEvents = "";
    if (header) header.style.transition = "";
    diving = false;
  }
}

// ---------------------------------------------------------------------------
// The water. A static, seamlessly tiling caustic light field is generated once
// per theme and scrolled in three layers (different scale, heading, and speed)
// so the surface stays alive for the cost of three patterned fills per frame.
// Ripples are elliptical crest/trough pairs: a highlight nudged against a shadow
// is what makes a line read as a wave rather than as a circle.
let canvasState = null;

const TAU = Math.PI * 2;
const SURFACE_SQUASH = .46;      // vertical compression of the water plane
const CAUSTIC_TILE = 256;

const PALETTE = {
  light: {
    top: [229, 246, 248], mid: [206, 234, 238], bottom: [174, 214, 221],
    glow: [255, 255, 255], glowAlpha: .46,
    caustic: [255, 255, 255], causticAlpha: .8, causticMode: "source-over",
    pool: [255, 255, 255], poolAlpha: .46, poolMode: "source-over",
    shaft: [255, 255, 255], shaftAlpha: .32,
    crest: [255, 255, 255], crestAlpha: 1,
    trough: [26, 104, 120], troughAlpha: .5,
    glint: [255, 255, 255], glintAlpha: .95,
    vignette: [8, 66, 80], vignetteAlpha: .14
  },
  dark: {
    top: [10, 35, 43], mid: [6, 24, 31], bottom: [3, 13, 18],
    glow: [86, 196, 212], glowAlpha: .18,
    caustic: [138, 232, 245], causticAlpha: .3, causticMode: "lighter",
    pool: [116, 214, 230], poolAlpha: .2, poolMode: "lighter",
    shaft: [128, 220, 234], shaftAlpha: .16,
    crest: [214, 250, 255], crestAlpha: .95,
    trough: [0, 0, 0], troughAlpha: .34,
    glint: [232, 253, 255], glintAlpha: .95,
    vignette: [0, 0, 0], vignetteAlpha: .46
  }
};
const rgba = (color, alpha) => `rgba(${color[0]},${color[1]},${color[2]},${Math.max(0, Math.min(1, alpha)).toFixed(4)})`;

export function startCoverCanvas(cover) {
  if (!cover) return;
  const canvas = cover.querySelector(".cover-canvas");
  if (!canvas || typeof canvas.getContext !== "function") return;
  if (!canvasState || canvasState.canvas !== canvas) canvasState = createScene(canvas, cover);
  canvasState.kick();
}

// Seamlessly tiling caustic filaments. The bright web is the near-zero set of a
// sum of integer-frequency waves, so the tile wraps exactly and can be repeated.
// Two extra periodic terms break the web up: a slow envelope leaves calm water
// between lit patches, and a fast carrier beads each filament into sparkles.
// Without them the zero set is uniformly distributed and reads as a glowing net.
function buildCausticTile(color) {
  const cv = document.createElement("canvas");
  cv.width = cv.height = CAUSTIC_TILE;
  const c = cv.getContext("2d");
  if (!c || typeof c.createImageData !== "function") return null;
  const image = c.createImageData(CAUSTIC_TILE, CAUSTIC_TILE);
  const data = image.data;
  const step = 1 / CAUSTIC_TILE;
  let p = 0;
  for (let y = 0; y < CAUSTIC_TILE; y++) {
    const v = y * step;
    for (let x = 0; x < CAUSTIC_TILE; x++) {
      const u = x * step;
      const s1 = Math.sin(TAU * (2 * u + 3 * v) + 1.3);
      const s2 = Math.sin(TAU * (3 * u - 2 * v) + 4.1);
      const s3 = Math.sin(TAU * (1 * u + 5 * v) + 2.7);
      const s4 = Math.sin(TAU * (5 * u - 3 * v) + 5.5);
      const h = (s1 + s2 + s3 + s4) * .25;
      const line = 1 - Math.min(1, Math.abs(h) * 5.4);
      // calm patches: a slow periodic envelope, so much of the water is dark
      const env = .06 + .94 * Math.max(0, Math.sin(TAU * (1 * u + 1 * v) + .9)) ** .8;
      // beading: bright focal points strung along each filament
      const bead = .55 + .45 * (.5 + .5 * Math.sin(TAU * (3 * u + 2 * v) + 2.2));
      const i = (Math.pow(line, 6) * .9 + Math.pow(line, 2.6) * .1) * env * bead;
      data[p++] = color[0];
      data[p++] = color[1];
      data[p++] = color[2];
      data[p++] = i * 255;
    }
  }
  c.putImageData(image, 0, 0);
  return cv;
}

function createScene(canvas, cover) {
  const ctx = canvas.getContext("2d");
  const landing = cover.closest("#landing-view") || cover;
  const stage = cover.querySelector(".cover-stage-wrap");
  let W = 1, H = 1, DPR = 1, cx = 0, cy = 0, coreR = 180;
  let running = false, raf = 0, lastT = 0, nowSec = 0, lastEmit = -3.4, surge = 0;
  let px = .5, py = .5, vx = .5, vy = .5, parX = 0, parY = 0;
  let ripples = [];
  const wake = { x: 0, y: 0, t: -9 };

  // glint sprite: a soft white pinpoint reused for every sparkle on a crest
  const sprite = document.createElement("canvas");
  sprite.width = sprite.height = 64;
  const sctx = sprite.getContext("2d");
  if (sctx) {
    const g = sctx.createRadialGradient(32, 32, 0, 32, 32, 32);
    g.addColorStop(0, "rgba(255,255,255,.98)");
    g.addColorStop(.3, "rgba(205,245,255,.55)");
    g.addColorStop(1, "rgba(205,245,255,0)");
    sctx.fillStyle = g;
    sctx.fillRect(0, 0, 64, 64);
  }

  const tiles = new Map();
  const tileFor = name => {
    if (!tiles.has(name)) tiles.set(name, buildCausticTile(PALETTE[name].caustic));
    return tiles.get(name);
  };
  const patterns = new Map();

  const layout = () => {
    DPR = Math.min(2, window.devicePixelRatio || 1);
    const box = cover.getBoundingClientRect();
    W = Math.max(1, Math.round(box.width));
    H = Math.max(1, Math.round(box.height));
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    canvas.style.width = `${W}px`;
    canvas.style.height = `${H}px`;
    const rect = stage ? stage.getBoundingClientRect() : box;
    cx = rect.left - box.left + rect.width / 2;
    cy = rect.top - box.top + rect.height / 2;
    coreR = Math.max(96, rect.width / 2 + 10);
    ripples = [];
  };

  // A stone in the water: one leading crest plus two slower trailing ones. A
  // real drop emits a train like this, and the dispersion is what stops the
  // pattern from reading as a single expanding circle.
  const drop = (x, y, power, t) => {
    const reach = Math.max(Math.hypot(x, y), Math.hypot(W - x, y), Math.hypot(x, H - y), Math.hypot(W - x, H - y)) * 1.05;
    const glints = [];
    const count = power > 1.2 ? 4 : power > .8 ? 3 : 2;
    for (let i = 0; i < count; i++) glints.push(Math.random() * TAU);
    for (let k = 0; k < 3; k++) {
      ripples.push({
        x, y,
        born: t - k * .17,
        speed: 172 - k * 30,
        r0: 12 + k * 20,
        amp: power * (k === 0 ? 1 : .5 - k * .09),
        reach,
        seed: Math.random() * TAU,
        wob: .010 + Math.random() * .016,
        spin: Math.random() < .5 ? -1 : 1,
        glints: k ? [] : glints
      });
    }
    while (ripples.length > 42) ripples.shift();
  };

  const radiusOf = (r, t) => r.r0 + Math.max(0, t - r.born) * r.speed;
  // fade in as the crest is born, then thin out as it runs across the water
  const amplitudeOf = (r, R) => {
    const birth = Math.min(1, R / 24);
    const travel = 46 / (46 + R * .42);
    const edge = Math.pow(1 - Math.min(1, R / r.reach), 1.15);
    return r.amp * birth * travel * edge;
  };

  const paintBody = theme => {
    const body = ctx.createLinearGradient(0, 0, 0, H);
    body.addColorStop(0, rgba(theme.top, 1));
    body.addColorStop(.58, rgba(theme.mid, 1));
    body.addColorStop(1, rgba(theme.bottom, 1));
    ctx.fillStyle = body;
    ctx.fillRect(0, 0, W, H);
    const reach = Math.hypot(W, H);
    // a broad sheen of reflected surface light, drifting slowly
    ctx.save();
    ctx.globalCompositeOperation = theme.poolMode;
    const sheenX = cx + Math.sin(nowSec * .21) * W * .06;
    const sheenY = cy - H * .1 + Math.cos(nowSec * .17) * H * .04;
    const sheen = ctx.createRadialGradient(sheenX, sheenY, 0, sheenX, sheenY, reach * .52);
    sheen.addColorStop(0, rgba(theme.pool, theme.poolAlpha));
    sheen.addColorStop(.55, rgba(theme.pool, theme.poolAlpha * .34));
    sheen.addColorStop(1, rgba(theme.pool, 0));
    ctx.fillStyle = sheen;
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
    // light from the emblem reaching down through the water: a soft elliptical
    // glow only — no polygon edges, those read as a hard cone
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    const drift = Math.sin(nowSec * .5) * coreR * .1;
    ctx.translate(cx + drift, cy + coreR * .55);
    ctx.scale(1, 1.85);
    const shaft = ctx.createRadialGradient(0, 0, coreR * .1, 0, 0, coreR * 1.15);
    shaft.addColorStop(0, rgba(theme.shaft, theme.shaftAlpha));
    shaft.addColorStop(.45, rgba(theme.shaft, theme.shaftAlpha * .34));
    shaft.addColorStop(1, rgba(theme.shaft, 0));
    ctx.fillStyle = shaft;
    ctx.beginPath();
    ctx.arc(0, 0, coreR * 1.15, 0, TAU);
    ctx.fill();
    ctx.restore();
  };

  const paintCaustics = (theme, name, light, t) => {
    const tile = tileFor(name);
    if (!tile || !ctx.createPattern) return;
    if (!patterns.has(name)) patterns.set(name, ctx.createPattern(tile, "repeat"));
    const pattern = patterns.get(name);
    if (!pattern) return;
    const scale = light ? 2.6 : 2.2;
    const reach = Math.hypot(W, H);
    // two layers at different scales and headings break the tile's period
    const layers = [
      { s: scale, ax: 11, ay: 5.5, rot: 0, alpha: theme.causticAlpha },
      { s: scale * 1.7, ax: -7, ay: 9, rot: .55, alpha: theme.causticAlpha * .74 }
    ];
    ctx.save();
    ctx.globalCompositeOperation = theme.causticMode;
    ctx.fillStyle = pattern;
    for (const layer of layers) {
      const period = CAUSTIC_TILE * layer.s;
      const ox = ((t * layer.ax) % period + period) % period;
      const oy = ((t * layer.ay) % period + period) % period;
      const breathe = .84 + .16 * Math.sin(t * .37 + layer.rot * 3);
      ctx.globalAlpha = Math.max(0, Math.min(1, layer.alpha * breathe));
      ctx.save();
      // centre on the emblem, then paint a patch large enough that the rotated
      // viewport corners are always covered — a short fillRect leaves a seam
      ctx.translate(cx + parX * .6, cy + parY * .6);
      ctx.rotate(layer.rot);
      ctx.scale(layer.s, layer.s);
      ctx.translate(-ox, -oy);
      const span = (reach * 2.2) / layer.s + CAUSTIC_TILE * 2;
      ctx.fillRect(-span / 2, -span / 2, span, span);
      ctx.restore();
    }
    ctx.restore();
  };

  const paintRipples = (theme, t) => {
    ctx.globalCompositeOperation = "source-over";
    ctx.setLineDash([]);
    for (let i = ripples.length - 1; i >= 0; i--) {
      const r = ripples[i];
      const R = radiusOf(r, t);
      const amp = amplitudeOf(r, R) * (1 + surge * .9);
      if (R > r.reach || amp < .05) { ripples.splice(i, 1); continue; }
      const rx = R, ry = R * SURFACE_SQUASH;
      const width = Math.max(1.4, 1.6 + amp * 5.2);
      const depth = Math.min(1, amp * 2.4);
      // A crest is a *continuous* soft line, not a dashed one: water reflects
      // the sky along the whole wavefront. Blur is borrowed from shadowBlur
      // (a real ctx.filter would cost far more per frame) which is what makes
      // the line read as light on water instead of a drawn oval.
      const spinPhase = r.seed + t * .35 * r.spin;
      // faint crest thickness wobble keeps the ellipse from looking machined
      const wob = r.wob * .8;
      const segs = Math.min(160, Math.max(64, Math.round(R * .5)));
      // traces the wavefront, offset vertically by `dy` so the lit lip and its
      // shadowed wall stay parallel
      const trace = dy => {
        ctx.beginPath();
        for (let s = 0; s <= segs; s++) {
          const a = (s / segs) * TAU;
          const swell = 1 + wob * (Math.sin(a * 3 + spinPhase) * .7 + Math.sin(a * 5 - spinPhase) * .3);
          const X = r.x + Math.cos(a) * rx * swell;
          const Y = r.y + dy + Math.sin(a) * ry * swell;
          if (s) ctx.lineTo(X, Y); else ctx.moveTo(X, Y);
        }
        ctx.closePath();
      };
      ctx.save();
      // one pass: soft light along the whole crest, brighter where it faces up
      trace(0);
      const shade = ctx.createLinearGradient(r.x, r.y - ry, r.x, r.y + ry);
      shade.addColorStop(0, rgba(theme.crest, Math.min(1, theme.crestAlpha * amp * 1.9 + .02)));
      shade.addColorStop(.42, rgba(theme.crest, Math.min(1, theme.crestAlpha * amp * 1.1)));
      shade.addColorStop(.75, rgba(theme.crest, Math.min(1, theme.crestAlpha * amp * .28)));
      shade.addColorStop(1, rgba(theme.crest, 0));
      ctx.strokeStyle = shade;
      ctx.lineWidth = width;
      ctx.shadowColor = rgba(theme.crest, Math.min(1, theme.crestAlpha * amp * .8));
      ctx.shadowBlur = width * 2.6;
      ctx.stroke();
      ctx.shadowBlur = 0;
      // the shaded near wall just below the lit lip
      trace(width * .9);
      ctx.strokeStyle = rgba(theme.trough, theme.troughAlpha * depth * .55);
      ctx.lineWidth = width * .8;
      ctx.stroke();
      ctx.restore();
      // sparkles ride the leading crest
      for (const angle of r.glints) {
        const a = angle + t * .22 * r.spin;
        const gx = r.x + Math.cos(a) * rx;
        const gy = r.y + Math.sin(a) * ry;
        const size = 6 + amp * 30;
        ctx.globalAlpha = Math.min(1, amp * 2.8) * theme.glintAlpha;
        ctx.drawImage(sprite, gx - size / 2, gy - size / 2, size, size);
      }
      ctx.globalAlpha = 1;
    }
  };

  const paintVignette = theme => {
    const g = ctx.createRadialGradient(cx, cy, Math.min(W, H) * .2, cx, cy, Math.max(W, H) * .78);
    g.addColorStop(0, rgba(theme.vignette, 0));
    g.addColorStop(1, rgba(theme.vignette, theme.vignetteAlpha));
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  };

  const draw = now => {
    const t = now / 1000;
    nowSec = t;
    const dt = Math.min(.05, Math.max(.001, (now - lastT) / 1000));
    lastT = now;
    const light = document.documentElement.dataset.theme === "light";
    const theme = light ? PALETTE.light : PALETTE.dark;
    vx += (px - vx) * .06;
    vy += (py - vy) * .06;
    parX = (vx - .5) * -24;
    parY = (vy - .5) * -18;
    surge *= Math.exp(-1.1 * dt);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.clearRect(0, 0, W, H);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
    paintBody(theme);
    ctx.save();
    ctx.translate(parX, parY);
    paintCaustics(theme, light ? "light" : "dark", light, t);
    if (!reduced && t - lastEmit > 3.3) {
      lastEmit = t;
      drop(cx + (Math.random() - .5) * 26, cy + 34 + (Math.random() - .5) * 12, 1.05, t);
    }
    paintRipples(theme, t);
    ctx.restore();
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
    paintVignette(theme);
  };

  const loop = now => {
    if (document.hidden || !landing.isConnected || landing.hidden) { running = false; return; }
    draw(now);
    raf = requestAnimationFrame(loop);
  };
  const kick = () => {
    if (reduced || running || document.hidden || !landing.isConnected || landing.hidden) return;
    running = true;
    lastT = performance.now();
    raf = requestAnimationFrame(loop);
  };
  const burst = () => {
    if (reduced || !landing.isConnected || landing.hidden) return;
    surge = 1;
    drop(cx, cy + 40, 2.4, nowSec);
    setTimeout(() => drop(cx + 34, cy + 24, 1.5, nowSec), 120);
  };

  layout();
  window.addEventListener("resize", () => { layout(); if (reduced) draw(performance.now()); });
  cover.addEventListener("pointermove", event => {
    const box = cover.getBoundingClientRect();
    if (!box.width || !box.height) return;
    px = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    py = Math.min(1, Math.max(0, (event.clientY - box.top) / box.height));
    if (reduced) return;
    const x = event.clientX - box.left - parX;
    const y = event.clientY - box.top - parY;
    if (nowSec - wake.t > .14 && Math.hypot(x - wake.x, y - wake.y) > 92) {
      wake.x = x; wake.y = y; wake.t = nowSec;
      drop(x, y, .5, nowSec);
    }
  });
  // clicking the water drops a stone; clicks on links belong to the router
  cover.addEventListener("click", event => {
    if (reduced) return;
    if (event.target && event.target.closest && event.target.closest("a, button")) return;
    if (nowSec - wake.t < .12) return;
    const box = cover.getBoundingClientRect();
    if (!box.width || !box.height) return;
    const x = event.clientX - box.left - parX;
    const y = event.clientY - box.top - parY;
    wake.x = x; wake.y = y; wake.t = nowSec;
    drop(x, y, 1.3, nowSec);
  });
  document.addEventListener("visibilitychange", kick);
  if (reduced) {
    // one composed still frame: two crest trains settled around the emblem
    drop(cx, cy + 40, 1.05, 2.6);
    drop(cx, cy + 40, 1.05, .4);
    draw(5200 + 3400);
  } else {
    kick();
  }
  return { canvas, kick, burst };
}
