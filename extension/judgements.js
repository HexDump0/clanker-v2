// Clanker judgements. A dashboard-style table of everything Clanker judged, and a detail view where a
// human confirms or overrules Clanker's call. The real verdict is still submitted by a human on the dashboard.
(() => {
  const { h, icon, badge, statusText, timeAgo, reasonPairs, toastFactory, parts, videoBlob } = ClankerUI;
  const SLUG = "stardance";
  const DASH = `https://ds.shipwrights.dev/${SLUG}/certifications/`;
  const drafts = new Map();   // edited feedback text per ship (survives re-renders)
  const dashInfo = new Map(); // last known dashboard status per ship
  const ID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
  const KEY = "clanker.page";

  const state = { results: [], loaded: false, error: null, view: "list", selected: null, cursor: null,
    verdict: "", queue: "queue", q: "", sort: "created", dir: -1 };
  try { Object.assign(state, JSON.parse(sessionStorage.getItem(KEY) || "{}"), { view: "list" }); } catch {}
  const save = () => { try { sessionStorage.setItem(KEY, JSON.stringify({ verdict: state.verdict, sort: state.sort, dir: state.dir })); } catch {} };

  const app = document.getElementById("app");
  const toast = toastFactory(document.body);
  const norm = (v) => (v === "FLAG_FOR_HUMAN" ? "NEEDS_HUMAN" : v);
  const ORDER = { REJECT: 0, NEEDS_HUMAN: 1, APPROVE: 2 };

  // ---------- derived ----------
  const matches = (r) => {
    if (state.verdict && norm(r.verdict) !== state.verdict) return false;
    // The Clanker queue is everything except ships a human said Clanker got wrong.
    if (state.queue === "queue" ? r.manual_review : !r.manual_review) return false;
    if (state.q) {
      const hay = [r.project_name, r.summary, ...reasonPairs(r).map((p) => p.label)].join(" ").toLowerCase();
      if (!hay.includes(state.q.toLowerCase())) return false;
    }
    return true;
  };
  const sortKey = (r) => state.sort === "project" ? r.project_name.toLowerCase()
    : state.sort === "verdict" ? ORDER[norm(r.verdict)] ?? 9 : r.created_at;
  const visible = () => state.results.filter(matches).sort((a, b) => {
    const x = sortKey(a), y = sortKey(b);
    return (x < y ? -1 : x > y ? 1 : 0) * state.dir;
  });
  const count = (fn) => state.results.filter(fn).length;
  const inQueue = (r) => !r.manual_review;
  const rec = () => state.results.find((r) => r.cert_id === state.selected);

  // ---------- top bar ----------
  function statBar() {
    const labelled = state.results.filter((r) => r.feedback);
    const right = labelled.filter((r) => r.feedback.agreement === "right").length;
    const queue = state.results.filter(inQueue);
    const pct = (n) => (queue.length ? `${Math.round((n / queue.length) * 100)}%` : "");
    const cell = (label, value, tone, extra, cls = "") => h("div", { class: `sb ${tone ? "c " + tone : ""} ${cls}` },
      h("span", { class: "lbl" }, label), h("span", { class: "v" }, String(value), extra && h("span", { class: "pct" }, extra)));
    const of = (v) => queue.filter((r) => norm(r.verdict) === v).length;
    return h("div", { class: "statbar" },
      cell("In queue", queue.length, null, null, "hero"),
      cell("Rejects", of("REJECT"), "bad", pct(of("REJECT"))),
      cell("Approves", of("APPROVE"), "ok", pct(of("APPROVE"))),
      cell("Needs human", of("NEEDS_HUMAN"), "warn"),
      cell("Got it wrong", count((r) => r.manual_review), "flag"),
      cell("Agreement", labelled.length ? `${Math.round((right / labelled.length) * 100)}%` : "–", null, labelled.length ? `${labelled.length} labelled` : ""));
  }

  function topBar() {
    return h("div", { class: "topbar" }, statBar(),
      h("div", { class: "actions" },
        h("button", { class: "btn t accent", onclick: openReviewDialog }, icon("plus"), "Review a ship"),
        h("button", { class: "btn", onclick: exportFeedback }, icon("download"), "Export labels"),
        h("button", { class: "btn icon", title: "Refresh", "aria-label": "Refresh", onclick: load }, icon("refresh")),
        h("button", { class: "btn icon", title: "Settings", "aria-label": "Settings", onclick: openSettings }, icon("settings"))));
  }

  // ---------- list view ----------
  function filterBtn(name, n, current, value, tone, set) {
    return h("button", { class: `fbtn ${tone || ""} ${current === value ? "on" : ""}`, onclick: () => set(value) },
      tone && h("span", { class: `dot ${tone}` }), name, n != null && h("span", { class: "n" }, String(n)));
  }

  function filters() {
    const queue = state.results.filter(inQueue);
    const v = (value, name, tone) => {
      const n = value ? queue.filter((r) => norm(r.verdict) === value).length : queue.length;
      const on = state.queue === "queue" && state.verdict === value;
      return h("button", { class: `fbtn ${tone || ""} ${on ? "on" : ""}`, onclick: () => { state.queue = "queue"; state.verdict = value; save(); render(); } },
        tone && h("span", { class: `dot ${tone}` }), name, h("span", { class: "n" }, String(n)));
    };
    const wrong = count((r) => r.manual_review);
    const search = h("input", { type: "search", placeholder: "Search ships and reasons…", value: state.q, "aria-label": "Search" });
    search.addEventListener("input", () => { state.q = search.value; renderTable(); });
    return h("div", { class: "filters" },
      h("div", { class: "frow" }, v("", "Clanker queue"), v("REJECT", "Reject", "bad"), v("APPROVE", "Approve", "ok"), v("NEEDS_HUMAN", "Needs human", "warn"),
        h("button", { class: `fbtn flag ${state.queue === "wrong" ? "on" : ""}`, title: "Ships a human marked wrong. They are off the Clanker queue.",
          onclick: () => { state.queue = state.queue === "wrong" ? "queue" : "wrong"; render(); } },
          h("span", { class: "dot flag" }), "Clanker got it wrong", h("span", { class: "n" }, String(wrong))),
        h("div", { class: "search" }, search)));
  }

  function th(label, key) {
    const on = state.sort === key;
    return h("button", { class: "th lbl" + (on ? " on" : ""), onclick: () => { if (on) state.dir *= -1; else { state.sort = key; state.dir = key === "created" ? -1 : 1; } save(); renderTable(); } },
      label, on && h("span", {}, state.dir === 1 ? "↑" : "↓"));
  }

  function row(r) {
    const pairs = reasonPairs(r);
    const why = pairs.length ? pairs[0].label + (pairs.length > 1 ? `, +${pairs.length - 1} more` : "") : (r.summary || "").split(". ")[0];
    const lab = r.feedback
      ? h("span", { class: r.feedback.agreement === "right" ? "note-ok" : "flag", style: r.feedback.agreement === "right" ? "" : "color:var(--c)" },
          r.feedback.agreement === "right" ? "✓ right" : "✗ wrong")
      : "—";
    return h("button", { class: "tr" + (r.cert_id === state.cursor ? " cur" : ""), "data-id": r.cert_id, onclick: () => open(r.cert_id) },
      h("span", { class: "td-name" }, r.project_name), statusText(r),
      h("span", { class: "td-why", title: why }, why), h("span", { class: "td-lab" }, lab),
      h("span", { class: "td-when", title: new Date(r.created_at).toLocaleString() }, timeAgo(r.created_at)));
  }

  function emptyBox(title, body, ...actions) {
    return h("div", { class: "empty" }, h("h3", {}, title), h("p", {}, body), actions.length ? h("div", { class: "row-actions" }, actions) : null);
  }

  function tableBox() {
    const box = h("div", { class: "table", id: "tablebox" });
    box.append(h("div", { class: "tr head" }, th("Project", "project"), th("Verdict", "verdict"), h("span", { class: "lbl" }, "Reason"), h("span", { class: "lbl" }, "Feedback"), th("Reviewed", "created")));
    if (!state.loaded) { box.append(...Array.from({ length: 7 }, () => h("div", { class: "skel" }))); return box; }
    if (state.error) {
      box.append(emptyBox("Can't reach the Clanker API", state.error,
        h("button", { class: "btn t accent", onclick: load }, "Retry"), h("button", { class: "btn", onclick: openSettings }, "API settings")));
      return box;
    }
    if (!state.results.length) {
      box.append(emptyBox("Nothing judged yet", "Ships show up here after Clanker reviews them. You can also ask for one now.",
        h("button", { class: "btn t accent", onclick: openReviewDialog }, "Review a ship")));
      return box;
    }
    const items = visible();
    if (!items.length) { box.append(emptyBox(state.queue === "wrong" ? "Nothing here" : state.q || state.verdict ? "No matches" : "The queue is empty", state.queue === "wrong" ? "No ships are marked as wrong." : "Nothing in this view.")); return box; }
    if (!items.some((r) => r.cert_id === state.cursor)) state.cursor = items[0].cert_id;
    box.append(...items.map(row), h("div", { class: "pager" }, h("span", {}, `${items.length} of ${state.results.length} ships`), h("span", {}, "j / k to move · Enter to open")));
    return box;
  }
  const renderTable = () => { const old = document.getElementById("tablebox"); if (old) old.replaceWith(tableBox()); };

  // ---------- reviewing from here ----------
  const STATUS_TONE = { PENDING: "warn", IN_REVIEW: "info", APPROVED: "ok", REJECTED: "bad", RETURNED: "flag" };

  function feedbackCard(r) {
    const manual = !!r.manual_review;
    const clanker = r.message || "";
    if (!drafts.has(r.cert_id)) drafts.set(r.cert_id, manual ? "" : clanker); // never prefill a message Clanker got wrong
    const text = h("textarea", { class: "fb-text", rows: "7", maxlength: "5000", spellcheck: "true",
      placeholder: "Feedback for the shipper (required to reject)" });
    text.value = drafts.get(r.cert_id);
    const count = h("span", { class: "hint" });
    const sync = () => { drafts.set(r.cert_id, text.value); count.textContent = `${text.value.length} / 5000`; };
    text.addEventListener("input", sync); sync();
    const reset = clanker && h("button", { class: "btn", title: "Put Clanker's message back", onclick: () => { text.value = clanker; sync(); text.focus(); } },
      manual ? "Insert Clanker's message" : "Reset to Clanker's");
    const copy = h("button", { class: "btn", onclick: async () => toast((await ClankerUI.copyText(text.value)) ? "Copied to clipboard" : "Could not copy", "ok") }, "Copy");
    const hint = manual ? "Clanker got this one wrong, so its message isn't filled in." : clanker ? "Filled in from Clanker. Edit it before you reject." : "Clanker didn't write a message for this one.";
    return { el: h("div", { class: "pc" }, h("div", { class: "pc-head" }, h("span", { class: "lbl" }, "Feedback"), h("div", { class: "row-actions" }, reset, copy)),
      text, h("div", { class: "pc-head", style: "margin:8px 0 0" }, h("span", { class: "hint" }, hint), count)), text };
  }

  function reviewCard(r, textarea) {
    const info = dashInfo.get(r.cert_id);
    const statusVal = h("span", { class: "v" }, "…");
    const kv = h("div", { class: "kv" }, h("span", { class: "k" }, "Dashboard status"), statusVal);
    // The video is part of the rejection: always attached, except when Clanker got this one wrong (its video shows the wrong reasons).
    const withVideo = !!r.video_path && !r.manual_review;
    const attachRow = h("div", { class: "kv" }, h("span", { class: "k" }, "Video"),
      h("span", { class: "v" }, withVideo ? "Clanker's video is attached" : r.video_path ? "Not attached (Clanker was wrong)" : "None for this ship"));
    const note = h("div", { class: "hint", style: "margin-top:8px" });
    const btn = h("button", { class: "btn t bad block" }, "Reject the project");

    const apply = (i) => {
      const done = i && (i.status === "APPROVED" || i.status === "REJECTED");
      const other = i && i.status === "IN_REVIEW" && !i.viewerIsClaimer && !i.viewerIsGlobalAdmin;
      statusVal.replaceChildren(i ? h("span", { class: `st ${STATUS_TONE[i.status] || "neutral"}` }, i.status.toLowerCase().replace("_", " ")) : "–");
      btn.disabled = !ClankerBridge.available || done || other;
      note.textContent = !ClankerBridge.available ? "Open Clanker from the dashboard sidebar to review from here."
        : done ? `Already ${i.status.toLowerCase()} on the dashboard.`
        : other ? `Claimed by ${i.claimer?.name || i.claimer?.username || "someone else"}.`
        : "Uses your dashboard account. A human always submits the review.";
    };
    apply(info);
    if (ClankerBridge.available) {
      ClankerBridge.status(SLUG, r.cert_id).then((i) => { dashInfo.set(r.cert_id, i); apply(i); })
        .catch((e) => { statusVal.textContent = "–"; note.textContent = `Couldn't read the dashboard: ${e.message}`; });
    } else apply(null);

    btn.addEventListener("click", () => confirmReject(r, textarea.value, withVideo));
    return h("div", { class: "pc accent" }, h("div", { class: "pc-head" }, h("span", { class: "lbl" }, "Review")), kv, attachRow, h("div", { style: "margin-top:10px" }, btn), note);
  }

  function confirmReject(r, comment, withVideo) {
    comment = comment.trim();
    if (!comment) return toast("Write some feedback for the shipper first.", "bad");
    const status = h("div", { class: "hint" });
    const go = h("button", { class: "btn t bad" }, "Reject project");
    const cancel = h("button", { class: "btn ghost", onclick: () => d.close() }, "Cancel");
    const d = dialog([
      h("h3", {}, `Reject ${r.project_name}?`),
      h("div", { class: "help" }, `This submits a REJECTED review on the dashboard as you. It will claim the ship if it isn't claimed${withVideo ? ", attach Clanker's video" : ""} and send this feedback to the shipper:`),
      h("pre", { class: "msg", style: "max-height:180px" }, comment),
      status, h("div", { class: "row-actions" }, cancel, go)]);
    go.addEventListener("click", async () => {
      go.disabled = cancel.disabled = true;
      try {
        let video = null;
        if (withVideo) { status.textContent = "Loading the video…"; video = await videoBlob(ClankerApi, r.cert_id); }
        await ClankerBridge.reject({ slug: SLUG, id: r.cert_id, comment, video }, (t) => (status.textContent = t));
        dashInfo.set(r.cert_id, { status: "REJECTED" });
        drafts.delete(r.cert_id);
        // Rejecting after Clanker also said reject is agreement: label it right (never overwrite an existing label).
        let labelled = false;
        if (norm(r.verdict) === "REJECT" && !r.feedback) {
          try {
            const saved = await ClankerApi.sendFeedback(r.cert_id, { agreement: "right", note: "", wrong_checks: [] });
            const i = state.results.findIndex((x) => x.cert_id === r.cert_id);
            if (i >= 0) state.results[i] = saved;
            labelled = true;
          } catch { /* the rejection itself already succeeded; the label is just a bonus */ }
        }
        d.close(); toast(`Rejected ${r.project_name}${labelled ? " and marked Clanker right" : ""}`, "ok"); render(true);
      } catch (e) {
        status.textContent = e.message; status.className = "hint note-bad"; go.disabled = cancel.disabled = false;
      }
    });
  }

  // ---------- detail view ----------
  function detailView(r) {
    const items = visible();
    const idx = items.findIndex((x) => x.cert_id === r.cert_id);
    const p = parts(r, {
      api: ClankerApi, toast,
      onChanged(updated, isRerun) {
        const before = visible().findIndex((x) => x.cert_id === updated.cert_id);
        const i = state.results.findIndex((x) => x.cert_id === updated.cert_id);
        if (i >= 0) state.results[i] = updated; else state.results.unshift(updated);
        const now = visible();
        if (!isRerun && !now.some((x) => x.cert_id === updated.cert_id)) {
          // Labelled out of the current filter: move on to the next ship in the queue.
          const next = now[Math.min(Math.max(before, 0), now.length - 1)];
          if (next) state.selected = next.cert_id; else { state.view = "list"; state.cursor = null; }
        }
        render();
      },
    });
    const link = (href, label, tone) => href && h("a", { class: `btn ${tone ? "t " + tone : ""}`, href, target: "_blank", rel: "noopener" }, label, icon("external"));
    const nav = h("span", { class: "pager-nav" },
      h("button", { class: "btn ghost icon", title: "Previous (k)", disabled: idx <= 0 ? "" : null, onclick: () => step(-1) }, "‹"),
      idx >= 0 ? `${idx + 1} / ${items.length}` : "",
      h("button", { class: "btn ghost icon", title: "Next (j)", disabled: idx < 0 || idx >= items.length - 1 ? "" : null, onclick: () => step(1) }, "›"));
    const head = h("div", { class: "crumb" },
      h("button", { class: "btn ghost", onclick: back }, icon("back"), "Back"), h("span", { class: "sep" }, "/"),
      h("h2", {}, r.project_name), badge(r),
      h("div", { class: "right" }, nav, link(r.demo_url, "Demo"), link(r.repo_url, "Repo"), link(r.stardance_url, "Project", "info"), link(DASH + r.cert_id, "Open ship", "accent")));

    p.pdfButton.classList.add("block"); p.rerunButton.classList.add("block");
    p.info.append(h("div", { class: "divider" }), p.pdfButton, p.rerunButton, h("div", { class: "hint", style: "margin-top:6px" }, p.rerunStatus));
    const fb = feedbackCard(r);
    const left = [fb.el, p.video], right = [reviewCard(r, fb.text), p.feedback, p.info];
    if (p.reasons) right.push(p.reasons);
    const view = h("div", { class: "stack", style: "gap:16px" }, head, p.banner,
      h("div", { class: "dgrid" }, h("div", { class: "dcol" }, left), h("div", { class: "dcol" }, right)));
    view.clankerRight = p.right; view.clankerWrong = p.wrong;
    return view;
  }

  let detail = null;
  function render() {
    detail = null;
    const nodes = [topBar()];
    if (state.view === "detail" && rec()) { detail = detailView(rec()); nodes.push(detail); }
    else { state.view = "list"; nodes.push(filters(), tableBox()); }
    const y = scrollY; app.replaceChildren(...nodes); scrollTo(0, y);
  }

  function open(id) { state.selected = state.cursor = id; state.view = "detail"; scrollTo(0, 0); render(); }
  function back() { state.view = "list"; state.cursor = state.selected; render(); }
  function step(d) {
    const items = visible(); const i = items.findIndex((x) => x.cert_id === state.selected);
    const next = items[i + d]; if (next) { state.selected = state.cursor = next.cert_id; scrollTo(0, 0); render(); }
  }

  // ---------- dialogs ----------
  function dialog(content) {
    const d = h("dialog", {}, h("div", { class: "dlg cl" }, content));
    d.addEventListener("close", () => d.remove());
    d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
    document.body.append(d); d.showModal();
    return d;
  }
  async function openSettings() {
    const input = h("input", { type: "text", value: await ClankerApi.getBase(), spellcheck: "false" });
    const result = h("div", { class: "hint" });
    const d = dialog([
      h("h3", {}, "Clanker API"),
      h("div", { class: "help" }, "Where the extension finds Clanker. Local default is http://127.0.0.1:8765. Use your https URL once it's hosted."),
      input, result,
      h("div", { class: "row-actions" },
        h("button", { class: "btn ghost", onclick: () => d.close() }, "Cancel"),
        h("button", { class: "btn", onclick: async () => {
          result.textContent = "Testing…"; result.className = "hint";
          try { await ClankerApi.setBase(input.value); const r = await ClankerApi.listResults(); result.textContent = `Connected. ${r.length} judged ships.`; result.className = "hint note-ok"; }
          catch (e) { result.textContent = e.message; result.className = "hint note-bad"; }
        } }, "Test"),
        h("button", { class: "btn t accent", onclick: async () => { await ClankerApi.setBase(input.value); d.close(); load(); } }, "Save"))]);
    input.select();
  }
  function openReviewDialog() {
    const input = h("input", { type: "text", placeholder: "Ship link or ID", spellcheck: "false" });
    const status = h("div", { class: "hint" });
    const go = h("button", { class: "btn t accent" }, "Request review");
    const d = dialog([
      h("h3", {}, "Review a ship"),
      h("div", { class: "help" }, "Paste the dashboard link or the ID. Clanker reviews it now and posts to Slack. Takes about a minute."),
      input, status,
      h("div", { class: "row-actions" }, h("button", { class: "btn ghost", onclick: () => d.close() }, "Cancel"), go)]);
    const submit = async () => {
      const id = (input.value.match(ID_RE) || [input.value.trim()])[0];
      if (!/^[A-Za-z0-9_-]+$/.test(id)) { status.textContent = "That doesn't look like a ship link or ID."; status.className = "hint note-bad"; return; }
      go.disabled = input.disabled = true; status.className = "hint";
      try {
        const done = await ClankerApi.runReview(id, (t) => (status.textContent = t));
        if (done.state === "failed") throw new Error(done.error || "review failed");
        d.close(); state.verdict = ""; state.queue = "queue"; state.q = "";
        await load(); open(id); toast("Review ready", "ok");
      } catch (e) { status.textContent = e.message; status.className = "hint note-bad"; go.disabled = input.disabled = false; }
    };
    go.addEventListener("click", submit);
    input.addEventListener("keydown", (e) => e.key === "Enter" && submit());
    input.focus();
  }
  async function exportFeedback() {
    try {
      const res = await ClankerApi.exportFeedback();
      h("a", { href: URL.createObjectURL(await res.blob()), download: "clanker-feedback.jsonl" }).click();
      toast("Exported your labels", "ok");
    } catch (e) { toast(`Export failed: ${e.message}`, "bad"); }
  }

  // ---------- data ----------
  async function load() {
    state.error = null; state.loaded = false; render();
    try { state.results = await ClankerApi.listResults(); }
    catch (e) { state.results = []; state.error = `${e.message} (${await ClankerApi.getBase()})`; }
    state.loaded = true; render();
  }

  // ---------- keyboard ----------
  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || document.querySelector("dialog[open]")) return;
    if (state.view === "detail") {
      if (e.key === "j" || e.key === "ArrowRight") step(1);
      else if (e.key === "k" || e.key === "ArrowLeft") step(-1);
      else if (e.key === "Escape" || e.key === "Backspace") back();
      else if (e.key === "r") detail?.clankerRight?.();
      else if (e.key === "w") detail?.clankerWrong?.();
      return;
    }
    const items = visible(); const i = items.findIndex((r) => r.cert_id === state.cursor);
    const move = (d) => { const n = items[Math.max(0, Math.min(items.length - 1, i + d))]; if (n) { state.cursor = n.cert_id; renderTable(); document.querySelector(".tr.cur")?.scrollIntoView({ block: "nearest" }); } };
    if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter" && state.cursor) open(state.cursor);
  });

  render(); load();
})();
