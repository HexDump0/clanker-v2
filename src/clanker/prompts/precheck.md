# Stage 1: Pre-Check

Fast, lightweight validation before any deeper review begins. You ONLY check the
items below in this stage — nothing else.

## What you check

1. **Project type detection**: You MUST independently determine the actual project
   type. The type claimed in the submission (and any AI-detected type) is frequently
   wrong — treat it as a weak hint at best. Your detected type is the one used for all
   downstream checks including demo validation.

   **How to detect** — cross-reference ALL of these signals; no single signal is definitive:
   - **Repo files** (`get_github_repo_tree`): marker files — `package.json`
     (web/node), `.sln`/`.csproj` (desktop), `AndroidManifest.xml` (Android),
     `Podfile`/`.xcodeproj` (iOS), `Cargo.toml` (Rust CLI/lib), `setup.py`/`pyproject.toml`
     (Python lib/CLI), Unity/Godot project files (game), Arduino/KiCad files (hardware),
     `manifest.json` in extension-like structure (browser extension), etc.
   - **Languages** (`get_github_languages`): a Python repo could be a web app
     (Flask/Django), CLI tool, or library depending on other signals.
   - **README content** (in the packet): the description often states what it is
     ("a Discord bot", "a Chrome extension", "a portfolio website").
   - **Project name and description** from the submission: context only — verify against the repo.
   - **Demo URL pattern**: an `.exe` in GitHub Releases suggests desktop, a live URL
     suggests web app, an npm link suggests library.

   **If the claimed type conflicts with what you detect**, always use YOUR detected
   type and set `type_mismatch: true`.

2. **Repo accessibility**: confirm via `get_github_repo_info` that the repository
   exists and is public. A 404 or private repo is an instant reject.

3. **README existence**: the packet includes the README if the dashboard could fetch
   it. If it's missing or empty, double-check with `get_github_readme` before
   concluding. No README is an instant reject.

4. **Demo URL reachability**: if a demo URL was provided, `check_url` it and
   record whether it responds without error (2xx/3xx). Do NOT test functionality.

5. **Resubmission spam detection** (flag): check the prior reviews in the packet. If
   the same project has been rejected 3+ times for the same or substantially similar
   issues, check whether there were commits AFTER the most recent rejection
   (`get_github_commits`). Commits after the last rejection = benefit of the
   doubt, do NOT flag. Only flag if there are no post-rejection commits or they are
   trivial (README-only). Not an instant reject — record it for the verdict stage.

6. **Demo URL early screening** (flag): record matches against problematic patterns
   (`check_url` flags these automatically): Google Drive, Google Colab,
   Hugging Face, Kaggle, `*.onrender.com`, `*.up.railway.app`, ngrok, localhost.

## Instant reject conditions

- Repository does not exist (404) → instant reject
- Repository is private → instant reject
- No README file exists → instant reject

On instant reject: set `instant_reject: true` with the reason, mark all rubric checks
`skip` (except any you already evaluated), and proceed straight to the verdict stage.
