// Runs inside the Clanker page iframe. Asks the dashboard page (nav.js) to make dashboard calls with the
// reviewer's own session. Only works when embedded in the dashboard (the sidebar entry).
(() => {
  const PARENT = "https://ds.shipwrights.dev";
  const available = window.parent !== window;
  const pending = new Map();
  let n = 0;

  window.addEventListener("message", (e) => {
    if (e.source !== window.parent || e.origin !== PARENT) return;
    const m = e.data;
    if (!m || (m.clanker !== "dash-result" && m.clanker !== "dash-progress")) return;
    const p = pending.get(m.id);
    if (!p) return;
    if (m.clanker === "dash-progress") return p.onProgress?.(m.text);
    pending.delete(m.id);
    m.ok ? p.resolve(m.data) : p.reject(new Error(m.error));
  });

  function call(op, payload, onProgress) {
    return new Promise((resolve, reject) => {
      if (!available) return reject(new Error("Open Clanker from the dashboard sidebar to review from here."));
      const id = ++n;
      pending.set(id, { resolve, reject, onProgress });
      window.parent.postMessage({ clanker: "dash", id, op, payload }, PARENT);
    });
  }

  globalThis.ClankerBridge = {
    available,
    status: (slug, id) => call("status", { slug, id }),
    reject: (payload, onProgress) => call("reject", payload, onProgress),
  };
})();
