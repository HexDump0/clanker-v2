// Quick triage list of everything Clanker judged. A human confirms or overrules Clanker's
// call here; the real verdict is still submitted by a human on the dashboard.
(() => {
  const DASH = "https://ds.shipwrights.dev/stardance/certifications/";
  const VERDICT = {
    REJECT: ["REJECT", "#ef4444"],
    APPROVE: ["APPROVE", "#22c55e"],
    NEEDS_HUMAN: ["NEEDS HUMAN", "#f59e0b"],
    FLAG_FOR_HUMAN: ["NEEDS HUMAN", "#f59e0b"],
  };
  const FILTERS = [["", "All"], ["REJECT", "Rejects"], ["APPROVE", "Approves"], ["NEEDS_HUMAN", "Needs human"]];
  let filter = "REJECT";
  let results = [];

  const $ = (id) => document.getElementById(id);
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

  function card(r) {
    const [label, color] = VERDICT[r.verdict] || [r.verdict, "#71717a"];
    const status = h("span", { class: "dim" }, r.feedback ? `You marked: Clanker was ${r.feedback.agreement}` : "");
    const el = h("div", { class: "card" + (r.feedback ? " done" : "") });
    const note = h("textarea", { rows: "3", placeholder: "What did Clanker get wrong?" });
    const checks = r.reasons.map((x) => {
      const box = h("input", { type: "checkbox", value: x });
      return { box, el: h("label", {}, box, " " + x) };
    });
    const wrongForm = h("div", { hidden: "" }, h("p", { class: "dim" }, "Which reasons were wrong?"),
      checks.map((c) => c.el), note,
      h("div", { class: "row" }, h("button", { onclick: () =>
        send("wrong", note.value, checks.filter((c) => c.box.checked).map((c) => c.box.value)) }, "Send feedback")));

    async function send(agreement, text = "", wrong = []) {
      try {
        const saved = await ClankerApi.sendFeedback(r.cert_id, { agreement, note: text, wrong_checks: wrong });
        Object.assign(r, saved);
        el.classList.add("done");
        status.textContent = `You marked: Clanker was ${agreement}`;
        wrongForm.hidden = true;
      } catch (e) {
        status.textContent = e.message;
      }
    }

    const video = h("div");
    const links = [
      h("a", { href: DASH + r.cert_id, target: "_blank", rel: "noopener" }, "Open ship"),
      r.stardance_url && h("a", { href: r.stardance_url, target: "_blank", rel: "noopener" }, "Stardance"),
      r.repo_url && h("a", { href: r.repo_url, target: "_blank", rel: "noopener" }, "Repo"),
      r.demo_url && h("a", { href: r.demo_url, target: "_blank", rel: "noopener" }, "Demo"),
    ].filter(Boolean).flatMap((a, i) => (i ? [" · ", a] : [a]));

    el.append(
      h("div", { class: "top" }, h("h2", {}, r.project_name),
        h("span", { class: "badge", style: `background:${color}` }, label),
        h("span", { class: "dim" }, new Date(r.created_at).toLocaleString())),
      h("div", {}, links),
      h("p", {}, r.summary),
      r.reasons.length ? h("ul", {}, r.reasons.map((x) => h("li", {}, x))) : null,
      r.message ? h("details", {}, h("summary", {}, "Message for the shipper"), h("pre", {}, r.message)) : null,
      video,
      h("div", { class: "row" },
        r.video_path ? h("button", { onclick: async (e) => {
          e.target.disabled = true;
          try {
            const blob = await ClankerApi.videoBlob(r.cert_id);
            video.replaceChildren(h("video", { controls: "", src: URL.createObjectURL(blob) }));
          } catch (err) { status.textContent = err.message; }
        } }, "Watch video") : null,
        h("button", { onclick: () => send("right") }, "Clanker was right"),
        h("button", { onclick: () => (wrongForm.hidden = !wrongForm.hidden) }, "Clanker was wrong"),
        h("button", { onclick: async (e) => {
          e.target.disabled = true;
          try {
            const done = await ClankerApi.runReview(r.cert_id, (t) => (status.textContent = t));
            if (done.state === "failed") throw new Error(done.error || "review failed");
            await load();
          } catch (err) { status.textContent = `Review failed: ${err.message}`; e.target.disabled = false; }
        } }, "Re-request review"),
        status),
      wrongForm,
    );
    return el;
  }

  function draw() {
    const hide = $("hideDone").checked;
    const shown = results.filter((r) => (!filter || r.verdict === filter || (filter === "NEEDS_HUMAN" && r.verdict === "FLAG_FOR_HUMAN")) && !(hide && r.feedback));
    $("list").replaceChildren(...(shown.length ? shown.map(card) : [h("p", { class: "dim" }, "Nothing here.")]));
    $("filters").replaceChildren(...FILTERS.map(([v, name]) =>
      h("button", { class: v === filter ? "on" : "", onclick: () => { filter = v; draw(); } }, name)));
  }

  async function load() {
    $("msg").textContent = "Loading…";
    try {
      results = await ClankerApi.listResults();
      $("msg").textContent = `${results.length} judged · API ${await ClankerApi.getBase()}`;
    } catch (e) {
      results = [];
      $("msg").textContent = `Could not load: ${e.message} (API ${await ClankerApi.getBase()})`;
    }
    draw();
  }

  $("refresh").onclick = load;
  $("hideDone").onchange = draw;
  $("settings").onclick = async () => {
    const url = prompt("Clanker API URL", await ClankerApi.getBase());
    if (url) { await ClankerApi.setBase(url); load(); }
  };
  $("export").onclick = async () => {
    const res = await ClankerApi.exportFeedback();
    const a = h("a", { href: URL.createObjectURL(await res.blob()), download: "clanker-feedback.jsonl" });
    a.click();
  };
  load();
})();
