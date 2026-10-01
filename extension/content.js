// The Clanker panel on a Shipwrights certification page: a floating button that opens a drawer
// with Clanker's judgement, the shipper message and video, "use" buttons that fill the review
// into the dashboard, feedback, and re-request. Everything is built with textContent (never
// innerHTML) because the data comes from the Clanker API.
(() => {
  const ext = globalThis.browser ?? globalThis.chrome;
  const { h, icon, badge, timeAgo, toastFactory, detail } = ClankerUI;
  const COMMENT_BOX = 'textarea[placeholder^="Write feedback for the submitter"]';

  let host = null;
  let currentId = null;
  let drawerOpen = false;
  let closeDrawer = null;

  const certFromUrl = () => {
    const m = location.pathname.match(/^\/([^/]+)\/certifications\/([0-9a-f-]{8,})/i);
    return m ? { slug: m[1], id: m[2] } : null;
  };

  // The dashboard's comment box is a React-controlled textarea.
  function fillCommentBox(text) {
    const box =
      document.querySelector(COMMENT_BOX) ||
      [...document.querySelectorAll("textarea")].find((t) => t.offsetParent !== null);
    if (!box) return false;
    box.focus();
    box.select();
    // execCommand fires real input events, which React's onChange listens for.
    let ok = false;
    try { ok = document.execCommand("insertText", false, text) && box.value === text; } catch {}
    if (!ok) {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
      setter.call(box, text);
      box.dispatchEvent(new Event("input", { bubbles: true }));
    }
    return true;
  }

  // The same three steps the dashboard's own upload button performs, with the user's own session.
  async function uploadVideo(slug, id, blob) {
    const file = new File([blob], `${id}.mp4`, { type: "video/mp4" });
    const base = `/api/v1/workplaces/${slug}/certifications/${id}/upload`;
    const q = new URLSearchParams({ filename: file.name, contentType: "video/mp4", size: String(file.size) });
    const presign = await fetch(`${base}?${q}`);
    if (!presign.ok) throw new Error((await presign.json()).error ?? "could not start upload");
    const { uploadUrl, publicUrl } = await presign.json();
    const put = await fetch(uploadUrl, { method: "PUT", headers: { "Content-Type": "video/mp4" }, body: file });
    if (!put.ok) throw new Error(`upload failed: ${put.status}`);
    const attach = await fetch(base, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: publicUrl }),
    });
    if (!attach.ok) throw new Error((await attach.json()).error ?? "could not attach video");
  }

  const stylesheet = (file) => h("link", { rel: "stylesheet", href: ext.runtime.getURL(file) });
  // Resolves when the stylesheet loads, fails, or after a short wait (never block the panel on it).
  const loaded = (link) =>
    new Promise((r) => {
      link.onload = link.onerror = r;
      setTimeout(r, 1500);
    });

  async function render(slug, id) {
    const el = h("div", { "data-clanker-panel": "1" });
    const root = el.attachShadow({ mode: "open" });
    const sheets = [stylesheet("ui.css"), stylesheet("panel.css")];
    root.append(...sheets);
    const ui = h("div", { class: "cl" });
    root.append(ui);
    const toast = toastFactory(ui);

    let record = null;
    let error = null;
    try { record = await ClankerApi.getResult(id); } catch (e) { error = e.message; }
    if (currentId !== id) return; // navigated away while loading

    const rerender = () => render(slug, id);

    const close = () => { drawerOpen = false; draw(); };
    closeDrawer = close;
    const fab = h("button", { class: "fab", onclick: () => { drawerOpen = true; draw(); }, "aria-label": "Open Clanker" },
      h("span", { class: "lbl" }, "Clanker"), record ? badge(record.verdict) : h("span", { class: "hint" }, "not reviewed"));

    function body() {
      if (error) {
        return h("div", { class: "empty" },
          h("h3", {}, "Can't reach Clanker"), h("p", {}, error),
          h("div", { class: "row-actions" }, h("button", { class: "btn t accent", onclick: rerender }, "Retry")),
          h("p", { class: "hint", style: "margin-top:12px" }, "Check the API URL under Settings on the Clanker page."));
      }
      if (!record) {
        const status = h("div", { class: "hint", style: "margin-top:10px" });
        const ask = h("button", { class: "btn t accent" }, icon("refresh"), "Request Clanker review");
        ask.addEventListener("click", async () => {
          ask.disabled = true;
          ask.querySelector("svg").classList.add("spin");
          try {
            const done = await ClankerApi.runReview(id, (t) => (status.textContent = t));
            if (done.state === "failed") throw new Error(done.error || "review failed");
            rerender();
          } catch (e) {
            status.textContent = `Review failed: ${e.message}`;
            status.className = "hint note-bad";
            ask.disabled = false;
            ask.querySelector("svg").classList.remove("spin");
          }
        });
        return h("div", { class: "empty" },
          h("h3", {}, "Clanker hasn't looked at this ship"),
          h("p", {}, "Ask for a first-pass review. It takes about a minute and posts to Slack."),
          h("div", { class: "row-actions" }, ask), status);
      }
      return detail(record, {
        api: ClankerApi,
        toast,
        useReason: fillCommentBox,
        async useVideo(blob) {
          toast("Uploading video…");
          await uploadVideo(slug, id, blob);
          toast("Video attached. Reloading…", "ok");
          setTimeout(() => location.reload(), 1200);
        },
        onChanged: rerender,
      });
    }

    function draw() {
      ui.querySelectorAll(".fab, .drawer").forEach((n) => n.remove());
      if (!drawerOpen) return ui.append(fab);
      const title = record ? record.project_name : "Clanker";
      ui.append(h("div", { class: "drawer", role: "dialog", "aria-label": "Clanker" },
        h("div", { class: "drawer-head" },
          h("div", { class: "titles" }, h("div", { class: "lbl" }, "Clanker"), h("h2", {}, title)),
          record ? badge(record.verdict) : null,
          h("button", { class: "btn ghost icon", "aria-label": "Close", onclick: close }, icon("x"))),
        h("div", { class: "drawer-body" }, body())));
    }

    draw();
    await Promise.all(sheets.map(loaded)); // avoid a flash of unstyled content
    if (currentId !== id) return;
    host?.remove();
    host = el;
    document.body.append(el);
  }

  // The dashboard is a single-page app, so watch for client-side navigation.
  function sync() {
    const page = certFromUrl();
    const id = page ? page.id : null;
    if (id === currentId) return;
    currentId = id;
    drawerOpen = false;
    host?.remove();
    host = null;
    if (!page) return;
    render(page.slug, page.id);
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drawerOpen) closeDrawer?.();
  });
  sync();
  setInterval(sync, 400);
})();
