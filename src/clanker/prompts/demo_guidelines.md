# Demo Validation Guidelines

Rules for what constitutes a valid demo link or artifact per project type. Used by the checks agent for the `demo_validity` check. These rules validate the link type and accessibility only — actual demo testing is for human reviewers.

## General rejection rules (apply to ALL project types)

- **Reject**: Google Drive links (`drive.google.com`) — not acceptable as demo links. Use YouTube for videos, cdn.hackclub.com for files.
- **Reject**: Google Colab links (`colab.research.google.com`) — not acceptable as demos. Build a CLI/GUI wrapper and package as executable or website.
- **Reject**: Hugging Face links (`huggingface.co`) — not acceptable as demo hosting. Build a self-hosted deployment, API, or packaged application.
- **Reject**: Demo link pointing to a zip of source code — not a valid demo.
- **Reject**: Demo link pointing to a single source file (e.g., `.py`, `.js`) — not a valid demo.
- **Reject**: Demo link that is the repo URL itself (unless it's a library/package with clear install instructions).

## Web apps
- **Valid**: Live URL on GitHub Pages, Vercel, Netlify, or similar static/serverless hosting
- **Reject**: ngrok, cloudflared, DuckDNS links
- **Reject**: Render (*.onrender.com), Railway (*.up.railway.app) — free-tier hosting on Render/Railway is not accepted — unreliable, slow cold starts, no guarantee of indefinite hosting
- **Reject**: localhost URLs or local-only instructions without a live deployment
- **Reject**: localhost URLs or references to localhost in README/demo — must be replaced with actual domain

## Desktop apps (executables)
- **Valid**: `.exe`, `.app`, `.deb`, `.dmg`, `.AppImage`, or similar binaries in GitHub Releases
- **Reject**: Source-only with no prebuilt binary
- **Reject**: Demo video alone is not acceptable — need actual executable in GitHub Releases
- **Reject**: Link to a directory in the repo instead of a GitHub Release

## Android apps
- **Valid**: `.apk` in GitHub Releases OR a Google Play Store listing
- **Acceptable**: APK hosted on cdn.hackclub.com
- **Reject**: Source-only with no APK or store listing
- **Reject**: Google Drive link to APK — use cdn.hackclub.com or GitHub Releases instead

## iOS apps
- **Valid**: TestFlight link
- **Note**: If the developer lacks an Apple Developer account, this is not a review exception

## APIs
- **Valid**: Swagger UI, interactive endpoint explorer, or documented live base URL
- **Reject**: No testable endpoint or documentation-only with no live API

## Games
- **Valid**: Web build (playable in browser), itch.io page, or GitHub Releases with downloadable build
- **Reject**: Source-only with no playable or downloadable build

## Bots (Discord, Telegram, etc.)
- **Valid**: Bot is hosted and online, with a link to the relevant server or channel
- **Reject**: Bot requires the reviewer to host it themselves

## Libraries / packages
- **Valid**: Published on npm, PyPI, crates.io, Maven Central, or equivalent package manager
- **Reject**: GitHub Releases as the only distribution — libraries must be on a real package manager
- **Preferred**: A demo project or playground showing the library in use

## Browser extensions
- **Valid**: Published in the Chrome Web Store, Firefox Add-ons, or equivalent store
- **Acceptable**: `.crx` or `.xpi` installable package if store publishing is unavailable

## Userscripts
- **Valid**: Published on Tampermonkey (GreasyFork) or similar userscript repository
- **Reject**: Plain `.js` file on GitHub with no userscript platform listing

## Hardware projects
- **Valid**: Completed PCB or schematic with fabrication files, video of the physical build in use
- **Reject**: Breadboard-only footage, hardware simulations (unless firmware-only for ESP32 or similar)
- **Reject**: Google Drive video links — upload to YouTube instead
- **Note**: If physically built, firmware is required; schematic is not required
- **Note**: For hardware demos, YouTube video is the preferred format

## CLI tools
- **Valid**: Compiled executable binary in GitHub Releases with setup/usage instructions
- **Valid**: Published package on PyPI, npm, crates.io, or equivalent package manager
- **Reject**: Demo video alone — need actual executable in GitHub Releases or published package
- **Reject**: Link to a Python file (.py) in the repo — not a valid demo
- **Reject**: Link to a zip of source code — not a valid demo
- **Reject**: Repo URL used as demo URL — must have a release or package listing

## VR projects
- **Action**: Always flag for human review — do not attempt automated demo validation
- **Reject**: Demo video alone is not acceptable

## AI / ML projects
- **Reject**: Hugging Face as the submission host
- **Reject**: Google Colab links — build a proper deployment
- **Valid**: Self-hosted deployment, cloud-hosted API, or packaged application

## Game mods
- **Preferred**: Modrinth, CurseForge, or equivalent mod platform
- **Discouraged**: GitHub Releases as the primary distribution path

## 3D models / CAD projects
- **Valid**: Demo video on YouTube, model files on Thingiverse or Printables
- **Reject**: Google Drive links for models or videos
- **Reject**: Only STL files in repo with no visual demo

## Esolangs
- **Preferred**: Interactive playground or web REPL
- **Acceptable**: Detailed installation instructions with syntax guide
