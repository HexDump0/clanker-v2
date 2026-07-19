# Demo Validation Guidelines

Rules for what constitutes a valid demo link or artifact per project type, synced with
the official Shipwrights guide (ship docs, github.com/hackclub/ship). Used by the
checks agent for the `demo_validity` check. These rules validate the link type and
accessibility only — actual demo testing is for human reviewers.

## General rejection rules (apply to ALL project types)

- **Reject**: Google Drive links (`drive.google.com`) — not acceptable as demo links. Use YouTube for videos, cdn.hackclub.com for files.
- **Reject**: Google Colab links (`colab.research.google.com`) and Kaggle notebooks — not acceptable as demos. Build a CLI/GUI wrapper and package as executable or website.
- **Reject**: Hugging Face links (`huggingface.co`) — not acceptable as demo hosting. Build a self-hosted deployment, API, or packaged application.
- **Reject**: Demo link pointing to a zip of source code — not a valid demo.
- **Reject**: Demo link pointing to a single source file (e.g., `.py`, `.js`) — not a valid demo.
- **Reject**: Demo link that is the repo URL itself (unless it's a library/package with clear install instructions).

## Web apps
- **Valid**: Live URL on GitHub Pages, Vercel, Netlify, Cloudflare Pages, or similar permanent hosting
- **Reject**: ngrok, cloudflared, DuckDNS, or any tunnel link
- **Reject**: Render (*.onrender.com), Railway (*.up.railway.app), Hugging Face — free tiers spin down, causing cold-start delays or dead links
- **Reject**: localhost URLs or local-only instructions without a live deployment
- **Note**: If the app has authentication, users must be able to create their own accounts and log in

## Desktop apps (executables)
- **Valid**: Ready-to-download build in GitHub Releases — Windows: `.exe`/`.msi`; macOS: `.dmg` or `.zip` of the `.app`; Linux: `.AppImage`, `.deb`, or `.tar.gz`
- **Requirement**: Must launch on a standard machine without manual source-code setup; runtime/dependency instructions belong in the README
- **Reject**: Source-only with no prebuilt binary
- **Reject**: Demo video alone is not acceptable — need actual executable in GitHub Releases
- **Reject**: Link to a directory in the repo instead of a GitHub Release

## Android apps
- **Valid**: `.apk` in GitHub Releases OR a Google Play Store listing
- **Acceptable**: APK hosted on cdn.hackclub.com
- **Reject**: Source-only with no APK or store listing
- **Reject**: Google Drive link to APK — use cdn.hackclub.com or GitHub Releases instead

## iOS apps
- **Valid**: TestFlight link or App Store listing
- **Note**: If the developer lacks an Apple Developer account, this is not a review exception (Hack Club's team account is available via Amber)

## APIs
- **Valid**: Browser-based interactive API docs — Swagger UI, Redoc, Scalar, RapiDoc, or similar endpoint explorer
- **Requirement**: API must already be deployed (not local-only), with per-endpoint documentation and example requests/responses
- **Note**: Documented test credentials / API keys for trying endpoints are acceptable and encouraged
- **Reject**: No testable endpoint or documentation-only with no live API

## Games
- **Valid**: Web build (playable in browser), itch.io page, or GitHub Releases with downloadable build
- **Reject**: Source-only with no playable or downloadable build

## Bots (Discord, Slack, Telegram, etc.)
- **Valid**: Bot is hosted and online 24/7 — Discord: server invite link; Slack: workspace invite or channel link where it's installed; Telegram: link that opens a conversation with the bot immediately
- **Requirement**: Commands should be documented (README or the demo channel/server)
- **Reject**: Bot requires the reviewer to host it themselves, or bot is offline

## Libraries / packages
- **Valid**: Published on npm, PyPI, crates.io, LuaRocks, Maven Central, or equivalent package manager — the demo link should be the package page URL
- **Reject**: GitHub Releases as the only distribution — libraries must be on a real package manager
- **Requirement**: README must include a usage example showing how other developers would use it
- **Preferred**: A demo project or playground showing the library in use

## Browser extensions
- **Valid**: Published in the Chrome Web Store, Firefox Add-ons, or equivalent store
- **Acceptable**: Packaged `.crx` (Chrome), `.xpi` (Firefox), or `.vsix` (VS Code) file in GitHub Releases, with clear install instructions in the README — the demo link should point to the release

## Userscripts
- **Valid**: Published on Tampermonkey or GreasyFork (a proper install/update system)
- **Reject**: Raw `.js` or `.txt` file on GitHub with no userscript platform listing

## Hardware projects
- **Valid**: Video of the physical build working (inputs and outputs demonstrated), uploaded to YouTube or included in the GitHub repo/release
- **Valid**: For projects not physically built: GitHub release containing PCB design/schematic/wiring diagram plus a walkthrough demo (simulation like Wokwi only if no physical version exists)
- **Acceptable**: Breadboard builds, but only with a clear wiring diagram
- **Reject**: Lapse of just "messing around" with breadboards; pure simulations (unless the project is firmware-only)
- **Reject**: Google Drive video links — upload to YouTube or the repo instead
- **Note**: If physically built, firmware is required in the repo; schematic is optional. If NOT physically built (digital-only), a schematic is required
- **Note**: Development must be tracked with Hackatime or Lapse; if a case is included in the repo it should be printed/buildable

## CLI tools
- **Preferred**: Published on a package manager — npm, PyPI, crates.io, brew, or Go's `go install` from a tagged GitHub repo
- **Valid**: Pre-compiled binary in GitHub Releases with the exact install/run command in the README
- **Reject**: Demo video alone — need actual executable in GitHub Releases or published package
- **Reject**: Source-only (reviewer must not have to clone, install dependencies, and build)
- **Reject**: Link to a single source file or a zip of source — not a valid demo
- **Reject**: Repo URL used as demo URL — must have a release or package listing

## VR projects
- **Action**: Always flag for human review — do not attempt automated demo validation
- **Reject**: Demo video alone is not acceptable

## AI / ML / LLM projects
- **Reject**: Hugging Face Spaces, Google Colab, or Kaggle notebooks as the demo — these require running cells or external accounts
- **Valid**: A standalone interface for the AI — web app, CLI tool, or desktop app (self-hosted deployment, cloud-hosted API, or packaged application)
- **Valid**: Browser-based inference (WebLLM, Transformers.js) for small local models
- **Requirement**: Custom/local models must be bundled or auto-downloaded — reviewers must not manually fetch `.gguf`/`.safetensors` files or edit code to run the model

## Game mods
- **Minecraft — Valid**: Modrinth or CurseForge page, OR a GitHub Release containing the mod's `.jar`
- **Minecraft — Requirement**: Supported game versions, supported loaders (Fabric, Paper, etc.), and dependencies must be listed on the mod page and README; config file path documented if the mod has one
- **Other games — Valid**: Mod page on a popular registry such as Thunderstore or Nexus Mods, with dependencies and target game version listed
- **Other games — Note**: If the game is paid, a video demo should be included in the README or mod page

## 3D models / CAD projects
- **Valid**: Published model page on Printables, MakerWorld, or a similar platform, including print files AND a photo of the physically printed (and assembled) model
- **Requirement**: The repo must contain the editor files (`.f3d`, `.blend`, `.shapr`, etc. — Onshape link in the README if Onshape was used) and print files (`.obj`, `.step`, `.stl`, `.3mf`), plus pictures of the model and a proper README
- **Requirement**: The model must actually be 3D printed — no printed photo means not shippable; time tracked with a Hackatime-supported editor or Lapse
- **Reject**: Google Drive links for models or videos
- **Reject**: Only STL files in repo with no visual demo or printed photo
- **Reject**: Models made in Tinkercad

## Esolangs
- **Preferred**: Interactive playground or web REPL
- **Acceptable**: Detailed installation instructions with syntax guide
