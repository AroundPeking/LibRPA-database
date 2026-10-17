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
