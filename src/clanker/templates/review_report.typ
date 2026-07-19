// Shipwright Review Report — Hack Club Flavortown (Dark Mode)
// Compiled via: typst compile --input key=value ... review_report.typ out.pdf

// ── 1. Inputs & Editor Fallback ─────────────────────────────────────────────
#let is-cli = sys.inputs.keys().contains("data_file")

#let project_name = sys.inputs.at("project_name", default: "IDK MAN")
#let project_desc = sys.inputs.at("project_desc", default: "bla bla bla bla bla bla bla bla bla")
#let verdict      = sys.inputs.at("verdict", default: "REJECT")
#let project_type = sys.inputs.at("project_type", default: "Arcade Game")
#let reasoning    = sys.inputs.at("reasoning", default: "The core gameplay loop is solid, but there are multiple physics bugs and missing documentation.")
#let repo_url     = sys.inputs.at("repo_url", default: "github.com/hackclub/flavortown-game")
#let demo_url     = sys.inputs.at("demo_url", default: "demo.app")
#let review_date  = sys.inputs.at("review_date", default: datetime.today().display())
#let project_url  = sys.inputs.at("project_url", default: "flavortown.hackclub.com/projects/17475")
#let data = if is-cli { 
  json(sys.inputs.at("data_file")) 
} else {
  (
    checks: (
      (name: "syntax_lint", status: "pass", details: "No syntax errors found."),
      (name: "assets_check", status: "warn", details: "Large image files detected (>2MB)."),
      (name: "game_loop", status: "fail", details: "Frame drops on collision."),
    ),
    required_fixes: (
      "Optimize the background PNGs to be under 500kb.",
      "Fix the memory leak in the collision detection function.",
    ),
    feedback: (
      "The pixel art style is incredibly charming!",
      "Consider adding a mute button for the background music.",
    ),
    special_flags: (
      "Uses experimental WebGL features.",
    )
  )
}

#let checks         = data.at("checks", default: ())
#let required_fixes = data.at("required_fixes", default: ())
#let feedback_items = data.at("feedback", default: ())
#let special_flags  = data.at("special_flags", default: ())

// ── 2. Theme Colours ────────────────────────────────────────────────────────
#let hc-darker   = rgb("#121217")
#let hc-dark     = rgb("#17171d")
#let hc-darkless = rgb("#252429")
#let hc-steel    = rgb("#273444")
#let hc-slate    = rgb("#8492a6")
#let hc-smoke    = rgb("#e0e6ed")
#let hc-snow     = rgb("#f9fafc")
#let hc-white    = rgb("#ffffff")
#let hc-red      = rgb("#ec3750")
#let hc-orange   = rgb("#ff8c37")
#let hc-yellow   = rgb("#f1c40f")
#let hc-green    = rgb("#33d6a6")
#let hc-cyan     = rgb("#5bc0de")
#let hc-blue     = rgb("#338eda")
#let hc-purple   = rgb("#a633d6")

#let hc-card     = rgb("#1e1e24")
#let hc-card-alt = rgb("#24242b")
#let hc-border   = rgb("#2e2e36")

// ── 3. Helpers ──────────────────────────────────────────────────────────────
#let verdict-color = if verdict == "APPROVE" { hc-green } else if verdict == "REJECT" { hc-red } else { hc-orange }

#let status-color(s) = {
  if s == "pass" { hc-green } else if s == "fail" { hc-red } else if s == "warn" { hc-orange } else { hc-slate }
}

#let humanize(name) = {
  name.replace("_", " ").split(" ").map(w => {
    if w.len() == 0 { w } else { upper(w.first()) + w.slice(1) }
  }).join(" ")
}

// ── 4. Page Setup ───────────────────────────────────────────────────────────
#set document(title: "Shipwright Review — " + project_type, author: "Shipwright")

#let sans = ("Noto Sans", "Liberation Sans", "DejaVu Sans")
#let mono = ("JetBrainsMono Nerd Font", "DejaVu Sans Mono", "Liberation Mono")

#set page(
  paper: "us-letter",
  fill: hc-dark,
  margin: (x: 1.5cm, y: 2cm),
  header: align(right)[
    #text(fill: hc-slate, size: 8pt, weight: "bold", font: mono)[
      SW-CLANKER ™
    ]
  ],
  footer: context {
    set text(size: 8pt, fill: hc-slate, font: sans)
    grid(
      columns: (1fr, auto),
      align(left)[Made by Floppy · Powered by Hack Club AI],
      align(right)[Page #counter(page).display("1 of 1", both: true)],
    )
  },
)

#set text(fill: hc-snow, font: sans, size: 10pt, lang: "en")
#show: set text(font: sans)
#set par(justify: false, leading: 0.65em)

// Custom Headings
#set heading(numbering: none)
#show heading: it => block(
  above: 16pt, below: 10pt,
  [
    #text(fill: hc-red, weight: "black", size: 1.2em, font: sans)[#it.body]
    #v(-8pt)
    #line(length: 100%, stroke: 2pt + hc-red)
  ]
)

// ═══════════════════════════════════════════════════════════════════════════
// DOCUMENT BODY
// ═══════════════════════════════════════════════════════════════════════════
// ── Warning Banner ──────────────────────────────────────────────────────────
#rect(width: 100%, fill: hc-red.transparentize(90%), stroke: 1.5pt + hc-red, radius: 6pt, inset: 10pt)[
  #text(fill: hc-red, weight: "bold", size: 10pt)[⚠️ WARNING:]
  #text(fill: hc-smoke, size: 10pt)[ sw-clanker cant interact with the demo or verify its live functionality.]
]

#v(8pt)

// ── Top Banner ──────────────────────────────────────────────────────────────
#rect(width: 100%, fill: hc-red, radius: 6pt, inset: 15pt)[
  #text(fill: hc-white, size: 22pt, weight: "black")[#project_name] \
  #v(2pt)
  #text(fill: hc-white.transparentize(20%), size: 10pt, weight: "medium")[
    #project_desc
  ]
  #if repo_url != "" [
    #v(4pt)
    #text(fill: hc-white.transparentize(10%), size: 9pt, font: mono)[#link("https://" + repo_url)[#repo_url]]
  ]
]

#v(8pt)


// ── Metadata Grid ───────────────────────────────────────────────────────────
#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: 10pt,

  // Adding height: 72pt for perfectly uniform cards
  rect(
    height: 72pt,
    fill: verdict-color.transparentize(90%), 
    stroke: 1.5pt + verdict-color, 
    radius: 6pt, inset: 12pt, width: 100%
  )[
    #text(size: 9pt, fill: hc-slate, weight: "bold")[VERDICT] \
    #v(0pt)
    #text(size: 18pt, fill: verdict-color, weight: "black")[#verdict]
  ],

  rect(height: 72pt, fill: hc-card, stroke: 1pt + hc-border, radius: 6pt, inset: 12pt, width: 100%)[
    #text(size: 9pt, fill: hc-slate, weight: "bold")[PROJECT TYPE] \
    #v(6pt)
    #text(size: 12pt, fill: hc-snow, weight: "black")[#project_type]
  ],

  rect(height: 72pt, fill: hc-card, stroke: 1pt + hc-border, radius: 6pt, inset: 12pt, width: 100%)[
    #text(size: 9pt, fill: hc-slate, weight: "bold")[REVIEW DATE] \
    #v(6pt)
    #text(size: 12pt, fill: hc-snow, weight: "black")[#review_date]
  ],
)

#v(4pt)

// ── Demo URL ────────────────────────────────────────────────────────────────
#if demo_url != "" and project_url != "" [
  #rect(fill: hc-card, stroke: 1pt + hc-border, radius: 6pt, inset: 10pt, width: 100%)[
    #grid(
      columns: (65pt, 1fr),
      text(size: 9pt, fill: hc-slate, weight: "bold")[PROJECT],
      text(fill: hc-cyan, size: 9pt, font: mono)[#link("https://" + project_url)[#project_url]],
    )
    #v(4pt)
    #grid(
      columns: (65pt, 1fr),
      text(size: 9pt, fill: hc-slate, weight: "bold")[DEMO URL],
      text(fill: hc-cyan, size: 9pt, font: mono)[#link("https://" + demo_url)[#demo_url]],
    )

  ]
  #v(4pt)
]


// ── Reasoning & Feedback ────────────────────────────────────────────────────
= Reasoning

#v(10pt)

// Dynamically generate the bottom cards so they grid properly
#let bottom-cards = ()

#if verdict == "REJECT" and required_fixes.len() > 0 {
  bottom-cards.push(
    rect(width: 100%, fill: hc-red.transparentize(92%), stroke: 1.5pt + hc-red, radius: 6pt, inset: 12pt)[
      #text(fill: hc-red, weight: "bold", size: 11pt)[Required Fixes]
      #v(6pt)
      #set list(spacing: 12pt)
      #list(..required_fixes.map(f => text(fill: hc-smoke)[#f]))
    ]
  )
}

#if feedback_items.len() > 0 {
  bottom-cards.push(
    rect(width: 100%, fill: hc-blue.transparentize(92%), stroke: 1.5pt + hc-blue, radius: 6pt, inset: 12pt)[
      #text(fill: hc-blue, weight: "bold", size: 11pt)[Feedback]
      #v(6pt)
      #set list(spacing: 12pt)
      #list(..feedback_items.map(f => text(fill: hc-smoke)[#f]))
    ]
  )
}



// Render the grid if there's anything in it (handles 1 or 2 items safely)
#if bottom-cards.len() > 0 [
  #grid(
    columns: if bottom-cards.len() == 1 { (100%,) } else { (1fr, 1fr) },
    gutter: 12pt,
    ..bottom-cards
  )
]

#v(4pt)

#rect(width: 100%, fill: hc-card, stroke: 1pt + hc-border, radius: 6pt, inset: 12pt)[
  #text(size: 10pt, fill: hc-smoke, font: sans)[#reasoning]
]

#v(6pt)


// ── Checks Table ────────────────────────────────────────────────────────────
= Checks

#table(
  columns: (1.2fr, 55pt, 2.2fr),
  align: (left, center, left),
  stroke: (x, y) => if y == 0 { (bottom: 1pt + hc-red) } else { none },  inset: (x: 8pt, y: 8pt),
  
  // Changed y == 0 fill to hc-steel so it no longer blends in
  fill: (_, y) => if y == 0 { hc-darkless } else if calc.odd(y) { hc-card } else { hc-card-alt },

  table.header(
    text(fill: hc-smoke, weight: "bold", size: 8pt, font: sans)[CHECK],
    text(fill: hc-smoke, weight: "bold", size: 8pt, font: sans)[STATUS],
    text(fill: hc-smoke, weight: "bold", size: 8pt, font: sans)[DETAILS],
  ),

  ..checks.map(c => {
    let st = c.at("status", default: "skip")
    (
      text(fill: hc-snow, size: 9pt, weight: "semibold", font: sans)[#humanize(c.at("name", default: ""))],
      rect(
        fill: status-color(st).transparentize(80%), stroke: 1pt + status-color(st),
        radius: 3pt, inset: (x: 0pt, y: 3pt), width: 100%,
      )[
        #text(fill: status-color(st), size: 7pt, weight: "bold", font: sans)[#upper(st)]
      ],
      text(fill: hc-slate, size: 8.5pt, font: sans)[#c.at("details", default: "")],
    )
  }).flatten()
)

#v(10pt)

#if special_flags.len() > 0 [
  #v(12pt)
  #rect(width: 100%, fill: hc-orange.transparentize(92%), stroke: 1.5pt + hc-orange, radius: 6pt, inset: 12pt)[
    #text(fill: hc-orange, weight: "bold", size: 11pt, font: sans)[Special Flags]
    #v(6pt)
    #list(..special_flags.map(f => text(fill: hc-smoke, font: sans)[#f]))
  ]
]
