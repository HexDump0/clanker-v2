// Clanker judgements: triage everything Clanker judged. A human confirms or overrules Clanker's
// call here; the real verdict is still submitted by a human on the dashboard.
(() => {
  const { h, icon, verdictMeta, verdictPill, timeAgo, reasonPairs, toastFactory, detail } = ClankerUI;
  const DASH = "https://ds.shipwrights.dev/stardance/certifications/";
  const ID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
  const SEL_KEY = "clanker.selected";

  const state = { results: [], loaded: false, error: null, verdict: "", label: "todo", q: "", selected: null, detailMode: false };
  const app = document.getElementById("app");
  const toast = toastFactory(document.body);
  const nvh = (v) => (v === "FLAG_FOR_HUMAN" ? "NEEDS_HUMAN" : v);

  // ---------- derived data ----------
  const matches = (r) => {
    if (state.verdict && nvh(r.verdict) !== state.verdict) return false;
    if (state.label === "todo" && r.feedback) return false;
    if (state.label === "right" && r.feedback?.agreement !== "right") return false;
    if (state.label === "wrong" && r.feedback?.agreement !== "wrong") return false;
    if (state.q) {
      const hay = [r.project_name, r.summary, ...reasonPairs(r).map((p) => p.label)].join(" ").toLowerCase();
      if (!hay.includes(state.q.toLowerCase())) return false;
    }
    return true;
  };
  const visible = () => state.results.filter(matches);
  const count = (fn) => state.results.filter(fn).length;

  // ---------- pieces ----------
  function statTile(value, label, tone, sub) {
    return h("div", { class: "stat" },
      h("div", { class: "v" }, String(value)),
      h("div", { class: "k" }, tone && h("span", { class: `dot ${tone}` }), label),
      sub && h("div", { class: "sub" }, sub));
  }

  function stats() {
    const labelled = state.results.filter((r) => r.feedback);
    const right = labelled.filter((r) => r.feedback.agreement === "right").length;
    const agree = labelled.length ? `${Math.round((right / labelled.length) * 100)}%` : "–";
    return h("div", { class: "stats" },
      statTile(state.results.length, "Judged"),
      statTile(count((r) => nvh(r.verdict) === "REJECT"), "Rejects", "bad"),
      statTile(count((r) => nvh(r.verdict) === "APPROVE"), "Approves", "ok"),
      statTile(count((r) => nvh(r.verdict) === "NEEDS_HUMAN"), "Needs human", "warn"),
      statTile(agree, "Agreement", "accent", labelled.length ? `${labelled.length} labelled` : "no labels yet"));
  }

  function seg(items, current, onPick) {
    return h("div", { class: "seg", role: "tablist" }, items.map(([value, name, n]) =>
      h("button", { class: value === current ? "on" : "", role: "tab", "aria-selected": String(value === current),
        onclick: () => onPick(value) }, name, n != null && h("span", { class: "n" }, String(n)))));
  }

  function toolbar() {
    const search = h("input", { type: "search", placeholder: "Search ships and reasons", value: state.q, "aria-label": "Search" });
    search.addEventListener("input", () => { state.q = search.value; renderBody(); });
    return h("div", { class: "toolbar" },
      seg([["", "All", state.results.length],
           ["REJECT", "Rejects", count((r) => nvh(r.verdict) === "REJECT")],
           ["APPROVE", "Approves", count((r) => nvh(r.verdict) === "APPROVE")],
           ["NEEDS_HUMAN", "Needs human", count((r) => nvh(r.verdict) === "NEEDS_HUMAN")]],
          state.verdict, (v) => { state.verdict = v; render(); }),
      seg([["todo", "To review", count((r) => !r.feedback)], ["wrong", "Wrong"], ["right", "Right"], ["all", "Everything"]],
          state.label, (v) => { state.label = v; render(); }),
      h("div", { class: "search" }, icon("search"), search));
  }

  function row(r, selected) {
    const m = verdictMeta(r.verdict);
    const pairs = reasonPairs(r);
    const why = pairs.length ? pairs[0].label + (pairs.length > 1 ? ` +${pairs.length - 1}` : "") : (r.summary || "").split(". ")[0];
    const mark = r.feedback && h("span", { class: `mark ${r.feedback.agreement === "right" ? "ok" : "bad"}`,
      title: `You marked: Clanker was ${r.feedback.agreement}`, style: "color:var(--c)" },
      icon(r.feedback.agreement === "right" ? "check" : "x"));
    return h("button", { class: "row" + (selected ? " sel" : ""), "data-id": r.cert_id,
      onclick: () => select(r.cert_id, true) },
      h("span", { class: `dot ${m.tone}`, title: m.label }),
      h("div", { class: "rb" },
        h("div", { class: "rt" }, h("span", { class: "name" }, r.project_name), h("span", { class: "when" }, timeAgo(r.created_at))),
        h("div", { class: "why" }, why)),
      mark);
  }

  function empty(iconName, title, body, ...actions) {
    return h("div", { class: "empty" }, h("div", { class: "big" }, icon(iconName)), h("h3", {}, title), h("p", {}, body),
      actions.length ? h("div", { class: "row-actions" }, actions) : null);
  }

  function paneContent(rec) {
    const m = verdictMeta(rec.verdict);
    const link = (href, label) => href && h("a", { class: "btn sm", href, target: "_blank", rel: "noopener" }, label, icon("external"));
    const head = h("div", { class: "pane-head" },
      h("div", { class: "pane-title" },
        h("button", { class: "btn ghost icon back", "aria-label": "Back", onclick: () => { state.detailMode = false; render(); } }, icon("back")),
        h("h2", {}, rec.project_name), verdictPill(rec.verdict),
        h("span", { class: "hint", title: new Date(rec.created_at).toLocaleString() }, timeAgo(rec.created_at))),
      h("div", { class: "row-actions" },
        h("a", { class: "btn tint accent", href: DASH + rec.cert_id, target: "_blank", rel: "noopener" }, "Open ship", icon("external")),
        link(rec.stardance_url, "Stardance"), link(rec.repo_url, "Repo"), link(rec.demo_url, "Demo")));
    const body = detail(rec, {
      api: ClankerApi, toast,
      onChanged(updated) {
        const i = state.results.findIndex((r) => r.cert_id === updated.cert_id);
        if (i >= 0) state.results[i] = updated; else state.results.unshift(updated);
        render(true); // counts, stats and the list all change with a label
      },
    });
    const wrap = h("div", { class: "pane-body" }, body);
    wrap.clankerRight = body.clankerRight;
    wrap.clankerWrong = body.clankerWrong;
    return [head, wrap];
  }

  // ---------- rendering ----------
  let paneBody = null;
  function renderBody(keepScroll) {
    const list = h("div", { class: "list", role: "listbox", "aria-label": "Judged ships" });
    const pane = h("section", { class: "pane" });
    const items = visible();
    if (!state.selected || !items.some((r) => r.cert_id === state.selected)) {
      state.selected = items[0]?.cert_id ?? null;
    }

    if (!state.loaded) {
      list.append(...Array.from({ length: 7 }, () => h("div", { class: "skel-row" })));
      pane.append(empty("bot", "Loading…", "Fetching Clanker's judgements."));
    } else if (state.error) {
      list.append(empty("alert", "Can't reach Clanker", ""));
      pane.append(empty("alert", "Can't reach the Clanker API", state.error,
        h("button", { class: "btn tint accent", onclick: load }, icon("refresh"), "Retry"),
        h("button", { class: "btn", onclick: openSettings }, icon("settings"), "API settings")));
    } else if (!state.results.length) {
      list.append(empty("bot", "Nothing judged yet", "Ships appear here after Clanker reviews them."));
      pane.append(empty("plus", "Ask Clanker to review a ship", "Paste a ship link or ID and Clanker will take a look.",
        h("button", { class: "btn tint accent", onclick: openReviewDialog }, icon("plus"), "Review a ship")));
    } else if (!items.length) {
      list.append(empty("search", "No matches", "Try another filter, or clear the search."));
      pane.append(empty("check", "All caught up", "Nothing left in this view."));
    } else {
      list.append(...items.map((r) => row(r, r.cert_id === state.selected)));
      const rec = items.find((r) => r.cert_id === state.selected);
      const [head, body] = paneContent(rec);
      pane.append(head, body);
      paneBody = body;
    }

    const split = document.querySelector(".split");
    const next = h("div", { class: "split" + (state.detailMode ? " show-detail" : "") }, list, pane);
    if (split) {
      const top = split.querySelector(".list")?.scrollTop ?? 0;
      split.replaceWith(next);
      if (keepScroll) next.querySelector(".list").scrollTop = top;
    }
    return next;
  }

  function render(keepScroll) {
    const top = document.querySelector(".list")?.scrollTop ?? 0;
    app.replaceChildren(header(), toolbar(), h("div", { class: "split" }));
    renderBody();
    if (keepScroll) document.querySelector(".list").scrollTop = top;
  }

  function header() {
    return h("div", {},
      h("div", { class: "top", style: "margin-bottom:16px" },
        h("div", { class: "brand" }, h("div", { class: "logo" }, icon("bot")),
          h("div", {}, h("h1", {}, "Clanker"), h("p", {}, "First-pass reviews. A human makes every final call."))),
        h("div", { class: "top-actions" },
          h("button", { class: "btn tint accent", onclick: openReviewDialog }, icon("plus"), "Review a ship"),
          h("button", { class: "btn", onclick: exportFeedback }, icon("download"), "Export labels"),
          h("button", { class: "btn icon", title: "Refresh", "aria-label": "Refresh", onclick: load }, icon("refresh")),
          h("button", { class: "btn icon", title: "Settings", "aria-label": "Settings", onclick: openSettings }, icon("settings")))),
      stats());
  }

  function select(id, userClick) {
    state.selected = id;
    if (userClick) state.detailMode = true;
    try { sessionStorage.setItem(SEL_KEY, id); } catch {}
    renderBody(true);
    document.querySelector(".row.sel")?.scrollIntoView({ block: "nearest" });
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
      h("div", { class: "help" }, "Where the extension finds Clanker. Local default is http://127.0.0.1:8765; use your https URL once it's hosted."),
      input, result,
      h("div", { class: "row-actions" },
        h("button", { class: "btn ghost", onclick: () => d.close() }, "Cancel"),
        h("button", { class: "btn", onclick: async () => {
          result.textContent = "Testing…"; result.className = "hint";
          try { await ClankerApi.setBase(input.value); const r = await ClankerApi.listResults();
            result.textContent = `Connected. ${r.length} judged ships.`; result.className = "hint note-ok";
          } catch (e) { result.textContent = e.message; result.className = "hint note-bad"; }
        } }, "Test"),
        h("button", { class: "btn tint accent", onclick: async () => { await ClankerApi.setBase(input.value); d.close(); load(); } }, "Save")),
    ]);
    input.select();
  }

  function openReviewDialog() {
    const input = h("input", { type: "text", placeholder: "Ship link or ID", spellcheck: "false" });
    const status = h("div", { class: "hint" });
    const go = h("button", { class: "btn tint accent" }, "Request review");
    const d = dialog([
      h("h3", {}, "Review a ship"),
      h("div", { class: "help" }, "Paste the dashboard link (or the ID). Clanker reviews it now and posts to Slack. Takes about a minute."),
      input, status,
      h("div", { class: "row-actions" }, h("button", { class: "btn ghost", onclick: () => d.close() }, "Cancel"), go),
    ]);
    const submit = async () => {
      const id = (input.value.match(ID_RE) || [input.value.trim()])[0];
      if (!/^[A-Za-z0-9_-]+$/.test(id)) { status.textContent = "That doesn't look like a ship link or ID."; status.className = "hint note-bad"; return; }
      go.disabled = input.disabled = true; status.className = "hint";
      try {
        const done = await ClankerApi.runReview(id, (t) => (status.textContent = t));
        if (done.state === "failed") throw new Error(done.error || "review failed");
        d.close(); state.verdict = ""; state.label = "all"; state.q = "";
        await load(); select(id); toast("Review ready", "ok");
      } catch (e) { status.textContent = e.message; status.className = "hint note-bad"; go.disabled = input.disabled = false; }
    };
    go.addEventListener("click", submit);
    input.addEventListener("keydown", (e) => e.key === "Enter" && submit());
    input.focus();
  }

  async function exportFeedback() {
    try {
      const res = await ClankerApi.exportFeedback();
      const a = h("a", { href: URL.createObjectURL(await res.blob()), download: "clanker-feedback.jsonl" });
      a.click(); toast("Exported your labels", "ok");
    } catch (e) { toast(`Export failed: ${e.message}`, "bad"); }
  }

  // ---------- data ----------
  async function load() {
    state.error = null; state.loaded = false; renderBody();
    try { state.results = await ClankerApi.listResults(); state.loaded = true; }
    catch (e) { state.results = []; state.error = `${e.message} (${await ClankerApi.getBase()})`; state.loaded = true; }
    render();
  }

  // ---------- keyboard: j/k move, r right, w wrong ----------
  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || document.querySelector("dialog[open]")) return;
    const items = visible(); const i = items.findIndex((r) => r.cert_id === state.selected);
    if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); items[i + 1] && select(items[i + 1].cert_id); }
    else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); items[i - 1] && select(items[i - 1].cert_id); }
    else if (e.key === "r") paneBody?.clankerRight?.();
    else if (e.key === "w") paneBody?.clankerWrong?.();
  });

  try { state.selected = sessionStorage.getItem(SEL_KEY); } catch {}
  render(); load();
})();
