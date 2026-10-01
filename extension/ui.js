// Shared UI helpers + the "result detail" view, used by the judgements page and the cert panel.
// Plain script (no modules); exposes one global: ClankerUI. All text goes through textContent.
(() => {
  const ICONS = {
    bot: '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    copy: '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
    back: '<path d="m15 18-6-6 6-6"/>',
    pen: '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/>',
    film: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18"/><path d="M17 3v18"/><path d="M3 12h18"/>',
    alert: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
    loader: '<path d="M21 12a9 9 0 1 1-6.219-8.56"/>',
  };

  const VERDICTS = {
    REJECT: { label: "Reject", tone: "bad", icon: "x" },
    APPROVE: { label: "Approve", tone: "ok", icon: "check" },
    NEEDS_HUMAN: { label: "Needs human", tone: "warn", icon: "alert" },
    FLAG_FOR_HUMAN: { label: "Needs human", tone: "warn", icon: "alert" },
  };
  const verdictMeta = (v) => VERDICTS[v] || { label: v || "Unknown", tone: "neutral", icon: "alert" };

  const SVG_NS = "http://www.w3.org/2000/svg";
  // Parse the static icon paths as SVG (no innerHTML) and return a fresh <svg>.
  function svgFrom(inner) {
    const doc = new DOMParser().parseFromString(`<svg xmlns="${SVG_NS}">${inner}</svg>`, "image/svg+xml");
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    for (const node of doc.documentElement.childNodes) svg.append(document.importNode(node, true));
    return svg;
  }

  function icon(name, size) {
    const svg = svgFrom(ICONS[name] || "");
    svg.setAttribute("class", "ic");
    if (size) { svg.style.width = svg.style.height = size + "px"; }
    return svg;
  }

  // Tiny hyperscript. Strings become text nodes (never HTML).
  function h(tag, props = {}, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "html") throw new Error("no raw html");
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid);
    return el;
  }

  function timeAgo(iso) {
    const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "just now";
    for (const [n, unit] of [[60, "m"], [3600, "h"], [86400, "d"]].reverse()) {
      if (s >= n) return `${Math.floor(s / n)}${unit} ago`;
    }
    return "just now";
  }

  const prettify = (code) => code.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  function reasonPairs(rec) {
    return rec.reasons.map((code, i) => ({
      code,
      label: (rec.reason_labels && rec.reason_labels[i]) || prettify(code),
    }));
  }

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch {}
    const ta = h("textarea", { style: "position:fixed;opacity:0" });
    ta.value = text; document.body.append(ta); ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch {}
    ta.remove();
    return ok;
  }

  function toastFactory(root) {
    let current = null, timer = null;
    return (msg, tone = "") => {
      current?.remove(); clearTimeout(timer);
      current = h("div", { class: `toast ${tone}`, role: "status" }, msg);
      root.append(current);
      timer = setTimeout(() => current?.remove(), 3600);
    };
  }

  // ---- blobs are cached per cert so reselecting a row does not refetch ----
  const videoCache = new Map();
  const videoBlob = (api, id) => {
    if (!videoCache.has(id)) {
      videoCache.set(id, api.videoBlob(id).then((b) => { if (!b) throw new Error("no video"); return b; }));
    }
    return videoCache.get(id);
  };
  const pdfUrls = new Map();
  async function openPdf(api, id) {
    if (!pdfUrls.has(id)) {
      const blob = await api.pdfBlob(id);
      if (!blob) throw new Error("no PDF for this review");
      pdfUrls.set(id, URL.createObjectURL(blob));
    }
    h("a", { href: pdfUrls.get(id), target: "_blank", rel: "noopener" }).click();
  }

  const badge = (verdict) => {
    const m = verdictMeta(verdict);
    return h("span", { class: `badge ${m.tone}` }, m.label);
  };
  const statusText = (verdict) => {
    const m = verdictMeta(verdict);
    return h("span", { class: `st ${m.tone}` }, m.label.toLowerCase());
  };

  /**
   * The pieces of a result, so each surface can arrange them. opts:
   *   api, toast, onChanged(record, rerun), useReason(text) -> bool, useVideo(blob) -> Promise
   * Returns { banner, message, video, reasons, info, feedback, pdfButton, rerunButton, right(), wrong() }.
   */
  function parts(rec, opts) {
    const { api, toast } = opts;
    const meta = verdictMeta(rec.verdict);
    const pairs = reasonPairs(rec);
    const out = {};

    out.banner = h("div", { class: `banner ${meta.tone}` },
      h("div", { class: "top" }, h("span", { class: "lbl", style: "color:inherit;opacity:.75" }, "Clanker"), h("span", { title: new Date(rec.created_at).toLocaleString() }, `reviewed ${timeAgo(rec.created_at)}`)),
      h("p", {}, rec.summary || "No summary."));

    // message for the shipper (rejects)
    if (rec.message) {
      const useReason = opts.useReason && h("button", { class: "btn t accent", onclick: () => {
        const ok = opts.useReason(rec.message);
        if (ok) toast("Filled the review box. Read it, then submit.", "ok");
        else { copyText(rec.message); toast("No review box here (claim the ship first). Copied instead."); }
      } }, "Use reason");
      out.message = h("div", { class: "pc" },
        h("div", { class: "pc-head" }, h("span", { class: "lbl" }, "Message for the shipper"),
          h("div", { class: "row-actions" },
            h("button", { class: "btn", onclick: async () => toast((await copyText(rec.message)) ? "Copied to clipboard" : "Could not copy", "ok") }, "Copy"),
            useReason)),
        h("pre", { class: "msg" }, rec.message));
    } else if (opts.useReason) {
      const text = [rec.summary, ...pairs.map((p) => `- ${p.label}`)].filter(Boolean).join("\n");
      out.message = h("div", { class: "row-actions" }, h("button", { class: "btn t accent", onclick: () => {
        const ok = opts.useReason(text);
        toast(ok ? "Filled the review box. Read it, then submit." : "No review box here (claim the ship first).", ok ? "ok" : "");
      } }, "Use summary as comment"));
    }

    // video
    if (rec.video_path) {
      const wrap = h("div", { class: "video-wrap" }, h("div", { class: "skeleton" }, "Loading video…"));
      const useVideo = opts.useVideo && h("button", { class: "btn t accent" }, "Use video");
      let blob = null;
      videoBlob(api, rec.cert_id).then((b) => {
        blob = b;
        wrap.replaceChildren(h("video", { controls: "", preload: "metadata", src: URL.createObjectURL(b) }));
      }).catch(() => wrap.replaceChildren(h("div", { class: "skeleton" }, "Could not load the video")));
      if (useVideo) {
        useVideo.addEventListener("click", async () => {
          if (!blob) return toast("Video is still loading");
          useVideo.disabled = true;
          try { await opts.useVideo(blob); } catch (e) { toast(`Upload failed: ${e.message}`, "bad"); useVideo.disabled = false; }
        });
      }
      out.video = h("div", { class: "pc" }, h("div", { class: "pc-head" }, h("span", { class: "lbl" }, "Video"), useVideo), wrap);
    }

    // reasons
    if (pairs.length) {
      out.reasons = h("div", { class: "pc" }, h("div", { class: "pc-head" }, h("span", { class: "lbl" }, rec.verdict === "REJECT" ? "Reasons" : "Why")),
        h("ul", { class: "reasons" }, pairs.map((p) => h("li", {}, h("span", { class: `dot ${meta.tone}` }), p.label))));
    }

    // key/value info
    const kv = (k, v) => h("div", { class: "kv" }, h("span", { class: "k" }, k), h("span", { class: "v" }, v));
    out.info = h("div", { class: "pc" },
      kv("Ship", h("span", { title: rec.cert_id }, rec.cert_id.slice(0, 8))),
      kv("Verdict", statusText(rec.verdict)),
      kv("Reviewed", new Date(rec.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })),
      kv("Reasons", String(pairs.length)));

    // feedback
    const status = h("div", { class: "hint" });
    const rightBtn = h("button", { class: "btn t ok block" }, "Clanker was right");
    const wrongBtn = h("button", { class: "btn t bad block" }, "Clanker was wrong");
    const picked = new Set();
    const note = h("textarea", { rows: "3", placeholder: pairs.length ? "Anything else? (optional)" : "What did Clanker get wrong?" });
    const wrongForm = h("div", { class: "stack", hidden: "", style: "margin-top:10px" },
      pairs.length ? h("div", { class: "lbl" }, "Which reasons were wrong?") : null,
      pairs.map((p) => {
        const b = h("button", { class: "pick", type: "button", onclick: () => {
          picked.has(p.code) ? picked.delete(p.code) : picked.add(p.code);
          b.classList.toggle("on", picked.has(p.code));
        } }, h("span", { class: "box" }, icon("check")), p.label);
        return b;
      }),
      note,
      h("div", { class: "row-actions" },
        h("button", { class: "btn t accent", style: "flex:1", onclick: () => send("wrong", note.value, [...picked]) }, "Send feedback"),
        h("button", { class: "btn ghost", onclick: () => { wrongForm.hidden = true; } }, "Cancel")));

    function showSaved(fb) {
      rightBtn.classList.toggle("on", fb?.agreement === "right");
      wrongBtn.classList.toggle("on", fb?.agreement === "wrong");
      status.className = "hint " + (fb ? (fb.agreement === "right" ? "note-ok" : "note-bad") : "");
      status.textContent = fb
        ? `You marked this: Clanker was ${fb.agreement}.${fb.note ? ` “${fb.note}”` : ""}`
        : "Your answer improves Clanker. A human still decides the ship.";
    }
    async function send(agreement, text = "", wrong = []) {
      try {
        const saved = await api.sendFeedback(rec.cert_id, { agreement, note: text, wrong_checks: wrong });
        rec.feedback = saved.feedback; showSaved(rec.feedback); wrongForm.hidden = true;
        toast(`Saved: Clanker was ${agreement}`, "ok");
        opts.onChanged?.(saved);
      } catch (e) { toast(`Could not save: ${e.message}`, "bad"); }
    }
    rightBtn.addEventListener("click", () => send("right"));
    wrongBtn.addEventListener("click", () => { wrongForm.hidden = !wrongForm.hidden; if (!wrongForm.hidden) note.focus(); });
    showSaved(rec.feedback);
    out.feedback = h("div", { class: "pc accent" },
      h("div", { class: "pc-head" }, h("span", { class: "lbl" }, "Was Clanker right?")),
      h("div", { class: "stack" }, rightBtn, wrongBtn), h("div", { style: "margin-top:8px" }, status), wrongForm);

    // PDF + re-request
    out.pdfButton = h("button", { class: "btn", title: rec.pdf_path ? "Open Clanker's review report" : "No PDF was generated for this review" }, icon("file"), "Review PDF");
    if (!rec.pdf_path) out.pdfButton.disabled = true;
    out.pdfButton.addEventListener("click", async () => {
      out.pdfButton.disabled = true;
      try { await openPdf(api, rec.cert_id); } catch (e) { toast(`Could not open the PDF: ${e.message}`, "bad"); }
      out.pdfButton.disabled = false;
    });
    const rerunStatus = h("span", { class: "hint" });
    out.rerunStatus = rerunStatus;
    out.rerunButton = h("button", { class: "btn" }, icon("refresh"), "Re-request review");
    out.rerunButton.addEventListener("click", async () => {
      const b = out.rerunButton;
      b.disabled = true; b.querySelector("svg").classList.add("spin");
      try {
        const done = await api.runReview(rec.cert_id, (t) => (rerunStatus.textContent = t));
        if (done.state === "failed") throw new Error(done.error || "review failed");
        toast("Fresh review ready", "ok");
        opts.onChanged?.(await api.getResult(rec.cert_id), true);
      } catch (e) {
        rerunStatus.textContent = "";
        toast(`Review failed: ${e.message}`, "bad");
        b.disabled = false; b.querySelector("svg").classList.remove("spin");
      }
    });
    out.right = () => rightBtn.click();
    out.wrong = () => wrongBtn.click();
    return out;
  }

  // Everything stacked in one column: the cert-page drawer.
  function detail(rec, opts) {
    const p = parts(rec, opts);
    const root = h("div", { class: "stack", style: "gap:12px" },
      p.banner, p.message, p.video, p.reasons, p.feedback,
      h("div", { class: "row-actions" }, p.pdfButton, p.rerunButton, p.rerunStatus));
    root.clankerRight = p.right; root.clankerWrong = p.wrong;
    return root;
  }

  globalThis.ClankerUI = { h, icon, svgFrom, verdictMeta, badge, statusText, timeAgo, reasonPairs, copyText, toastFactory, parts, detail };
})();
