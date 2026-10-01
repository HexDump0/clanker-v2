// Adds a "Clanker" entry to the dashboard sidebar. Clicking it shows the judgements page
// over the dashboard's main panel (an iframe of the extension page), without leaving the SPA.
(() => {
  const ext = globalThis.browser ?? globalThis.chrome;
  const BOT_ICON =
    '<path d="M12 8V4H8"></path><rect width="16" height="12" x="4" y="8" rx="2"></rect>' +
    '<path d="M2 14h2"></path><path d="M20 14h2"></path><path d="M15 13v2"></path><path d="M9 13v2"></path>';

  let overlay = null;
  let link = null;
  let lastPath = location.pathname;

  const sidebarNav = () => document.querySelector("aside nav");

  function makeLink(nav) {
    // Clone an inactive entry so the new one picks up the dashboard's own styling and
    // collapse/expand behaviour. cloneNode drops React's handlers, so it is inert to the app.
    const model =
      [...nav.querySelectorAll("a")].find((a) => a.className.includes("border-transparent")) ||
      nav.querySelector("a");
    if (!model) return null;
    const a = model.cloneNode(true);
    a.dataset.clankerNav = "1";
    a.title = "Clanker";
    a.setAttribute("href", "#clanker");
    a.removeAttribute("aria-current");
    const svg = a.querySelector("svg");
    if (svg) {
      const doc = new DOMParser().parseFromString(
        `<svg xmlns="http://www.w3.org/2000/svg">${BOT_ICON}</svg>`, "image/svg+xml");
      svg.replaceChildren(...[...doc.documentElement.childNodes].map((n) => document.importNode(n, true)));
    }
    const label = a.querySelector("span");
    if (label) label.textContent = "Clanker";
    a.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      overlay ? closeOverlay() : openOverlay();
    });
    return a;
  }

  function placeOverlay() {
    const main = document.querySelector("main");
    if (!overlay || !main) return;
    const r = main.getBoundingClientRect();
    Object.assign(overlay.style, {
      left: `${r.left}px`,
      top: `${r.top}px`,
      width: `${r.width}px`,
      height: `${r.height}px`,
    });
  }

  // The cert-page button would sit on top of the embedded page; hide it while that is open.
  const setPanelHidden = (hidden) =>
    document.querySelectorAll("[data-clanker-panel]").forEach((el) => (el.style.display = hidden ? "none" : ""));

  function openOverlay() {
    if (!document.querySelector("main")) return;
    setPanelHidden(true);
    overlay = document.createElement("div");
    overlay.dataset.clankerOverlay = "1";
    Object.assign(overlay.style, {
      position: "fixed",
      zIndex: "40",
      borderRadius: "12px",
      overflow: "hidden",
      border: "1px solid rgba(255,255,255,.1)",
      background: "oklch(21% 0.006 286)",
    });
    const frame = document.createElement("iframe");
    frame.src = ext.runtime.getURL("judgements.html?embedded=1");
    Object.assign(frame.style, { width: "100%", height: "100%", border: "0" });
    overlay.append(frame);
    document.body.append(overlay);
    placeOverlay();
    if (link) {
      link.style.background = "rgba(255,255,255,.05)";
      link.style.borderLeftColor = "#38bdf8";
    }
  }

  function closeOverlay() {
    setPanelHidden(false);
    overlay?.remove();
    overlay = null;
    if (link) {
      link.style.background = "";
      link.style.borderLeftColor = "";
    }
  }

  function ensureLink() {
    const nav = sidebarNav();
    if (!nav || nav.querySelector("[data-clanker-nav]")) return;
    link = makeLink(nav);
    if (link) nav.append(link);
  }

  // Any other sidebar link, a route change, or Escape returns to the normal dashboard.
  document.addEventListener(
    "click",
    (e) => {
      const a = e.target.closest?.("a");
      if (overlay && a && !a.dataset.clankerNav && a.closest("aside")) closeOverlay();
    },
    true,
  );
  document.addEventListener("keydown", (e) => e.key === "Escape" && overlay && closeOverlay());
  addEventListener("resize", placeOverlay);

  let scheduled = false;
  new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      ensureLink();
      if (location.pathname !== lastPath) {
        lastPath = location.pathname;
        closeOverlay();
      }
      placeOverlay(); // the sidebar can resize the main panel
    });
  }).observe(document.body, { childList: true, subtree: true });
  ensureLink();
})();
