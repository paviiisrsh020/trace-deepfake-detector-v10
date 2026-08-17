/* particles.js — animated connected-node network background.
   Lightweight canvas animation: drifting nodes, proximity-based
   connecting lines, subtle mouse interaction. Pauses when the tab
   is hidden to avoid burning CPU in the background. */

(function () {
  const canvas = document.createElement("canvas");
  canvas.id = "particleCanvas";
  canvas.style.cssText = "position:fixed;inset:0;z-index:0;pointer-events:none;opacity:0.55;";
  document.body.insertBefore(canvas, document.body.firstChild);

  const ctx = canvas.getContext("2d");
  let w, h, dpr;
  let particles = [];
  let mouse = { x: null, y: null };
  let running = true;
  let animId = null;

  const COLORS = ["#f5ab3d", "#5093c9", "#c57fe0"];
  const NODE_COUNT_BASE = 70; // scaled by screen area below
  const LINK_DIST = 130;
  const MOUSE_DIST = 160;

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = window.innerWidth;
    h = window.innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function initParticles() {
    const area = w * h;
    const count = Math.max(30, Math.min(110, Math.round(NODE_COUNT_BASE * area / (1440 * 900))));
    particles = Array.from({ length: count }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.28,
      vy: (Math.random() - 0.5) * 0.28,
      r: Math.random() * 1.6 + 0.6,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
    }));
  }

  function step() {
    if (!running) return;
    ctx.clearRect(0, 0, w, h);

    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > w) p.vx *= -1;
      if (p.y < 0 || p.y > h) p.vy *= -1;
      p.x = Math.max(0, Math.min(w, p.x));
      p.y = Math.max(0, Math.min(h, p.y));
    }

    // connecting lines between nearby particles
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const a = particles[i], b = particles[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < LINK_DIST) {
          ctx.strokeStyle = `rgba(140,165,190,${(1 - dist / LINK_DIST) * 0.16})`;
          ctx.lineWidth = 0.6;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
      // link to mouse
      if (mouse.x !== null) {
        const dx = particles[i].x - mouse.x, dy = particles[i].y - mouse.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < MOUSE_DIST) {
          ctx.strokeStyle = `rgba(245,171,61,${(1 - dist / MOUSE_DIST) * 0.35})`;
          ctx.lineWidth = 0.8;
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(mouse.x, mouse.y);
          ctx.stroke();
        }
      }
    }

    // draw nodes on top
    for (const p of particles) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = p.color;
      ctx.globalAlpha = 0.75;
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    animId = requestAnimationFrame(step);
  }

  window.addEventListener("resize", () => { resize(); initParticles(); });
  window.addEventListener("mousemove", e => { mouse.x = e.clientX; mouse.y = e.clientY; });
  window.addEventListener("mouseleave", () => { mouse.x = null; mouse.y = null; });
  document.addEventListener("visibilitychange", () => {
    running = !document.hidden;
    if (running) step();
    else if (animId) cancelAnimationFrame(animId);
  });

  resize();
  initParticles();
  step();
})();
