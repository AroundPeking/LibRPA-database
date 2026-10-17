// Cover choreography: pointer parallax, orbit acceleration, and the fly-to-brand
// transition into the database. Everything here is a progressive enhancement —
// reduced-motion visitors and browsers without the needed APIs get plain
// hash navigation, and the CSS animation remains the no-JS fallback for the orbit.
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

let flying = false;

export function installCoverEffects(cover) {
  if (!cover) return;
  cover.addEventListener("click", event => {
    const link = event.target.closest('a[href="#/materials"]');
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    enterWithFlight(event);
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
    wrap.style.transform = `translate3d(${(curX * 10).toFixed(2)}px, ${(curY * 8).toFixed(2)}px, 0)`;
    orbit.style.translate = `${(-curX * 18).toFixed(2)}px ${(-curY * 14).toFixed(2)}px`;
    tile.style.transform = `perspective(900px) rotateX(${(-curY * 3.5).toFixed(2)}deg) rotateY(${(curX * 3.5).toFixed(2)}deg)${hovering ? " translateY(-4px) scale(1.02)" : ""}`;
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
}

async function enterWithFlight(event) {
  if (reduced || flying) return;
  const tile = document.querySelector(".cover-emblem");
  const header = document.querySelector(".site-header");
  if (!tile || !header || typeof tile.animate !== "function") return;
  event.preventDefault();
  flying = true;
  const start = tile.getBoundingClientRect();
  const clone = tile.cloneNode(true);
  clone.classList.add("cover-fly-clone");
  clone.setAttribute("aria-hidden", "true");
  clone.style.left = `${start.left}px`;
  clone.style.top = `${start.top}px`;
  clone.style.width = `${start.width}px`;
  clone.style.height = `${start.height}px`;
  clone.style.transition = "none";
  document.body.appendChild(clone);
  tile.style.visibility = "hidden";
  try {
    clone.animate(
      [{ transform: "scale(1)", filter: "drop-shadow(0 0 0 rgba(22,139,150,0))" }, { transform: "scale(1.06)", filter: "drop-shadow(0 14px 34px rgba(22,139,150,.5))" }],
      { duration: 140, easing: "ease-out" }
    ).finished.catch(() => {});
    await new Promise(resolve => setTimeout(resolve, 140));
    header.style.transition = "none";
    location.hash = "#/materials";
    await new Promise(resolve => window.addEventListener("hashchange", resolve, { once: true }));
    await nextFrame();
    const brand = document.querySelector(".brand-mark");
    if (brand) {
      const target = brand.getBoundingClientRect();
      const dx = (target.left + target.width / 2) - (start.left + start.width / 2);
      const dy = (target.top + target.height / 2) - (start.top + start.height / 2);
      const scale = target.height / start.height;
      await clone.animate(
        [
          { transform: "translate(0px, 0px) scale(1)", opacity: 1 },
          { transform: `translate(${(dx * .5).toFixed(1)}px, ${(dy * .35).toFixed(1)}px) scale(${((1 + scale) / 2).toFixed(3)})`, opacity: 1, offset: .55 },
          { transform: `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px) scale(${scale.toFixed(3)})`, opacity: 0 }
        ],
        { duration: 640, easing: "cubic-bezier(.2,.75,.2,1)" }
      ).finished.catch(() => {});
    }
  } finally {
    clone.remove();
    tile.style.visibility = "";
    header.style.transition = "";
    flying = false;
  }
}

// ---------------------------------------------------------------------------
// GW/RPA electron sea: a canvas scene behind the cover emblem.
// Layers: drifting electrons (additive glow), polarization bubbles (dashed
// loops with a running electron-hole arc), wavy screened-interaction lines
// from the emblem to each bubble, and expanding screening rings. Purely
// decorative; reduced-motion visitors get one static frame.
let canvasState = null;

export function startCoverCanvas(cover) {
  if (!cover) return;
  const canvas = cover.querySelector(".cover-canvas");
  if (!canvas || typeof canvas.getContext !== "function") return;
  if (!canvasState || canvasState.canvas !== canvas) canvasState = createScene(canvas, cover);
  canvasState.kick();
}

function createScene(canvas, cover) {
  const ctx = canvas.getContext("2d");
  const landing = cover.closest("#landing-view") || cover;
  const wrap = cover.querySelector(".cover-stage-wrap");
  let W = 1, H = 1, DPR = 1, cx = 0, cy = 0, coreR = 180;
  let parts = [], bubbles = [], rings = [];
  let running = false, raf = 0, lastRing = -2.6, lastT = 0;
  let px = .5, py = .5, vx = .5, vy = .5;

  const sprite = document.createElement("canvas");
  sprite.width = sprite.height = 64;
  const sctx = sprite.getContext("2d");
  const grad = sctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(255,255,255,.95)");
  grad.addColorStop(.28, "rgba(120,225,235,.5)");
  grad.addColorStop(1, "rgba(120,225,235,0)");
  sctx.fillStyle = grad;
  sctx.fillRect(0, 0, 64, 64);

  const rand = (a, b) => a + Math.random() * (b - a);

  const layout = () => {
    DPR = Math.min(2, window.devicePixelRatio || 1);
    const box = cover.getBoundingClientRect();
    W = Math.max(1, Math.round(box.width));
    H = Math.max(1, Math.round(box.height));
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    canvas.style.width = `${W}px`;
    canvas.style.height = `${H}px`;
    const stage = wrap ? wrap.getBoundingClientRect() : box;
    cx = stage.left - box.left + stage.width / 2;
    cy = stage.top - box.top + stage.height / 2;
    coreR = Math.max(120, stage.width / 2 + 12);
    const count = Math.max(40, Math.min(150, Math.round(W * H / 11000)));
    parts = Array.from({ length: count }, () => ({
      x: rand(0, W), y: rand(0, H),
      vx: rand(-9, 9), vy: rand(-9, 9),
      s: rand(7, 18), tw: rand(.5, 1.6), ph: rand(0, Math.PI * 2)
    }));
    const n = W < 700 ? 3 : 4;
    bubbles = Array.from({ length: n }, (_, i) => {
      const ang = rand(0, Math.PI * 2) + i * (Math.PI * 2 / n);
      const dist = rand(.3, .46) * Math.min(W, H);
      return {
        ax: cx + Math.cos(ang) * dist, ay: cy + Math.sin(ang) * dist,
        drift: rand(0, Math.PI * 2), driftR: rand(14, 34),
        r: rand(40, 92), breath: rand(.6, 1.4), brPh: rand(0, Math.PI * 2),
        spin: rand(.25, .6) * (Math.random() < .5 ? -1 : 1), arc: rand(0, Math.PI * 2),
        arcSpeed: rand(.5, 1.1) * (Math.random() < .5 ? -1 : 1), wobPh: rand(0, Math.PI * 2)
      };
    });
    rings = [];
  };

  const wavy = (x1, y1, x2, y2, phase, amp, color, alpha) => {
    const dx = x2 - x1, dy = y2 - y1;
    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len, ny = dx / len;
    ctx.beginPath();
    const steps = 26;
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const taper = Math.sin(t * Math.PI);
      const off = Math.sin(t * Math.PI * 3 + phase) * amp * taper;
      const x = x1 + dx * t + nx * off;
      const y = y1 + dy * t + ny * off;
      if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
    }
    ctx.strokeStyle = color(alpha);
    ctx.lineWidth = 1.4;
    ctx.stroke();
  };

  const draw = now => {
    const t = now / 1000;
    const light = document.documentElement.dataset.theme === "light";
    const hue = light ? "12,106,117" : "111,214,225";
    const col = a => `rgba(${hue},${a})`;
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.clearRect(0, 0, W, H);
    vx += (px - vx) * .06;
    vy += (py - vy) * .06;
    const ox = (vx - .5) * -22, oy = (vy - .5) * -16;
    ctx.translate(ox, oy);

    // expanding screening rings from the emblem
    if (t - lastRing > 2.6 && !reduced) {
      rings.push({ born: t });
      lastRing = t;
    }
    const maxR = Math.hypot(W, H) / 2;
    rings = rings.filter(ring => {
      const r = coreR + (t - ring.born) * 85;
      if (r > maxR) return false;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.strokeStyle = col(.2 * (1 - (r - coreR) / (maxR - coreR)));
      ctx.lineWidth = 1.2;
      ctx.stroke();
      return true;
    });

    // wavy screened-interaction lines: emblem -> each polarization bubble
    for (const b of bubbles) {
      const bx = b.ax + Math.cos(t * .12 + b.drift) * b.driftR;
      const by = b.ay + Math.sin(t * .09 + b.drift) * b.driftR;
      b.bx = bx; b.by = by;
      wavy(cx, cy, bx, by, t * .8 + b.wobPh, 7 + Math.sin(t * b.breath + b.brPh) * 4, col, light ? .22 : .3);
    }

    // polarization bubbles (RPA ring diagrams)
    for (const b of bubbles) {
      const r = b.r * (1 + Math.sin(t * b.breath + b.brPh) * .09);
      ctx.beginPath();
      ctx.arc(b.bx, b.by, r, 0, Math.PI * 2);
      ctx.setLineDash([3, 11]);
      ctx.lineDashOffset = -t * 22 * b.spin;
      ctx.strokeStyle = col(light ? .3 : .4);
      ctx.lineWidth = 1.2;
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.arc(b.bx, b.by, r, b.arc, b.arc + .95);
      b.arc += b.arcSpeed * .016;
      ctx.strokeStyle = col(light ? .55 : .8);
      ctx.lineWidth = 2.2;
      ctx.lineCap = "round";
      ctx.stroke();
      const g = r * 2.4;
      ctx.globalAlpha = light ? .1 : .16;
      ctx.drawImage(sprite, b.bx - g / 2, b.by - g / 2, g, g);
      ctx.globalAlpha = 1;
    }

    // electrons
    ctx.globalCompositeOperation = light ? "source-over" : "lighter";
    for (const p of parts) {
      p.x += p.vx * .016;
      p.y += p.vy * .016;
      if (p.x < -24) p.x = W + 24; else if (p.x > W + 24) p.x = -24;
      if (p.y < -24) p.y = H + 24; else if (p.y > H + 24) p.y = -24;
      const tw = .45 + .55 * (0.5 + 0.5 * Math.sin(t * p.tw + p.ph));
      ctx.globalAlpha = light ? .5 * tw : tw;
      ctx.drawImage(sprite, p.x - p.s / 2, p.y - p.s / 2, p.s, p.s);
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  };

  const loop = now => {
    if (document.hidden || !landing.isConnected || landing.hidden) { running = false; return; }
    draw(now);
    lastT = now;
    raf = requestAnimationFrame(loop);
  };
  const kick = () => {
    if (running || document.hidden || !landing.isConnected || landing.hidden) return;
    running = true;
    raf = requestAnimationFrame(loop);
  };

  layout();
  window.addEventListener("resize", () => { layout(); if (reduced) draw(performance.now()); });
  cover.addEventListener("pointermove", event => {
    const box = cover.getBoundingClientRect();
    if (!box.width || !box.height) return;
    px = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    py = Math.min(1, Math.max(0, (event.clientY - box.top) / box.height));
  });
  document.addEventListener("visibilitychange", kick);
  if (reduced) {
    rings.push({ born: 0 }, { born: -1.4 });
    draw(2600);
  } else {
    kick();
  }
  return { canvas, kick };
}
