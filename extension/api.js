// Shared by the content script and the judgements page. Plain script (no modules) so it
// loads the same way in Chrome and Firefox. Exposes one global: ClankerApi.
(() => {
  const ext = globalThis.browser ?? globalThis.chrome;
  const DEFAULT_BASE = "http://127.0.0.1:8765";

  const storageGet = (key) =>
    new Promise((resolve) => {
      try {
        const r = ext.storage.local.get(key, (v) => resolve(v && v[key]));
        if (r && typeof r.then === "function") r.then((v) => resolve(v && v[key]));
      } catch {
        resolve(undefined);
      }
    });

  const sendMessage = (msg) =>
    new Promise((resolve) => {
      try {
        const r = ext.runtime.sendMessage(msg, (v) => resolve(v));
        if (r && typeof r.then === "function") r.then(resolve, () => resolve(undefined));
      } catch {
        resolve(undefined);
      }
    });

  async function getBase() {
    return ((await storageGet("apiBase")) || DEFAULT_BASE).replace(/\/+$/, "");
  }

  async function setBase(url) {
    await ext.storage.local.set({ apiBase: url.trim().replace(/\/+$/, "") });
  }

  async function request(path, { method = "GET", body, raw = false } = {}) {
    const reply = await sendMessage({ type: "getToken" });
    if (!reply || !reply.token) {
      throw new Error("Not logged in to the Shipwrights dashboard (no session cookie).");
    }
    const res = await fetch((await getBase()) + path, {
      method,
      headers: {
        Authorization: `Bearer ${reply.token}`,
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401) throw new Error("Clanker rejected your dashboard session.");
    if (res.status === 404) return null;
    if (!res.ok) {
      let detail = "";
      try { detail = (await res.json()).error || ""; } catch {}
      throw new Error(detail || `Clanker API error ${res.status}`);
    }
    return raw ? res : res.json();
  }

  globalThis.ClankerApi = {
    getBase,
    setBase,
    listResults: (verdict) =>
      request("/api/results" + (verdict ? `?verdict=${encodeURIComponent(verdict)}` : "")),
    getResult: (id) => request(`/api/results/${encodeURIComponent(id)}`),
    requestReview: (id) =>
      request(`/api/results/${encodeURIComponent(id)}/review`, { method: "POST", body: {} }),
    reviewStatus: (id) => request(`/api/results/${encodeURIComponent(id)}/review-status`),
    // Ask for a review and wait until it finishes. Resolves with the final status.
    async runReview(id, onStatus = () => {}) {
      await this.requestReview(id);
      for (;;) {
        const s = await this.reviewStatus(id);
        if (!s || s.state !== "running") return s || { state: "idle" };
        onStatus("Clanker is reviewing… (about a minute)");
        await new Promise((r) => setTimeout(r, 3000));
      }
    },
    exportFeedback: () => request("/api/feedback.jsonl", { raw: true }),
    sendFeedback: (id, body) =>
      request(`/api/results/${encodeURIComponent(id)}/feedback`, { method: "POST", body }),
    async pdfBlob(id) {
      const res = await request(`/api/results/${encodeURIComponent(id)}/pdf`, { raw: true });
      return res ? res.blob() : null;
    },
    // The <video> tag cannot send an Authorization header, so fetch it as a blob.
    async videoBlob(id) {
      const res = await request(`/api/results/${encodeURIComponent(id)}/video`, { raw: true });
      return res ? res.blob() : null;
    },
  };
})();
