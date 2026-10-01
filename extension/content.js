// Adds a "Clanker" panel to a Shipwrights certification page. Everything is built with
// textContent (never innerHTML) because the data comes from the Clanker API.
(() => {
  const VERDICT = {
    REJECT: { label: "REJECT", color: "#ef4444" },
    APPROVE: { label: "APPROVE", color: "#22c55e" },
    NEEDS_HUMAN: { label: "NEEDS HUMAN", color: "#f59e0b" },
    FLAG_FOR_HUMAN: { label: "NEEDS HUMAN", color: "#f59e0b" },
  };
  const COMMENT_BOX = 'textarea[placeholder^="Write feedback for the submitter"]';

  const h = (tag, props = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid != null) el.append(kid);
    return el;
  };

  const CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: system-ui, sans-serif; }
    .tab { position: fixed; right: 0; top: 40%; z-index: 2147483646; cursor: pointer;
      background: #18181b; color: #fafafa; border: 1px solid #3f3f46; border-right: 0;
      border-radius: 8px 0 0 8px; padding: 10px 8px; writing-mode: vertical-rl; font-size: 13px; }
    .tab i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-bottom: 6px; }
    .panel { position: fixed; right: 0; top: 0; bottom: 0; width: 380px; max-width: 100vw;
      z-index: 2147483647; background: #18181b; color: #e4e4e7; border-left: 1px solid #3f3f46;
      padding: 16px; overflow-y: auto; font-size: 13px; line-height: 1.45; }
    .panel[hidden] { display: none; }
    h2 { margin: 0 0 4px; font-size: 15px; } h3 { margin: 14px 0 6px; font-size: 12px;
      text-transform: uppercase; letter-spacing: .05em; color: #a1a1aa; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; color: #fff;
      font-weight: 600; font-size: 12px; }
    ul { margin: 0; padding-left: 18px; } pre { white-space: pre-wrap; background: #09090b;
      border: 1px solid #3f3f46; border-radius: 6px; padding: 8px; margin: 0; font: 12px ui-monospace, monospace; }
    video { width: 100%; border-radius: 6px; background: #000; }
    .row { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
    button { cursor: pointer; border: 1px solid #52525b; background: #27272a; color: #fafafa;
      border-radius: 6px; padding: 7px 10px; font-size: 13px; }
    button:hover:not(:disabled) { background: #3f3f46; } button:disabled { opacity: .45; cursor: default; }
    button.primary { background: #2563eb; border-color: #2563eb; }
    textarea { width: 100%; background: #09090b; color: inherit; border: 1px solid #3f3f46;
      border-radius: 6px; padding: 6px; font: inherit; } label { display: block; margin: 2px 0; }
    .status { margin-top: 10px; color: #a1a1aa; min-height: 1.4em; } .muted { color: #a1a1aa; }
    .close { float: right; }
  `;

  let host = null;
  let currentId = null;

  const certIdFromUrl = () => {
    const m = location.pathname.match(/^\/([^/]+)\/certifications\/([0-9a-f-]{8,})/i);
    return m ? { slug: m[1], id: m[2] } : null;
  };

  function fillCommentBox(text) {
    const box =
      document.querySelector(COMMENT_BOX) ||
      [...document.querySelectorAll("textarea")].find((t) => t.offsetParent !== null);
    if (!box) return false;
    box.focus();
    box.select();
    // execCommand fires real input events, which the dashboard's React form listens for.
    let ok = false;
    try {
      ok = document.execCommand("insertText", false, text) && box.value === text;
    } catch {}
    if (!ok) {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
      setter.call(box, text);
      box.dispatchEvent(new Event("input", { bubbles: true }));
    }
    return true;
  }

  // Same three steps the dashboard's own upload button performs, with the user's own session.
  async function uploadVideo(slug, id, blob, setStatus) {
    const file = new File([blob], `${id}.mp4`, { type: "video/mp4" });
    const base = `/api/v1/workplaces/${slug}/certifications/${id}/upload`;
    setStatus("Uploading video…");
    const q = new URLSearchParams({
      filename: file.name,
      contentType: "video/mp4",
      size: String(file.size),
    });
    const presign = await fetch(`${base}?${q}`);
    if (!presign.ok) throw new Error((await presign.json()).error ?? "could not start upload");
    const { uploadUrl, publicUrl } = await presign.json();
    const put = await fetch(uploadUrl, {
      method: "PUT",
      headers: { "Content-Type": "video/mp4" },
      body: file,
    });
    if (!put.ok) throw new Error(`upload failed: ${put.status}`);
    const attach = await fetch(base, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: publicUrl }),
    });
    if (!attach.ok) throw new Error((await attach.json()).error ?? "could not attach video");
  }

  function reasonText(r) {
    return r.message || [r.summary, ...r.reasons.map((x) => `- ${x}`)].filter(Boolean).join("\n");
  }

  async function render(slug, id) {
    host?.remove();
    host = h("div");
    const root = host.attachShadow({ mode: "open" });
    root.append(h("style", {}, CSS));
    const status = h("div", { class: "status" });
    const setStatus = (t) => (status.textContent = t);

    let record = null;
    let error = null;
    try {
      record = await ClankerApi.getResult(id);
    } catch (e) {
      error = e.message;
    }
    if (!record && !error) return; // Clanker hasn't judged this one: stay out of the way.

    const v = record ? VERDICT[record.verdict] || { label: record.verdict, color: "#71717a" } : null;
    const panel = h("div", { class: "panel", hidden: "" });
    const tab = h(
      "div",
      { class: "tab", onclick: () => (panel.hidden = !panel.hidden) },
      h("i", { style: `background:${v ? v.color : "#71717a"}` }),
      document.createElement("br"),
      "Clanker",
    );
    root.append(tab, panel);
    panel.append(h("button", { class: "close", onclick: () => (panel.hidden = true) }, "✕"));

    if (error) {
      panel.append(h("h2", {}, "Clanker"), h("p", { class: "muted" }, error));
      document.body.append(host);
      return;
    }

    panel.append(
      h("h2", {}, record.project_name),
      h("span", { class: "badge", style: `background:${v.color}` }, v.label),
      h("p", {}, record.summary),
    );
    if (record.reasons.length) {
      panel.append(h("h3", {}, "Reasons"), h("ul", {}, record.reasons.map((r) => h("li", {}, r))));
    }
    if (record.message) panel.append(h("h3", {}, "Message for the shipper"), h("pre", {}, record.message));

    const video = h("video", { controls: "", preload: "none" });
    let blobPromise = null;
    const getBlob = () => (blobPromise ??= ClankerApi.videoBlob(id));
    if (record.video_path) {
      panel.append(h("h3", {}, "Video"), video);
      getBlob().then((b) => b && (video.src = URL.createObjectURL(b))).catch(() => {});
    }

    const useReason = h(
      "button",
      {
        class: "primary",
        onclick: () => {
          const ok = fillCommentBox(reasonText(record));
          if (ok) return setStatus("Filled the review comment. Read it, then submit yourself.");
          navigator.clipboard?.writeText(reasonText(record));
          setStatus("No comment box here (claim the ship first). Copied to clipboard instead.");
        },
      },
      "Use reason",
    );
    const useVideo = h(
      "button",
      {
        class: "primary",
        onclick: async () => {
          useVideo.disabled = true;
          try {
            const blob = await getBlob();
            if (!blob) throw new Error("no video file");
            await uploadVideo(slug, id, blob, setStatus);
            setStatus("Video attached. Reloading…");
            setTimeout(() => location.reload(), 1200);
          } catch (e) {
            setStatus(`Video upload failed: ${e.message}`);
            useVideo.disabled = false;
          }
        },
      },
      "Use video",
    );
    if (!record.video_path) useVideo.disabled = true;
    panel.append(h("div", { class: "row" }, useReason, useVideo));

    // Feedback: was Clanker right? "Wrong" asks which checks and why.
    panel.append(h("h3", {}, "Was Clanker right?"));
    const note = h("textarea", { rows: "3", placeholder: "What did Clanker get wrong?" });
    const checks = record.reasons.map((r) => {
      const box = h("input", { type: "checkbox", value: r });
      return { box, el: h("label", {}, box, " " + r) };
    });
    const wrongForm = h(
      "div",
      { hidden: "" },
      h("p", { class: "muted" }, "Which reasons were wrong?"),
      checks.map((c) => c.el),
      note,
      h(
        "div",
        { class: "row" },
        h(
          "button",
          { onclick: () => send("wrong", note.value, checks.filter((c) => c.box.checked).map((c) => c.box.value)) },
          "Send feedback",
        ),
      ),
    );
    async function send(agreement, text = "", wrong = []) {
      try {
        await ClankerApi.sendFeedback(id, { agreement, note: text, wrong_checks: wrong });
        setStatus(`Saved: Clanker was ${agreement}.`);
        wrongForm.hidden = true;
      } catch (e) {
        setStatus(`Could not save feedback: ${e.message}`);
      }
    }
    panel.append(
      h(
        "div",
        { class: "row" },
        h("button", { onclick: () => send("right") }, "Clanker was right"),
        h("button", { onclick: () => (wrongForm.hidden = !wrongForm.hidden) }, "Clanker was wrong"),
      ),
      wrongForm,
    );
    if (record.feedback) {
      setStatus(`You marked this: Clanker was ${record.feedback.agreement}.`);
    }
    panel.append(status);
    document.body.append(host);
  }

  // The dashboard is a single-page app, so watch for client-side navigation.
  function sync() {
    const page = certIdFromUrl();
    const id = page ? page.id : null;
    if (id === currentId) return;
    currentId = id;
    if (!page) {
      host?.remove();
      host = null;
      return;
    }
    render(page.slug, page.id);
  }
  sync();
  setInterval(sync, 1000);
})();
