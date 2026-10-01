# Video is always attached on reject (no checkbox)

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** fix

- Human: the video is always necessary, so the "Attach Clanker's video" checkbox is gone. Rejecting from the Clanker page always uploads
  Clanker's video when the ship has one; if the video can't be loaded the reject is aborted with an error.
- Kept one exception: ships marked "Clanker got it wrong" don't attach it (the video shows the wrong reasons). The Review card shows a
  "Video" row saying which case applies ("attached" / "not attached (Clanker was wrong)" / "none for this ship").
- `extension/judgements.js`, `page.css`, README. Re-ran the Chromium E2E: presign, PUT, attach, then the REJECTED review, as before.
