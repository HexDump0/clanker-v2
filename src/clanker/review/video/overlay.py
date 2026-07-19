"""The injected highlight overlay: dim mask, pulsing spotlight, callout card.

Pure static JS/CSS evaluated inside the recorded page. Callout text is passed
as evaluate() arguments and set via textContent, so untrusted page content and
untrusted callout text alike can never execute. The overlay never reads page
data back out — it only draws.

The dim mask and spotlight are drawn on a full-viewport <canvas>, not with DOM
elements. Large fixed overlay elements (giant box-shadow spreads, full-width
panels) rasterize patchily or not at all in headless Chromium's screencast on
some pages (observed on GitHub's 404 page); a canvas bitmap composites
reliably everywhere. The small callout card stays DOM for text layout.
"""

from __future__ import annotations

OVERLAY_JS = r"""
() => {
  if (window.__clankerOverlay) return;

  const Z = 2147483647; // real pages use surprisingly large z-indexes; take the max
  const style = document.createElement("style");
  style.textContent = `
    .clanker-card {
      position: absolute; z-index: 2; pointer-events: none;
      max-width: 400px; padding: 14px 18px 16px;
      background: #17171d; color: #e8e8ec;
      border: 1px solid #3a3a44; border-left: 4px solid #ec3750;
      border-radius: 12px; box-shadow: 0 12px 40px rgba(0, 0, 0, 0.55);
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      opacity: 0; transform: translateY(14px);
      transition: opacity 0.45s ease-out, transform 0.45s ease-out;
    }
    .clanker-card .clanker-badge {
      font-size: 10px; font-weight: 700; letter-spacing: 1.5px;
      color: #ec3750; margin-bottom: 6px;
    }
    .clanker-card .clanker-title {
      font-size: 17px; font-weight: 700; color: #ffffff; margin-bottom: 6px;
      line-height: 1.3;
    }
    .clanker-card .clanker-body { font-size: 14px; line-height: 1.5; color: #c9c9d2; }
  `;
  document.documentElement.appendChild(style);

  let targetEl = null;
  let useViewport = false;
  let layer = null;
  let raf = 0;

  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };

  const findByText = (needle) => {
    const clean = (s) => s.replace(/\s+/g, " ").trim().toLowerCase();
    const want = clean(needle);
    // First: a single text node containing the snippet.
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => {
        const p = node.parentElement;
        if (!p || ["SCRIPT", "STYLE", "NOSCRIPT"].includes(p.tagName) || !visible(p)) {
          return NodeFilter.FILTER_REJECT;
        }
        return clean(node.data).includes(want)
          ? NodeFilter.FILTER_ACCEPT
          : NodeFilter.FILTER_SKIP;
      },
    });
    const node = walker.nextNode();
    if (node) {
      const parent = node.parentElement;
      return parent.closest("p, li, h1, h2, h3, h4, td, th, article, section, div") || parent;
    }
    // Fallback: the snippet spans multiple nodes (styled fragments, links) —
    // descend to the deepest visible element whose combined text contains it.
    if (!clean(document.body.textContent).includes(want)) return null;
    let el = document.body;
    let descending = true;
    while (descending) {
      descending = false;
      for (const child of el.children) {
        if (visible(child) && clean(child.textContent).includes(want)) {
          el = child;
          descending = true;
          break;
        }
      }
    }
    return el === document.body ? null : el;
  };

  // Repaint loop: dim everything, punch out the spotlight cutout, stroke a
  // gently pulsing red border around it. Redrawn each frame for the pulse and
  // for the fade controlled by alpha.
  const paint = (ctx, rect, vw, vh, alpha, t) => {
    ctx.clearRect(0, 0, vw, vh);
    ctx.globalAlpha = alpha;
    ctx.fillStyle = "rgba(6, 6, 12, 0.62)";
    ctx.fillRect(0, 0, vw, vh);
    const r = 10;
    const path = new Path2D();
    path.roundRect(rect.left, rect.top, rect.width, rect.height, r);
    ctx.save();
    ctx.globalCompositeOperation = "destination-out";
    ctx.fillStyle = "#fff";
    ctx.fill(path);
    ctx.restore();
    const pulse = 0.5 + 0.5 * Math.sin(t / 250);
    ctx.shadowColor = `rgba(236, 55, 80, ${0.35 + 0.4 * pulse})`;
    ctx.shadowBlur = 8 + 14 * pulse;
    ctx.strokeStyle = "#ec3750";
    ctx.lineWidth = 3;
    ctx.stroke(path);
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;
  };

  window.__clankerOverlay = {
    // Resolve the target and start scrolling it into view. Returns false if
    // the target cannot be found (the recorder then skips the scene).
    locate(spec) {
      useViewport = !!spec.viewport;
      targetEl = null;
      if (useViewport) return true;
      targetEl = spec.selector
        ? document.querySelector(spec.selector)
        : findByText(spec.text || "");
      if (!targetEl) return false;
      targetEl.scrollIntoView({ behavior: "smooth", block: "center" });
      return true;
    },

    // Measure the settled target and animate in the spotlight + callout.
    draw(title, body) {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const pad = 10;
      let rect;
      if (useViewport || !targetEl) {
        rect = { left: 14, top: 14, width: vw - 28, height: vh - 28 };
      } else {
        const r = targetEl.getBoundingClientRect();
        rect = {
          left: Math.max(4, r.left - pad),
          top: Math.max(4, r.top - pad),
          width: Math.min(vw - 8, r.width + pad * 2),
          height: Math.min(vh - 8, r.height + pad * 2),
        };
      }

      layer = document.createElement("div");
      layer.style.cssText =
        "position:fixed;left:0;top:0;width:100vw;height:100vh;overflow:hidden;" +
        `z-index:${Z};pointer-events:none;transform:translateZ(0);`;

      const canvas = document.createElement("canvas");
      canvas.width = vw;
      canvas.height = vh;
      canvas.style.cssText =
        "position:absolute;left:0;top:0;z-index:1;transition:opacity 0.4s ease;";
      const ctx = canvas.getContext("2d");

      const card = document.createElement("div");
      card.className = "clanker-card";
      for (const [cls, text] of [
        ["clanker-badge", "SW-CLANKER REVIEW"],
        ["clanker-title", title],
        ["clanker-body", body],
      ]) {
        const el = document.createElement("div");
        el.className = cls;
        el.textContent = text;
        card.appendChild(el);
      }

      layer.appendChild(canvas);
      layer.appendChild(card);
      document.documentElement.appendChild(layer);

      // Place the callout below the spotlight when there is room, else above,
      // else centered over it (whole-viewport scenes).
      const cw = Math.min(400, vw - 32);
      const ch = card.getBoundingClientRect().height;
      let top;
      if (useViewport) {
        top = (vh - ch) / 2;
      } else if (rect.top + rect.height + ch + 24 < vh) {
        top = rect.top + rect.height + 14;
      } else if (rect.top - ch - 24 > 0) {
        top = rect.top - ch - 14;
      } else {
        top = Math.max(16, vh - ch - 24);
      }
      const left = Math.min(Math.max(16, rect.left), vw - cw - 16);
      Object.assign(card.style, { left: left + "px", top: top + "px" });

      const started = performance.now();
      const loop = (t) => {
        const alpha = Math.min(1, (t - started) / 400); // fade the mask in
        paint(ctx, rect, vw, vh, alpha, t);
        raf = requestAnimationFrame(loop);
      };
      raf = requestAnimationFrame(loop);
      requestAnimationFrame(() => {
        card.style.opacity = "1";
        card.style.transform = "translateY(0)";
      });
    },

    hide() {
      if (!layer) return;
      cancelAnimationFrame(raf);
      const doomed = layer;
      for (const el of doomed.children) el.style.opacity = "0";
      setTimeout(() => doomed.remove(), 450);
      layer = targetEl = null;
    },
  };
}
"""
