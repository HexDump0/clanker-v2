// First-layer review report — same Hack Club dark theme as review_report.typ.
// Compiled via: typst compile --input key=value ... first_layer_report.typ out.pdf
// Data: clanker.review.first_layer.report.build_report_data (JSON file in `data_file`).

// ── 1. Inputs & editor fallback ─────────────────────────────────────────────
#let is-cli = sys.inputs.keys().contains("data_file")

#let project_name = sys.inputs.at("project_name", default: "ISO_VERSE")
#let project_desc = sys.inputs.at("project_desc", default: "It's very personal to me :D")
#let repo_url     = sys.inputs.at("repo_url", default: "github.com/someone/ISO_VERSE")
#let demo_url     = sys.inputs.at("demo_url", default: "someone.github.io/ISO_VERSE")
#let readme_url   = sys.inputs.at("readme_url", default: "raw.githubusercontent.com/someone/ISO_VERSE/main/README.md")
#let project_url  = sys.inputs.at("project_url", default: "")
#let review_date  = sys.inputs.at("review_date", default: datetime.today().display())
#let data = if is-cli {
  json(sys.inputs.at("data_file"))
} else {
  (
    verdict: "REJECT",
    project_type: "Web App",
    reasons: (
      (
        label: "AI-heavy code",
        fix: "The code/CSS looks mostly AI-generated (over the 30% AI limit). Rewrite the styling and core parts yourself and add your own features.",
        evidence: ("Code rule: 9/10 modern AI CSS signals (rejects at 6): noise_texture, eyebrow_label", "Files read: style.css, index.html, script.js"),
      ),
    ),
    message: "Hey there! Cool idea! Unfortunately your project seems to use an excessive amount of AI. Please rewrite the CSS by hand and make it something that's really yours.",
    near_misses: (),
    jev: (
      (name: "Code/CSS mostly AI-generated", score: 0.67, limit: 0.7, status: "warn"),
      (name: "README written with AI", score: 0.21, limit: 0.7, status: "pass"),
      (name: "Demo can't be tried", score: 0.35, limit: none, status: "info"),
    ),
    code_checks: (
      (name: "README", status: "pass", details: "1,840 chars, from Dashboard cache"),
      (name: "Modern AI CSS style", status: "fail", details: "9/10 signals (rejects at 6)"),
    ),
  )
}

#let verdict     = data.at("verdict", default: "NEEDS HUMAN")
#let reasons     = data.at("reasons", default: ())
#let message     = data.at("message", default: "")
#let near_misses = data.at("near_misses", default: ())
#let jev_rows    = data.at("jev", default: ())
#let code_checks = data.at("code_checks", default: ())

// ── 2. Theme ────────────────────────────────────────────────────────────────
#let hc-dark     = rgb("#17171d")
#let hc-darkless = rgb("#252429")
#let hc-slate    = rgb("#8492a6")
#let hc-smoke    = rgb("#e0e6ed")
#let hc-snow     = rgb("#f9fafc")
#let hc-white    = rgb("#ffffff")
#let hc-red      = rgb("#ec3750")
#let hc-orange   = rgb("#ff8c37")
#let hc-green    = rgb("#33d6a6")
#let hc-cyan     = rgb("#5bc0de")
#let hc-blue     = rgb("#338eda")
#let hc-purple   = rgb("#8b5cf6")
#let hc-card     = rgb("#1e1e24")
#let hc-card-alt = rgb("#24242b")
#let hc-border   = rgb("#2e2e36")

#let sans = ("Noto Sans", "Liberation Sans", "DejaVu Sans")
#let mono = ("JetBrainsMono Nerd Font", "DejaVu Sans Mono", "Liberation Mono")

#let verdict-color = if verdict == "REJECT" { hc-red } else { hc-purple }
#let status-color(s) = {
  if s == "pass" { hc-green } else if s == "fail" { hc-red } else if s == "warn" { hc-orange } else { hc-slate }
}
#let status-label(s) = {
  if s == "pass" { "OK" } else if s == "fail" { "FAIL" } else if s == "warn" { "CLOSE" } else { "INFO" }
}
#let pill(s) = rect(
  fill: status-color(s).transparentize(80%), stroke: 1pt + status-color(s),
  radius: 3pt, inset: (x: 0pt, y: 3pt), width: 100%,
)[#align(center, text(fill: status-color(s), size: 7pt, weight: "bold")[#status-label(s)])]
#let card(body, color: none, fill: hc-card) = rect(
  width: 100%, radius: 6pt, inset: 12pt,
  fill: if color == none { fill } else { color.transparentize(92%) },
  stroke: if color == none { 1pt + hc-border } else { 1.5pt + color },
  body,
)
#let link-row(label, url) = if url != "" {
  grid(
    columns: (62pt, 1fr),
    text(size: 8pt, fill: hc-slate, weight: "bold")[#label],
    text(fill: hc-cyan, size: 8.5pt, font: mono)[#link("https://" + url)[#url]],
  )
  v(3pt)
}

// ── 3. Page ─────────────────────────────────────────────────────────────────
#set document(title: "Clanker first-layer review — " + project_name, author: "sw-clanker v2")
#set page(
  paper: "us-letter",
  fill: hc-dark,
  margin: (x: 1.5cm, y: 2cm),
  header: align(right, text(fill: hc-slate, size: 8pt, weight: "bold", font: mono)[SW-CLANKER V2 · FIRST LAYER]),
  footer: context {
    set text(size: 8pt, fill: hc-slate, font: sans)
    grid(
      columns: (1fr, auto),
      align(left)[Made by Floppy],
      align(right)[Page #counter(page).display("1 of 1", both: true)],
    )
  },
)
#set text(fill: hc-snow, font: sans, size: 10pt, lang: "en")
#set par(justify: false, leading: 0.65em)
#show heading: it => block(above: 18pt, below: 10pt)[
  #text(fill: hc-red, weight: "black", size: 1.2em)[#it.body]
  #v(-8pt)
  #line(length: 100%, stroke: 2pt + hc-red)
]

// ── 4. Body ─────────────────────────────────────────────────────────────────
#rect(width: 100%, fill: hc-red, radius: 6pt, inset: 15pt)[
  #text(fill: hc-white, size: 22pt, weight: "black")[#project_name] \
  #if project_desc != "" [
    #v(2pt)
    #text(fill: hc-white.transparentize(20%), size: 10pt, weight: "medium")[#project_desc]
  ]
]

#v(8pt)

#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: 10pt,
  rect(height: 64pt, width: 100%, fill: verdict-color.transparentize(88%), stroke: 1.5pt + verdict-color, radius: 6pt, inset: 12pt)[
    #text(size: 8pt, fill: hc-slate, weight: "bold")[VERDICT] \
    #v(2pt)
    #text(size: if verdict.len() > 8 { 15pt } else { 18pt }, fill: verdict-color, weight: "black")[#verdict]
  ],
  rect(height: 64pt, width: 100%, fill: hc-card, stroke: 1pt + hc-border, radius: 6pt, inset: 12pt)[
    #text(size: 8pt, fill: hc-slate, weight: "bold")[PROJECT TYPE] \
    #v(4pt)
    #text(size: 12pt, weight: "black")[#data.at("project_type", default: "Other")]
  ],
  rect(height: 64pt, width: 100%, fill: hc-card, stroke: 1pt + hc-border, radius: 6pt, inset: 12pt)[
    #text(size: 8pt, fill: hc-slate, weight: "bold")[REVIEWED] \
    #v(4pt)
    #text(size: 12pt, weight: "black")[#review_date]
  ],
)

#v(4pt)

#card[
  #link-row("DEMO", demo_url)
  #link-row("REPO", repo_url)
  #link-row("README", readme_url)
  #link-row("STARDANCE", project_url)
]

// Why / what to look at
#if verdict == "REJECT" [
  = Why it was rejected
  #for r in reasons [
    #card(color: hc-red)[
      #text(fill: hc-red, weight: "bold", size: 11pt)[#r.label]
      #v(3pt)
      #text(fill: hc-smoke, size: 9.5pt)[#r.fix]
      #if r.evidence.len() > 0 [
        #v(5pt)
        #for e in r.evidence [
          #text(fill: hc-slate, size: 8pt, font: mono)[→ #e] \
        ]
      ]
    ]
    #v(2pt)
  ]
  #if message != "" [
    = Message for the shipper
    #card(color: hc-blue)[
      #text(fill: hc-smoke, size: 9.5pt)[#message]
    ]
  ]
] else [
  = What the human should look at
  #card(color: hc-purple)[
    #text(fill: hc-smoke, size: 9.5pt)[Nothing was clear enough to reject automatically. Test the demo as usual.]
    #if near_misses.len() > 0 [
      #v(6pt)
      #text(fill: hc-orange, weight: "bold", size: 9.5pt)[Close to the limit, worth a look:]
      #v(2pt)
      #list(..near_misses.map(n => text(fill: hc-smoke, size: 9pt)[#n]))
    ]
  ]
]

// Jev scores
#if jev_rows.len() > 0 [
  = Jev scores
  #let bar(score, limit, st) = box(width: 100%, height: 7pt, radius: 3pt, fill: hc-darkless, clip: true)[
    #place(left, box(width: score * 100%, height: 7pt, radius: 3pt, fill: status-color(st)))
    #if limit != none { place(left, dx: limit * 100% - 1pt, box(width: 2pt, height: 7pt, fill: hc-snow)) }
  ]
  #table(
    columns: (1.6fr, 1.4fr, 34pt, 38pt, 46pt),
    align: (left + horizon, horizon, right + horizon, right + horizon, center + horizon),
    stroke: (x, y) => if y == 0 { (bottom: 1pt + hc-red) } else { none },
    inset: (x: 7pt, y: 6pt),
    fill: (_, y) => if y == 0 { hc-darkless } else if calc.odd(y) { hc-card } else { hc-card-alt },
    table.header(
      text(fill: hc-smoke, weight: "bold", size: 7.5pt)[QUESTION (YES = REJECT)],
      text(fill: hc-smoke, weight: "bold", size: 7.5pt)[SCORE · LIMIT],
      text(fill: hc-smoke, weight: "bold", size: 7.5pt)[SCORE],
      text(fill: hc-smoke, weight: "bold", size: 7.5pt)[LIMIT],
      text(fill: hc-smoke, weight: "bold", size: 7.5pt)[RESULT],
    ),
    ..jev_rows.map(r => (
      text(size: 8.5pt, weight: "semibold")[#r.name],
      bar(r.score, r.limit, r.status),
      text(size: 8.5pt, font: mono)[#r.at("score_text", default: str(r.score))],
      text(size: 8.5pt, font: mono, fill: hc-slate)[#if r.limit == none [—] else [#str(r.limit)]],
      pill(r.status),
    )).flatten(),
  )
]

// Code checks
#if code_checks.len() > 0 [
  = Code checks
  #table(
    columns: (1.1fr, 46pt, 2.6fr),
    align: (left + horizon, center + horizon, left + horizon),
    stroke: (x, y) => if y == 0 { (bottom: 1pt + hc-red) } else { none },
    inset: (x: 7pt, y: 6pt),
    fill: (_, y) => if y == 0 { hc-darkless } else if calc.odd(y) { hc-card } else { hc-card-alt },
    table.header(
      text(fill: hc-smoke, weight: "bold", size: 7.5pt)[CHECK],
      text(fill: hc-smoke, weight: "bold", size: 7.5pt)[RESULT],
      text(fill: hc-smoke, weight: "bold", size: 7.5pt)[DETAILS],
    ),
    ..code_checks.map(c => (
      text(size: 8.5pt, weight: "semibold")[#c.name],
      pill(c.status),
      text(fill: hc-slate, size: 8pt)[#c.details],
    )).flatten(),
  )
]
