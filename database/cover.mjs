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
// Electrons drift as additive-glow particles. Polarization bubbles are soft
// bodies: the screening rings expanding from the emblem knock them outward,
// and bubbles that touch each other repel — flashes and sparks mark the hits.
// Purely decorative; reduced-motion visitors get one static frame.
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
  let parts = [], bubbles = [], rings = [], sparks = [];
  let running = false, raf = 0, lastRing = -2.6, lastT = 0, nowSec = 0;
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
    coreR = Math.max(96, stage.width / 2 + 10);
    const count = Math.max(40, Math.min(150, Math.round(W * H / 11000)));
    parts = Array.from({ length: count }, () => ({
      x: rand(0, W), y: rand(0, H),
      vx: rand(-9, 9), vy: rand(-9, 9),
      s: rand(7, 18), tw: rand(.5, 1.6), ph: rand(0, Math.PI * 2)
    }));
    const span = Math.min(W, H);
    const n = W < 700 ? 4 : 7;
    bubbles = Array.from({ length: n }, (_, i) => {
      const ang = rand(0, Math.PI * 2) + i * (Math.PI * 2 / n);
      const dist = rand(.34, .44) * span;
      return {
        id: i,
        x: cx + Math.cos(ang) * dist, y: cy + Math.sin(ang) * dist,
        vx: rand(-14, 14), vy: rand(-14, 14),
        r: Math.max(22, rand(.05, .09) * span),
        breath: rand(.6, 1.4), brPh: rand(0, Math.PI * 2),
        spin: rand(.25, .6) * (Math.random() < .5 ? -1 : 1),
        flash: 0
      };
    });
    rings = [];
    sparks = [];
  };

  const spawnSparks = (x, y, nx, ny, count) => {
    if (sparks.length > 40) return;
    for (let i = 0; i < count; i++) {
      const spread = rand(-.9, .9);
      const speed = rand(28, 90);
      sparks.push({
        x, y,
        vx: (nx * Math.cos(spread) - ny * Math.sin(spread)) * speed,
        vy: (nx * Math.sin(spread) + ny * Math.cos(spread)) * speed,
        life: 1, s: rand(5, 10)
      });
    }
  };

  const physics = (dt) => {
    const damp = Math.exp(-1.05 * dt);
    for (const b of bubbles) {
      b.vx += (Math.random() - .5) * 26 * dt;
      b.vy += (Math.random() - .5) * 26 * dt;
      b.vx *= damp;
      b.vy *= damp;
    }
    for (const b of bubbles) {
      const dx = b.x - cx, dy = b.y - cy;
      const dist = Math.hypot(dx, dy) || 1;
      const min = coreR + b.r + 26;
      if (dist < min) {
        const nx = dx / dist, ny = dy / dist;
        b.x = cx + nx * min;
        b.y = cy + ny * min;
        const vn = b.vx * nx + b.vy * ny;
        if (vn < 0) {
          b.vx -= 1.6 * vn * nx;
          b.vy -= 1.6 * vn * ny;
          b.flash = Math.min(1, b.flash + .35);
        }
      }
      const m = b.r + 26;
      if (b.x < m) { b.x = m; b.vx = Math.abs(b.vx) * .8; }
      else if (b.x > W - m) { b.x = W - m; b.vx = -Math.abs(b.vx) * .8; }
      if (b.y < m) { b.y = m; b.vy = Math.abs(b.vy) * .8; }
      else if (b.y > H - m) { b.y = H - m; b.vy = -Math.abs(b.vy) * .8; }
    }
    // pairwise separation runs last so core/wall clamps cannot override it
    for (let iter = 0; iter < 2; iter++) {
      for (let i = 0; i < bubbles.length; i++) {
        for (let j = i + 1; j < bubbles.length; j++) {
          const a = bubbles[i], c = bubbles[j];
          const dx = c.x - a.x, dy = c.y - a.y;
          const dist = Math.hypot(dx, dy) || 1;
          const overlap = a.r + c.r - dist;
          if (overlap > 0) {
            const nx = dx / dist, ny = dy / dist;
            const ma = a.r * a.r, mc = c.r * c.r, total = ma + mc;
            a.x -= nx * overlap * (mc / total); a.y -= ny * overlap * (mc / total);
            c.x += nx * overlap * (ma / total); c.y += ny * overlap * (ma / total);
            const rv = (c.vx - a.vx) * nx + (c.vy - a.vy) * ny;
            if (rv < 0) {
              const imp = -1.7 * rv / (1 / ma + 1 / mc);
              a.vx -= imp * nx / ma; a.vy -= imp * ny / ma;
              c.vx += imp * nx / mc; c.vy += imp * ny / mc;
              a.flash = Math.min(1, a.flash + .5);
              c.flash = Math.min(1, c.flash + .5);
              const mx = (a.x + c.x) / 2, my = (a.y + c.y) / 2;
              spawnSparks(mx, my, nx, ny, 2);
            }
          }
        }
      }
    }
    for (const b of bubbles) {
      const sp = Math.hypot(b.vx, b.vy);
      if (sp > 150) { b.vx *= 150 / sp; b.vy *= 150 / sp; }
      b.x += b.vx * dt;
      b.y += b.vy * dt;
      b.flash *= Math.exp(-2.6 * dt);
    }
    for (const spark of sparks) {
      spark.x += spark.vx * dt;
      spark.y += spark.vy * dt;
      spark.life -= dt / .6;
    }
    sparks = sparks.filter(spark => spark.life > 0);
  };

  const draw = now => {
    const t = now / 1000;
    nowSec = t;
    const dt = Math.min(.05, Math.max(.001, (now - lastT) / 1000));
    lastT = now;
    const light = document.documentElement.dataset.theme === "light";
    const hue = light ? "12,106,117" : "111,214,225";
    const col = a => `rgba(${hue},${Math.min(1, a)})`;
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.clearRect(0, 0, W, H);
    vx += (px - vx) * .06;
    vy += (py - vy) * .06;
    ctx.translate((vx - .5) * -22, (vy - .5) * -16);

    physics(dt);

    // expanding screening rings: the wavefront shoves bubbles outward
    if (t - lastRing > 2.6 && !reduced) {
      rings.push({ born: t, hit: new Set() });
      lastRing = t;
    }
    const maxR = Math.hypot(W, H) / 2;
    rings = rings.filter(ring => {
      const R = coreR + (t - ring.born) * 85;
      if (R > maxR) return false;
      const energy = Math.max(0, 1 - (R - coreR) / (maxR - coreR));
      for (const b of bubbles) {
        if (ring.hit.has(b.id)) continue;
        const d = Math.hypot(b.x - cx, b.y - cy);
        if (Math.abs(d - R) < 30) {
          ring.hit.add(b.id);
          const nx = (b.x - cx) / (d || 1), ny = (b.y - cy) / (d || 1);
          const shove = (ring.manual ? 84 : 62) * Math.max(.25, energy);
          b.vx += nx * shove;
          b.vy += ny * shove;
          b.flash = 1;
          spawnSparks(b.x - nx * b.r, b.y - ny * b.r, nx, ny, 3);
        }
      }
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.strokeStyle = col((ring.manual ? .32 : .22) * energy);
      ctx.lineWidth = 1.2;
      ctx.stroke();
      return true;
    });

    // polarization bubbles: breathing dashed loops that flash when struck
    for (const b of bubbles) {
      const r = b.r * (1 + Math.sin(t * b.breath + b.brPh) * .08);
      const g = r * 2.2 * (1 + b.flash * .5);
      const fill = (light ? .06 : .09) + b.flash * (light ? .16 : .24);
      const shell = ctx.createRadialGradient(b.x, b.y, r * .3, b.x, b.y, r);
      shell.addColorStop(0, col(0));
      shell.addColorStop(.72, col(fill * .45));
      shell.addColorStop(1, col(fill));
      ctx.fillStyle = shell;
      ctx.beginPath();
      ctx.arc(b.x, b.y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = (light ? .08 : .13) + b.flash * (light ? .18 : .3);
      ctx.drawImage(sprite, b.x - g / 2, b.y - g / 2, g, g);
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(b.x, b.y, r, 0, Math.PI * 2);
      ctx.setLineDash([3, 11]);
      ctx.lineDashOffset = -t * 22 * b.spin;
      ctx.strokeStyle = col((light ? .3 : .42) + b.flash * .4);
      ctx.lineWidth = 1.2 + b.flash * 1.2;
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // electrons and collision sparks
    ctx.globalCompositeOperation = light ? "source-over" : "lighter";
    for (const spark of sparks) {
      ctx.globalAlpha = spark.life * (light ? .6 : .9);
      ctx.drawImage(sprite, spark.x - spark.s / 2, spark.y - spark.s / 2, spark.s, spark.s);
    }
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
    raf = requestAnimationFrame(loop);
  };
  const kick = () => {
    if (reduced || running || document.hidden || !landing.isConnected || landing.hidden) return;
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
  // tapping the cover background fires a screening ring from the emblem
  cover.addEventListener("click", event => {
    if (reduced) return;
    if (event.target && event.target.closest && event.target.closest("a, button")) return;
    if (!rings.some(ring => ring.manual && nowSec - ring.born < .12)) {
      rings.push({ born: nowSec, hit: new Set(), manual: true });
      lastRing = Math.max(lastRing, nowSec);
    }
  });
  document.addEventListener("visibilitychange", kick);
  if (reduced) {
    rings.push({ born: 0, hit: new Set() }, { born: -1.4, hit: new Set() });
    draw(2600);
  } else {
    kick();
  }
  return { canvas, kick };
}
