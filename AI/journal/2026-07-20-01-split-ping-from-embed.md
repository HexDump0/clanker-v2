# Split the group ping off the ship embed to stop repeated pings

**Date:** 2026-07-20 · **Agent:** Claude (Opus 4.8) · **Type:** fix

## What was done
- Diagnosed why the pinged group got notified for *every* threaded message
  (running-review note, PDF, video) under a new-ship announcement.
- Root cause: the `cc @ping` mention lived inside the ship **embed attachment**,
  and that embed was the **thread parent**. Slack auto-follows anyone @mentioned
  in a thread parent, so they get notified of every subsequent reply in that
  thread. Confirmed against Slack's threads help doc ("you'll be notified of new
  replies if you started the thread, replied to it, or were mentioned").
- Reworked `announce_ship` per the human's requested design: post **two separate
  top-level messages**.
  1. Plain-text headline `New ship: <name> (<type>)` + `cc <ping>` — standalone,
     nothing threaded under it, so the group is pinged exactly once and never
     re-fires.
  2. The coloured embed with **no mention** — this is the thread parent for the
     running note / PDF / video, so those replies never re-ping.

## Why / decisions made
- A real Slack mention (`<@U…>` / `<!subteam^S…>`) always notifies + auto-follows;
  there's no "muted mention". The only reliable fix is to keep the mention off the
  thread parent and off every message that has replies after it.
- Removed the `cc` block from `_ship_attachment` (both initial post and the
  `chat_update` verdict render still use this builder, so the ping is now gone
  from both).
- Dropped the top-level `text=fallback` on the embed post and on the verdict
  `chat_update`, since the headline text now lives in its own message and the
  attachment already carries a `fallback`. Public contract of `announce_ship`
  (returns embed ts) and `post_outcome` (signature) is unchanged, so
  `service.py` needs no changes.

## Files touched
- `src/clanker/slack/announcer.py` — modified — split ping into standalone
  headline message; removed ping from embed; dropped redundant top-level text.
- `AI/journal/2026-07-20-01-split-ping-from-embed.md` — created — this entry.

## Open questions / for the human
- The headline and embed are now two independent channel messages (not linked).
  If you'd prefer them visually grouped, we could revisit, but linking them into
  one thread would reintroduce the follow-notification problem.

## Next steps
- Verify live in Slack that the group is pinged once (headline only) and the
  PDF/video threaded under the embed do not re-ping.
- Consider a regression test once the announcer gets a fake-Slack test harness.
