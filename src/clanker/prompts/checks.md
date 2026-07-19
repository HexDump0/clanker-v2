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
The repo link must point to the repo root, not a specific file or subdirectory.
- **pass**: repo root URL
- **fail**: points at a file, blob, or unrelated page

### 4. pre_event_commits
Check commit history for activity before **June 1, 2026** (the event cutoff —
projects started before Stardance, or previously submitted to another YSWS, must be
declared as updates).
- **pass**: no commits before the cutoff, OR commits exist AND the submission is
  declared as an update (check the `updated_project` field in the packet and the
  description for an "UPDATED PROJECT" mention)
- **warn**: commits before the cutoff but not declared as an update
- (never fail)

### 5. ai_detection
Analyze the README for signs of AI generation (generic phrasing, ChatGPT-style
structure like "🚀 Features", boilerplate "Getting Started", polish that doesn't match
code quality). Also check the demo site for AI-generated content. If AI usage is
detected, check the `ai_declaration` field in the packet.
- **pass**: no AI signals, OR AI detected and declared in the submission
- **fail**: AI signals detected but no AI declaration

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
The README should explain what the project is, how to use it, and relevant setup.
A few lines is not enough for most project types (simple portfolio sites get leeway).
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
project as the repo? Do NOT test demo functionality — that is for human reviewers.
- **pass**: demo matches the expected format for the detected type
- **warn**: demo exists but on a discouraged platform, or detected type is ambiguous
- **fail**: demo missing, wrong type for the detected project, or unrelated to the repo

### 11. demo_credentials
Premade/shared credentials are NOT allowed — reviewers must be able to create their
own account. Check README, description, and demo page for "demo account", "test
credentials", "username: … password: …" patterns.
- **pass**: no premade credentials required
- **fail**: demo requires shared/premade login details
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
Kaggle notebooks, Hugging Face, Render/Railway free tier (for web apps), tunnel
links (ngrok, cloudflared, DuckDNS), zips of source, raw source files (`.py`,
`.js`) are all rejected.
- **pass**: not on any rejected platform/format
- **fail**: uses a universally rejected platform/format

## How to check

- Commits/authorship: `review_get_github_commits` (the packet has recent commits; fetch
  more when you need history depth).
- Repo contents: `review_get_github_repo_tree`, `review_get_github_file_content`,
  `review_get_github_releases` (for CLI/desktop: do releases contain real binaries?).
- Demo: `review_check_url`, then `review_fetch_page_text` to read the page.
- Secrets scan: `review_get_github_repo_tree` for suspicious files, then
  `review_get_github_file_content` (or `review_search_github_code`).
- AI declaration / update flag: `ai_declaration` and `updated_project` fields in the
  packet; `review_fetch_stardance_project` only as a fallback.
