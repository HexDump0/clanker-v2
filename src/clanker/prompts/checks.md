# Stage 2: Checks

The full rubric. Uses the pre-check results (detected project type, repo
accessibility, README existence, demo reachability). Every check maps to one field
of the structured output; each result is a status (`pass`/`fail`/`warn`/`skip`)
plus 1–2 sentences of evidence.

### 1. readme_is_raw_github
Stardance requires the raw README file URL (`raw.githubusercontent.com/...`) so it can
render the markdown itself. Check the submission's readme URL.
- **pass**: readme link is a raw GitHub URL
- **fail**: readme link points at the rendered repo page (`github.com/owner/repo` or
  `.../blob/.../README.md`) or is not on GitHub

### 2. readme_matches_repo
Verify the README and repository are for the same project, and the submitted
description/demo matches the repo content.
- **pass**: description, README, and repo all align
- **fail**: mismatch between description and repo

### 3. repo_link_valid
The repo link must point to the repo root, not a specific file or subdirectory, and
the complete meaningful project source must be publicly available there.
- **pass**: public repo-root URL containing the project source
- **fail**: points at a file/blob/unrelated page, or the public repo omits the actual
  source and contains only binaries, screenshots, a README, or an empty shell

### 4. pre_event_commits
Check project history against **June 1, 2026**, the Stardance cutoff.

- A project started before June 1, 2026 or previously submitted to another YSWS must
  be marked as an updated project.
- A project submitted to another competition, game jam, or hackathon is ineligible
  unless the packet shows that new work time was tracked after Stardance began (for
  example, more features built during qualifying tracked time or a restart from
  scratch). A later commit by itself is not proof that time was tracked.
- **pass**: no pre-cutoff/prior-program evidence; OR it is correctly declared as an
  update and any prior-competition submission has explicit post-start tracked-time
  evidence
- **warn**: it should be marked updated but is not; OR prior-competition eligibility
  is disclosed but the available packet cannot establish whether post-start time was
  tracked (also request human verification)
- **fail**: the project was submitted to another competition/game jam/hackathon and
  the evidence shows no qualifying tracked work after Stardance began

### 5. ai_detection
Check the README, release description, project/demo, devlogs, and any visible generated
images or logos against the AI declaration. Base this only on clear, concrete evidence;
professional writing, a conventional "Features"/"Getting Started" structure, or emojis
alone do not prove AI use.

- A completely AI-written README (especially generic copy filled with excessive emoji)
  must be returned. AI-assisted writing is allowed when the README is primarily in the
  shipper's own words, clear, readable, and project-specific.
- An AI-generated project banner is forbidden. The banner must be a screenshot of the
  project in action, not a generated image, logo, or irrelevant/inappropriate art.
- A completely vibe-coded generic project must be returned. Ask the shipper to add
  their own styling, design choices, and personal touches throughout the project.
- Ordinary AI assistance and generated assets must be clearly disclosed. If use seems
  undisclosed but is not one of the hard failures above, **warn**, add `AI UNDISCLOSED`,
  continue testing the other requirements, and report it without pressuring the shipper
  to make a declaration.
- **pass**: no concrete AI concern, or allowed AI assistance is adequately declared
- **warn**: concrete but non-disqualifying AI use appears undeclared, or visible
  banner/devlog evidence raises a material concern that needs human confirmation
- **fail**: clearly completely AI-written README, AI-generated banner, or completely
  vibe-coded generic project lacking the shipper's own design/personal contribution

### 6. commit_authorship
Check the commit history for suspicious patterns: no commits at all, or a single
"Initial commit" dump containing the whole project (no incremental development).
Do NOT compare commit author names/emails against the submitter's identity — git
identities frequently differ from dashboard usernames (different emails, machine
configs, noreply addresses) and this produces too many false positives.
- **pass**: history shows incremental development
- **warn**: single large commit containing the whole project, or history that
  otherwise doesn't reflect real development
- **fail**: no commits at all

### 7. readme_boilerplate
Scan the README for boilerplate/placeholder content: generic placeholders
(`localhost`, `your-project`, `TODO`, `Lorem ipsum`); framework scaffold text
(React+Vite "This template provides a minimal setup", Create React App "Available
Scripts", Next.js "bootstrapped with create-next-app", Vue CLI "Compiles and
hot-reloads", Angular CLI "generated with"); README that is just pasted source code.
- **pass**: original project-specific content
- **fail**: boilerplate, scaffold README, or pasted code

### 8. readme_substance
The README must be raw Markdown, written in English, and explain what the project is,
how to use it, and relevant setup/download steps and features. The needed depth depends
on the project: a portfolio may briefly cover development and features, while a CLI,
API, bot, or library needs detailed installation and usage instructions. It must never
be only a one-line "this is a ..." description.
- **pass**: substantive and informative
- **fail**: too short or content-free

### 9. readme_language
Judge the language of the README's **prose** (headings, paragraphs, setup
instructions) — NOT code snippets, variable names, or localized UI strings inside
examples.
- **pass**: prose is in English, or an English translation is linked at the top
- **fail**: prose is non-English with no English version linked

### 10. demo_validity
Validate the demo link/artifact against the **detected project type from pre-check**
(NOT the claimed type), using the Demo Guidelines reference. If pre-check flagged a
`type_mismatch`, pay extra attention. Cross-reference the demo against the actual
project: does the URL make sense for what the code is, and does it show the same
project as the repo? Inspect the evidence available to you, but do not claim that static
text/code/screenshot inspection functionally tested the project. The human reviewer must
test features while recording the required proof video.
- **pass**: demo matches the expected format for the detected type
- **warn**: demo exists but on a discouraged platform, or detected type is ambiguous
- **fail**: demo missing, wrong type for the detected project, or unrelated to the repo

### 11. demo_credentials
Premade/shared credentials are NOT allowed — reviewers must be able to create their
own account. Check README, description, demo page, and relevant auth code for "demo
account", "test credentials", "username: … password: …" patterns and for a real
sign-up path. A human reviewer must test at least one offered OAuth option and also the
conventional sign-up/login path so all authenticated features are exercised.
- **pass**: authentication is present, self-registration is available, and the required
  human OAuth/conventional interaction test was completed successfully
- **warn**: self-registration appears available, but Clanker cannot establish that the
  OAuth and conventional flows actually complete; request human testing
- **fail**: the project requires a premade/shared/shipwright account, does not allow the
  reviewer to create their own account, or the human test establishes a broken required
  auth path
- **skip**: project has no authentication at all
- Exception: for API projects, documented test credentials / demo API keys for trying
  endpoints are acceptable (the API guide even recommends them) — this rule targets
  user-account login flows.

### 12. description_accuracy
Compare features claimed in the description/README against what exists in the
code/demo.
- **pass**: claims match the codebase
- **warn**: minor discrepancies
- **fail**: major claimed features don't exist

### 13. demo_link_type
Universal link rules, independent of project type: Google Drive, Google Colab,
Kaggle notebooks, Hugging Face, Render/Railway/Streamlit free hosting (for web apps),
tunnel or dynamic-DNS links (ngrok, cloudflared/trycloudflare, DuckDNS), localhost,
zips of source, and raw source files (`.py`, `.js`) are all rejected. Web hosting that
is observably too slow or repeatedly cold-starts is also invalid; do not fail a site for
one transient slow request without corroborating evidence.
- **pass**: not on any rejected platform/format
- **fail**: uses a universally rejected platform/format

## How to check

- Commits/authorship: `get_github_commits` (the packet has recent commits; fetch
  more when you need history depth).
- Repo contents: `get_github_repo_tree`, `get_github_file_content`,
  `get_github_releases` (for CLI/desktop: do releases contain real binaries?).
- Demo: `check_url`, then `fetch_page_text` to read the page.
- Unknown hosting platform (demo host you don't recognize and can't classify from the
  page itself): one `web_search` to find out what it is (free tier that
  sleeps? tunnel service?) before judging `demo_validity` / `demo_link_type`. This is
  the tool's only routine use — see its restrictions in the tool list.
- Secrets scan: `get_github_repo_tree` for suspicious files, then
  `get_github_file_content` (or `search_github_code`).
- AI declaration / update flag: `ai_declaration` and `updated_project` fields in the
  packet; `fetch_stardance_project` only as a fallback.
- Banner: use the Stardance page's `image` metadata URL when present. `render_page` may
  inspect that public image when needed to distinguish an in-action screenshot from a
  logo/irrelevant image. Treat uncertain AI provenance as a human check, not a guess.
