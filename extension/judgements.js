// Clanker judgements. A dashboard-style table of everything Clanker judged, and a detail view where a
// human confirms or overrules Clanker's call. The real verdict is still submitted by a human on the dashboard.
(() => {
  const { h, icon, verdictMeta, badge, statusText, timeAgo, reasonPairs, toastFactory, parts } = ClankerUI;
  const DASH = "https://ds.shipwrights.dev/stardance/certifications/";
  const ID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
  const KEY = "clanker.page";

  const state = { results: [], loaded: false, error: null, view: "list", selected: null, cursor: null,
    verdict: "", label: "todo", q: "", sort: "created", dir: -1 };
  try { Object.assign(state, JSON.parse(sessionStorage.getItem(KEY) || "{}"), { view: "list" }); } catch {}
  const save = () => { try { sessionStorage.setItem(KEY, JSON.stringify({ verdict: state.verdict, label: state.label, sort: state.sort, dir: state.dir })); } catch {} };

  const app = document.getElementById("app");
  const toast = toastFactory(document.body);
  const norm = (v) => (v === "FLAG_FOR_HUMAN" ? "NEEDS_HUMAN" : v);
  const ORDER = { REJECT: 0, NEEDS_HUMAN: 1, APPROVE: 2 };

  // ---------- derived ----------
  const matches = (r) => {
    if (state.verdict && norm(r.verdict) !== state.verdict) return false;
    if (state.label === "todo" && r.feedback) return false;
    if (state.label === "right" && r.feedback?.agreement !== "right") return false;
    if (state.label === "wrong" && r.feedback?.agreement !== "wrong") return false;
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
  const rec = () => state.results.find((r) => r.cert_id === state.selected);

  // ---------- top bar ----------
  function statBar() {
    const labelled = state.results.filter((r) => r.feedback);
    const right = labelled.filter((r) => r.feedback.agreement === "right").length;
    const total = state.results.length;
    const pct = (n) => (total ? `${Math.round((n / total) * 100)}%` : "");
    const cell = (label, value, tone, extra, cls = "") => h("div", { class: `sb ${tone ? "c " + tone : ""} ${cls}` },
      h("span", { class: "lbl" }, label), h("span", { class: "v" }, String(value), extra && h("span", { class: "pct" }, extra)));
    const rejects = count((r) => norm(r.verdict) === "REJECT"), approves = count((r) => norm(r.verdict) === "APPROVE");
    return h("div", { class: "statbar" },
      cell("To review", count((r) => !r.feedback), null, null, "hero"),
      cell("Judged", total),
      cell("Rejects", rejects, "bad", pct(rejects)),
      cell("Approves", approves, "ok", pct(approves)),
      cell("Needs human", count((r) => norm(r.verdict) === "NEEDS_HUMAN"), "warn"),
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
    const v = (value, name, tone) => filterBtn(name, value ? count((r) => norm(r.verdict) === value) : state.results.length, state.verdict, value, tone, (x) => { state.verdict = x; save(); render(); });
    const l = (value, name, n, tone) => filterBtn(name, n, state.label, value, tone, (x) => { state.label = x; save(); render(); });
    const search = h("input", { type: "search", placeholder: "Search ships and reasons…", value: state.q, "aria-label": "Search" });
    search.addEventListener("input", () => { state.q = search.value; renderTable(); });
    return h("div", { class: "filters" },
      h("div", { class: "frow" }, v("", "All"), v("REJECT", "Reject", "bad"), v("APPROVE", "Approve", "ok"), v("NEEDS_HUMAN", "Needs human", "warn")),
      h("div", { class: "frow" },
        l("todo", "To review", count((r) => !r.feedback), "accent"), l("wrong", "Marked wrong", count((r) => r.feedback?.agreement === "wrong"), "bad"),
        l("right", "Marked right", count((r) => r.feedback?.agreement === "right"), "ok"), l("all", "Everything", state.results.length),
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
      ? h("span", { class: r.feedback.agreement === "right" ? "note-ok" : "note-bad" }, r.feedback.agreement === "right" ? "✓ right" : "✗ wrong")
      : "—";
    return h("button", { class: "tr" + (r.cert_id === state.cursor ? " cur" : ""), "data-id": r.cert_id, onclick: () => open(r.cert_id) },
      h("span", { class: "td-name" }, r.project_name), statusText(r.verdict),
      h("span", { class: "td-why", title: why }, why), h("span", { class: "td-lab" }, lab),
      h("span", { class: "td-when", title: new Date(r.created_at).toLocaleString() }, timeAgo(r.created_at)));
  }

  function emptyBox(title, body, ...actions) {
    return h("div", { class: "empty" }, h("h3", {}, title), h("p", {}, body), actions.length ? h("div", { class: "row-actions" }, actions) : null);
  }

  function tableBox() {
    const box = h("div", { class: "table", id: "tablebox" });
    box.append(h("div", { class: "tr head" }, th("Project", "project"), th("Verdict", "verdict"), h("span", { class: "lbl" }, "Reason"), h("span", { class: "lbl" }, "Your label"), th("Reviewed", "created")));
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
    if (!items.length) { box.append(emptyBox(state.label === "todo" && !state.q ? "All caught up" : "No matches", "Nothing left in this view.")); return box; }
    if (!items.some((r) => r.cert_id === state.cursor)) state.cursor = items[0].cert_id;
    box.append(...items.map(row), h("div", { class: "pager" }, h("span", {}, `${items.length} of ${state.results.length} ships`), h("span", {}, "j / k to move · Enter to open")));
    return box;
  }
  const renderTable = () => { const old = document.getElementById("tablebox"); if (old) old.replaceWith(tableBox()); };

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
      h("h2", {}, r.project_name), badge(r.verdict),
      h("div", { class: "right" }, nav, link(r.demo_url, "Demo"), link(r.repo_url, "Repo"), link(r.stardance_url, "Project", "info"), link(DASH + r.cert_id, "Open ship", "accent")));

    p.pdfButton.classList.add("block"); p.rerunButton.classList.add("block");
    p.info.append(h("div", { class: "divider" }), p.pdfButton, p.rerunButton, h("div", { class: "hint", style: "margin-top:6px" }, p.rerunStatus));
    const left = [p.message, p.video], right = [p.info];
    if (p.reasons) (left.some(Boolean) ? right : left).push(p.reasons);
    right.push(p.feedback);
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
        d.close(); state.verdict = ""; state.label = "all"; state.q = "";
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
