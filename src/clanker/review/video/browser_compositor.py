# ruff: noqa: E501
"""Reject videos that look like a person's screen recording, not an explainer.

The older compositor (``compositor.py``) builds a polished explainer: title cards, a
dimmed spotlight box, numbered red-accent callouts. That reads as machine-made. This
one renders the same captured screenshots inside a plain browser window and drives it
the way a reviewer would: click the address bar, type or paste the link, wait for the
page, skim down with the mouse wheel, drag-select the line that matters. The text
overlay stays, as plain subtitles.

Everything is planned here in Python from a seeded RNG (same cert -> same video); the
page only plays the timeline back. No network, no model.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from clanker.review.video.models import ComposedScene, VideoPlan, VideoProject

WIDTH, HEIGHT = 1280, 720
TAB_H, TOOLBAR_H = 38, 42
CHROME_H = TAB_H + TOOLBAR_H
PAGE_H = HEIGHT - CHROME_H
OMNIBOX = (118, TAB_H + 6, 1040, 30)  # x, y, w, h
PASTE_OVER = 48  # longer links are pasted, not typed
READ_WPS = 3.0  # caption reading speed (words per second)


# 24x24 Material-style icon paths for the browser chrome (text glyphs like "←" render tiny
# and differ per font).
ICONS = {
    "back": "M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z",
    "forward": "M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z",
    "reload": "M17.65 6.35A7.958 7.958 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 "
    "6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 "
    "4.22 1.78L13 11h7V4l-2.35 2.35z",
    "close": "M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 "
    "19 19 17.59 13.41 12z",
    "add": "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
    "minimize": "M6 11.3h12v1.4H6z",
    "maximize": "M18 4H6c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 "
    "14H6V6h12v12z",
    "menu": "M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 "
    "2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z",
    "tune": "M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 "
    "4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z",
    "globe": "M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 "
    "2zm6.93 6h-2.95a15.65 15.65 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.92 8zM12 4.04c.83 1.2 1.48 "
    "2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36"
    ".26-2h3.38c-.08.66-.14 1.32-.14 2s.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 "
    "3.56A7.987 7.987 0 0 1 5.08 16zm2.95-8H5.08a7.987 7.987 0 0 1 4.33-3.56A15.65 15.65 0 0 0 "
    "8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 "
    "14H9.66c-.09-.66-.16-1.32-.16-2s.07-1.35.16-2h4.68c.09.65.16 1.32.16 2s-.07 1.34-.16 "
    "2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95a8.03 8.03 0 0 1-4.33 3.56zM16.36 14c.08-.66"
    ".14-1.32.14-2s-.06-1.34-.14-2h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z",
}


def _icon(name: str, size: int, color: str = "#5f6368", extra: str = "") -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" {extra}>'
        f'<path d="{ICONS[name]}" fill="{color}"/></svg>'
    )


def _data_url(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _display_url(url: str) -> str:
    return url.removeprefix("https://").removeprefix("http://").removeprefix("www.")


@dataclass
class _Plan:
    """The timeline the page plays back (all times in seconds)."""

    rng: random.Random
    t: float = 0.0
    x: float = 760.0
    y: float = 430.0
    scenes: list[dict] = field(default_factory=list)
    moves: list[dict] = field(default_factory=list)
    presses: list[list[float]] = field(default_factory=list)
    typing: list[dict] = field(default_factory=list)
    scrolls: list[dict] = field(default_factory=list)
    selects: list[dict] = field(default_factory=list)
    captions: list[dict] = field(default_factory=list)
    omni_selected: list[list[float]] = field(default_factory=list)
    loads: list[list[float]] = field(default_factory=list)

    def wait(self, lo: float, hi: float) -> None:
        self.t += self.rng.uniform(lo, hi)

    def move(self, x: float, y: float, speed: float = 1.0) -> None:
        """A curved, decelerating hand movement (Fitts-ish duration)."""
        dx, dy = x - self.x, y - self.y
        dist = math.hypot(dx, dy)
        if dist < 2:
            return
        dur = (0.26 + 0.12 * math.log2(1 + dist / 30)) * self.rng.uniform(0.85, 1.2) / speed
        # Bend the path sideways a little, like a wrist arc.
        nx, ny = -dy / dist, dx / dist
        bend = self.rng.uniform(0.04, 0.16) * dist * self.rng.choice((-1, 1))
        c1 = (self.x + dx * 0.3 + nx * bend, self.y + dy * 0.3 + ny * bend)
        c2 = (self.x + dx * 0.78 + nx * bend * 0.35, self.y + dy * 0.78 + ny * bend * 0.35)
        self.moves.append({"t0": self.t, "t1": self.t + dur, "p": [self.x, self.y, *c1, *c2, x, y]})
        self.t += dur
        self.x, self.y = x, y

    def click(self) -> None:
        down = self.rng.uniform(0.07, 0.12)
        self.presses.append([self.t, self.t + down])
        self.t += down + self.rng.uniform(0.05, 0.12)

    def open_url(self, url: str) -> None:
        """Click the address bar, type or paste the link, press Enter, wait for the page."""
        ox, oy, ow, oh = OMNIBOX
        self.move(ox + self.rng.uniform(140, 420), oy + oh / 2 + self.rng.uniform(-4, 4))
        self.click()
        start_sel = self.t
        self.wait(0.15, 0.35)
        text = _display_url(url)
        if len(text) > PASTE_OVER:  # ctrl+v
            self.omni_selected.append([start_sel, self.t])
            self.t += self.rng.uniform(0.12, 0.25)
            self.typing.append({"t0": self.t, "text": text, "times": [0.0] * len(text)})
            self.wait(0.25, 0.5)
        else:
            self.omni_selected.append([start_sel, self.t])
            times, k = [], 0.0
            for ch in text:
                times.append(k)
                k += self.rng.uniform(0.035, 0.085) + (
                    self.rng.uniform(0.08, 0.2) if ch in "./" and self.rng.random() < 0.3 else 0
                )
            self.typing.append({"t0": self.t, "text": text, "times": times})
            self.t += k + self.rng.uniform(0.15, 0.35)
        enter = self.t
        self.t += self.rng.uniform(0.55, 1.05)
        self.loads.append([enter, self.t])

    def scroll(self, scene: int, y0: float, y1: float) -> float:
        """Mouse-wheel bursts from y0 to y1 (page pixels); returns where it stopped."""
        pos, sign = y0, 1 if y1 > y0 else -1
        while abs(y1 - pos) > 4:
            step = min(abs(y1 - pos), self.rng.uniform(90, 240))
            dur = self.rng.uniform(0.16, 0.3)
            self.scrolls.append(
                {"s": scene, "t0": self.t, "t1": self.t + dur, "y0": pos, "y1": pos + sign * step}
            )
            pos += sign * step
            self.t += dur + self.rng.uniform(0.04, 0.28)
        return pos

    def read_pause(self) -> None:
        """Stop to read; the hand drifts along the text now and then."""
        if self.rng.random() < 0.6:
            self.move(
                min(1120.0, max(260.0, self.x + self.rng.uniform(-200, 200))),
                min(HEIGHT - 150.0, max(CHROME_H + 110.0, self.y + self.rng.uniform(-90, 90))),
                speed=0.6,
            )
        self.wait(0.5, 1.4)

    def browse(self, scene: int, height: float, pos: float, seconds: float) -> float:
        """Read down the page for about ``seconds``: scroll a chunk, pause, repeat. Now and
        then scroll back up to re-read; at the bottom, glance back up and stop."""
        bottom = max(0.0, height - PAGE_H)
        end = self.t + seconds
        while self.t < end:
            if bottom - pos < 30:
                if pos > 200 and self.rng.random() < 0.6:
                    self.read_pause()
                    pos = self.scroll(scene, pos, max(0.0, pos - self.rng.uniform(250, 600)))
                break
            self.read_pause()
            if pos > 300 and self.rng.random() < 0.15:
                pos = self.scroll(scene, pos, max(0.0, pos - self.rng.uniform(120, 260)))
                continue
            pos = self.scroll(scene, pos, min(bottom, pos + self.rng.uniform(200, 560)))
        return pos


def _caption_words(scene: ComposedScene) -> int:
    return len(f"{scene.directed.title} {scene.directed.explanation}".split())


def build_browser_composition(
    project: VideoProject, plan: VideoPlan, scenes: list[ComposedScene], seed: str
) -> tuple[str, float]:
    if not scenes:
        raise ValueError("cannot render a video without scenes")
    rng = random.Random(int(hashlib.sha256(f"browser:{seed}".encode()).hexdigest()[:16], 16))
    p = _Plan(rng=rng)
    p.wait(0.5, 0.9)  # recording starts on an empty new tab

    for index, scene in enumerate(scenes):
        capture = scene.capture
        tall = capture.page_screenshot_path and capture.page_screenshot_path.is_file()
        image = capture.page_screenshot_path if tall else capture.screenshot_path
        height = (capture.page_height if tall else capture.viewport_height) or HEIGHT
        url = capture.final_url or capture.requested_url
        if url:
            p.open_url(url)
        else:  # a locally rendered text card: no address to visit
            p.wait(0.3, 0.6)
            p.loads.append([p.t, p.t + 0.01])
            p.t += 0.01
        load = p.t
        p.scenes.append(
            {
                "img": _data_url(image),
                "h": height,
                "url": _display_url(url) if url else "",
                "title": (
                    capture.page_title
                    or (_display_url(url).split("/")[0] if url else "")
                    or scene.directed.title
                )[:60],
                "load": load,
            }
        )
        p.wait(0.35, 0.7)
        caption_at = p.t
        read_seconds = min(8.5, max(4.0, 1.6 + _caption_words(scene) / READ_WPS))
        read_until = caption_at + read_seconds
        # How long to go through the page: about the caption's reading time, plus a bit.
        browse_for = min(11.0, read_seconds + rng.uniform(1.0, 3.0))

        box = scene.target_box
        caption_pos = "bottom"
        if box is not None:
            # Bring the line into view if needed, then drag-select it.
            scroll_to = 0.0
            if box.y + box.height > PAGE_H - 150:
                scroll_to = min(max(0.0, box.y - PAGE_H * 0.35), max(0.0, height - PAGE_H))
                p.move(rng.uniform(560, 820), rng.uniform(300, 420))
                p.scroll(index, 0.0, scroll_to)
            y_on_screen = CHROME_H + box.y - scroll_to + box.height / 2
            p.move(box.x + rng.uniform(-3, 2), y_on_screen + rng.uniform(-2, 2))
            p.wait(0.1, 0.25)
            down = p.t
            drag = rng.uniform(0.35, 0.75)
            p.selects.append(
                {"s": index, "t0": down, "t1": down + drag,
                 "x": box.x, "y": box.y, "w": box.width, "h": box.height}
            )  # fmt: skip
            p.presses.append([down, down + drag])
            p.moves.append(
                {"t0": down, "t1": down + drag,
                 "p": [p.x, p.y, p.x + box.width * 0.3, p.y + 1, p.x + box.width * 0.8, p.y - 1,
                       box.x + box.width + rng.uniform(0, 4), p.y + rng.uniform(-2, 2)]}
            )  # fmt: skip
            p.x, p.y = box.x + box.width, p.y
            p.t = down + drag + rng.uniform(0.25, 0.5)
            p.move(p.x + rng.uniform(20, 70), p.y + rng.uniform(25, 70), speed=0.7)
            if y_on_screen > CHROME_H + PAGE_H * 0.55:
                caption_pos = "top"
            # Then keep reading below it for a bit.
            if height - PAGE_H - scroll_to > 120:
                p.browse(index, height, scroll_to, rng.uniform(2.5, 4.5))
        elif height > PAGE_H + 80:
            # Go through the page like someone reading it.
            p.move(rng.uniform(520, 820), rng.uniform(280, 440))
            p.browse(index, height, 0.0, browse_for)
        else:
            for _ in range(rng.randint(2, 3)):
                p.read_pause()

        end = max(read_until, p.t + rng.uniform(0.6, 1.1))
        p.captions.append(
            {"t0": caption_at, "t1": end, "title": scene.directed.title,
             "text": scene.directed.explanation, "pos": caption_pos}
        )  # fmt: skip
        p.t = end

    fixes = project.required_fixes or ["Fix the issues above"]
    p.wait(0.2, 0.4)
    final_at = p.t
    p.move(rng.uniform(900, 1100), rng.uniform(420, 560), speed=0.6)
    total = final_at + 3.0 + 0.6 * len(fixes)
    timeline = {
        "scenes": p.scenes,
        "moves": p.moves,
        "presses": p.presses,
        "typing": p.typing,
        "scrolls": p.scrolls,
        "selects": p.selects,
        "captions": p.captions,
        "omniSelected": p.omni_selected,
        "loads": p.loads,
        "final": {"t0": final_at, "items": fixes},
        "start": [p.moves[0]["p"][0], p.moves[0]["p"][1]] if p.moves else [760, 430],
        "duration": total,
    }
    return _document(timeline), total


def _document(timeline: dict) -> str:
    data = json.dumps(timeline).replace("</", "<\\/")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
* {{ box-sizing:border-box; }}
html,body {{ margin:0; width:{WIDTH}px; height:{HEIGHT}px; overflow:hidden; background:#fff;
  font-family:"Noto Sans","Segoe UI",Roboto,"Liberation Sans",Arial,sans-serif; }}
#tabs {{ position:absolute; left:0; top:0; width:100%; height:{TAB_H}px; background:#dfe1e5; }}
.tab {{ position:absolute; left:8px; bottom:0; width:240px; height:30px; background:#fff;
  border-radius:8px 8px 0 0; display:flex; align-items:center; gap:8px; padding:0 10px; font-size:12px; color:#3c4043; }}
.tab .title {{ flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.tab svg {{ flex:none; }}
.newtab {{ position:absolute; left:256px; top:7px; width:24px; height:24px; display:grid; place-items:center; }}
.winbtns {{ position:absolute; right:14px; top:0; height:{TAB_H}px; display:flex; align-items:center; gap:28px; }}
#bar {{ position:absolute; left:0; top:{TAB_H}px; width:100%; height:{TOOLBAR_H}px; background:#fff;
  border-bottom:1px solid #dadce0; }}
.nav {{ position:absolute; left:12px; top:0; height:{TOOLBAR_H}px; display:flex; align-items:center; gap:14px; }}
#omni {{ position:absolute; left:{OMNIBOX[0]}px; top:6px; width:{OMNIBOX[2]}px; height:{OMNIBOX[3]}px; border-radius:15px;
  background:#f1f3f4; display:flex; align-items:center; padding:0 14px; font-size:14px; color:#202124; gap:10px; }}
#omni.focus {{ background:#fff; box-shadow:0 0 0 2px #1a73e8 inset; }}
#omni svg {{ flex:none; }}
#url {{ white-space:pre; overflow:hidden; }} #url .rest {{ color:#5f6368; }}
#url.sel {{ background:#c8ddfb; }}
#url.ph {{ color:#80868b; }}
#caret {{ width:1px; height:17px; background:#202124; }}
.avatar {{ position:absolute; right:52px; top:10px; width:22px; height:22px; border-radius:50%; background:#8ab4c8; }}
.menu {{ position:absolute; right:16px; top:0; height:{TOOLBAR_H}px; display:flex; align-items:center; }}
#load {{ position:absolute; left:0; top:{CHROME_H - 2}px; height:2px; width:0; background:#1a73e8; }}
#view {{ position:absolute; left:0; top:{CHROME_H}px; width:{WIDTH}px; height:{PAGE_H}px; overflow:hidden; background:#fff; }}
.pg {{ position:absolute; left:0; top:0; width:{WIDTH}px; display:none; will-change:transform; }}
.pg img {{ display:block; width:{WIDTH}px; }}
.sel {{ position:absolute; background:rgba(66,133,244,.32); width:0; }}
#cap {{ position:absolute; left:50%; transform:translateX(-50%); max-width:880px; padding:12px 18px;
  background:rgba(20,20,22,.84); color:#fff; border-radius:8px; font-size:19px; line-height:1.4; opacity:0; }}
#cap b {{ font-weight:700; }}
#cap.bottom {{ bottom:34px; }} #cap.top {{ top:{CHROME_H + 26}px; }}
#cap ul {{ margin:6px 0 0; padding-left:22px; }} #cap li {{ margin:3px 0; }}
#cur {{ position:absolute; left:0; top:0; width:22px; height:22px; z-index:9; pointer-events:none; }}
#spin {{ width:14px; height:14px; border-radius:50%; border:2px solid #c6dafc; border-top-color:#1a73e8; display:none; }}
</style></head><body>
<div id="tabs"><div class="tab"><div id="spin"></div>{_icon("globe", 16, "#5f6368", 'id="fav"')}<div class="title" id="title">New Tab</div>{_icon("close", 16)}</div>
<div class="newtab">{_icon("add", 20)}</div><div class="winbtns">{_icon("minimize", 16)}{_icon("maximize", 14)}{_icon("close", 16)}</div></div>
<div id="bar"><div class="nav">{_icon("back", 20)}{_icon("forward", 20, "#bdc1c6")}{_icon("reload", 20)}</div>
<div id="omni">{_icon("tune", 16)}<span id="url" class="ph">Search or type a URL</span><span id="caret"></span></div>
<div class="avatar"></div><div class="menu">{_icon("menu", 20)}</div></div><div id="load"></div>
<div id="view"></div><div id="cap" class="bottom"></div>
<svg id="cur" viewBox="0 0 22 22"><path id="arrow" d="M3 2 L3 18 L7.2 14.2 L10 20.5 L12.6 19.3 L9.9 13.2 L15.5 13.2 Z" fill="#000" stroke="#fff" stroke-width="1.3" stroke-linejoin="round"/>
<path id="ibeam" d="M8 3 h6 M11 3 v16 M8 19 h6" stroke="#000" stroke-width="1.6" fill="none" style="display:none"/></svg>
<script>
const T={data};
const view=document.getElementById('view'), cap=document.getElementById('cap'), cur=document.getElementById('cur');
const urlEl=document.getElementById('url'), omni=document.getElementById('omni'), caret=document.getElementById('caret');
const pages=T.scenes.map(s=>{{const d=document.createElement('div');d.className='pg';
  d.innerHTML='<img src="'+s.img+'"><div class="sel"></div>';view.appendChild(d);return d;}});
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v)), ease=p=>1-Math.pow(1-p,3), easeIO=p=>p<.5?4*p*p*p:1-Math.pow(-2*p+2,3)/2;
const esc=s=>s.replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}})[c]);
function bez(q,u){{const a=1-u;return [a*a*a*q[0]+3*a*a*u*q[2]+3*a*u*u*q[4]+u*u*u*q[6], a*a*a*q[1]+3*a*a*u*q[3]+3*a*u*u*q[5]+u*u*u*q[7]];}}
function cursorAt(t){{let pos=T.start;for(const m of T.moves){{ if(t<m.t0) break;
  if(t<=m.t1){{return bez(m.p, ease(clamp((t-m.t0)/(m.t1-m.t0),0,1)));}} pos=[m.p[6],m.p[7]]; }}
  return [pos[0]+Math.sin(t*1.7)*0.8+Math.sin(t*3.1)*0.4, pos[1]+Math.cos(t*1.3)*0.7]; }}
function scene(t){{let i=-1;T.scenes.forEach((s,k)=>{{if(t>=s.load)i=k;}});return i;}}
function scrollY(i,t){{let y=0;for(const s of T.scrolls){{ if(s.s!==i||t<s.t0) continue;
  y = t>=s.t1 ? s.y1 : s.y0+(s.y1-s.y0)*easeIO((t-s.t0)/(s.t1-s.t0)); }} return y; }}
function within(list,t){{return list.some(r=>t>=r[0]&&t<r[1]);}}
function render(t){{
  const i=scene(t);
  pages.forEach((d,k)=>{{d.style.display=k===i?'block':'none';}});
  if(i>=0){{const y=scrollY(i,t);pages[i].style.transform='translateY('+(-y)+'px)';
    const sel=pages[i].querySelector('.sel');sel.style.width='0';
    for(const s of T.selects){{ if(s.s!==i||t<s.t0) continue; const p=clamp((t-s.t0)/(s.t1-s.t0),0,1);
      Object.assign(sel.style,{{left:s.x+'px',top:s.y+'px',height:s.h+'px',width:(s.w*p)+'px'}}); }}
    document.getElementById('title').textContent=T.scenes[i].title; }}
  // address bar: placeholder, current page, selected-for-replace, typing, loading
  let text=i>=0?T.scenes[i].url:'', focus=false, typing=null;
  for(const ty of T.typing){{ if(t>=ty.t0) typing=ty; }}
  const loading=T.loads.find(l=>t>=l[0]&&t<l[1]);
  const typed=typing && (i<0 || T.scenes[i].load<typing.t0);
  if(typed){{const n=typing.times.filter(x=>t-typing.t0>=x).length;text=typing.text.slice(0,n);focus=!loading;}}
  const selected=within(T.omniSelected,t);
  if(selected) focus=true;
  urlEl.className=(!text&&!selected)?'ph':(selected?'sel':'');
  if(!text && !selected) urlEl.textContent='Search or type a URL';
  else {{ const cut=text.indexOf('/'); urlEl.innerHTML = (focus||cut<0)? esc(text) : esc(text.slice(0,cut))+'<span class="rest">'+esc(text.slice(cut))+'</span>'; }}
  omni.className=focus?'focus':''; caret.style.opacity=(focus&&!selected&&Math.floor(t*2)%2===0)?1:0;
  // loading spinner + progress line
  const ld=document.getElementById('load'), sp=document.getElementById('spin'), fav=document.getElementById('fav');
  if(loading){{const p=(t-loading[0])/(loading[1]-loading[0]);ld.style.width=(WIDTH_*(.15+.8*ease(p)))+'px';ld.style.opacity=1;
    sp.style.display='block';fav.style.display='none';sp.style.transform='rotate('+(t*720)+'deg)';}}
  else {{ld.style.opacity=0;sp.style.display='none';fav.style.display='block';}}
  // caption / final list
  let c=null; for(const x of T.captions){{ if(t>=x.t0&&t<x.t1) c=x; }}
  if(t>=T.final.t0){{ cap.className='bottom'; cap.innerHTML='<b>To fix before reshipping:</b><ul>'+T.final.items.map(f=>'<li>'+esc(f)+'</li>').join('')+'</ul>';
    cap.style.opacity=clamp((t-T.final.t0)/.3,0,1); }}
  else if(c){{ cap.className=c.pos; cap.innerHTML='<b>'+esc(c.title)+'</b><br>'+esc(c.text);
    cap.style.opacity=Math.min(clamp((t-c.t0)/.25,0,1),clamp((c.t1-t)/.2,0,1)); }}
  else cap.style.opacity=0;
  // cursor
  const [x,y]=cursorAt(t), down=within(T.presses,t);
  const ox={OMNIBOX[0]}, oy={OMNIBOX[1]}, ow={OMNIBOX[2]}, oh={OMNIBOX[3]};
  const textCursor=(x>ox&&x<ox+ow&&y>oy&&y<oy+oh)||T.selects.some(s=>t>=s.t0-.15&&t<s.t1+.2);
  document.getElementById('arrow').style.display=textCursor?'none':'';
  document.getElementById('ibeam').style.display=textCursor?'':'none';
  cur.style.transform='translate('+(x-(textCursor?11:3))+'px,'+(y-(textCursor?11:2))+'px) scale('+(down?.9:1)+')';
}}
const WIDTH_={WIDTH};
let start=null;
function frame(now){{ if(start===null) start=now; render((now-start)/1000); requestAnimationFrame(frame); }}
render(0);
window.__clankerStart=()=>requestAnimationFrame(frame);
</script></body></html>"""
