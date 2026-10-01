"""The screen-recording style reject video: plan only (no browser, no ffmpeg)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from clanker.review.video.browser_compositor import PASTE_OVER, build_browser_composition
from clanker.review.video.models import (
    Box,
    ComposedScene,
    DirectedScene,
    EvidenceCapture,
    HighlightResolution,
    SceneRole,
    VideoPlan,
    VideoProject,
)

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)


def scene(tmp_path, sid, url, *, page_height=None, box=None):
    shot = tmp_path / f"{sid}.png"
    shot.write_bytes(PNG)
    page = None
    if page_height:
        page = tmp_path / f"{sid}.page.png"
        page.write_bytes(PNG)
    capture = EvidenceCapture(
        evidence_id=sid,
        requested_url=url,
        final_url=url,
        captured_at=datetime.now(UTC),
        screenshot_path=shot,
        viewport_width=1280,
        viewport_height=720,
        page_screenshot_path=page,
        page_height=page_height,
    )
    directed = DirectedScene(
        evidence_id=sid, role=SceneRole.PRIMARY, title=f"Title {sid}", explanation="Do the fix."
    )
    return ComposedScene(
        directed=directed,
        capture=capture,
        target_box=box,
        resolution=HighlightResolution.RESOLVED if box else HighlightResolution.NOT_REQUESTED,
    )


HEADING = Box(x=370, y=420, width=400, height=40)


def build(tmp_path, seed="seed"):
    scenes = [
        scene(tmp_path, "readme", "https://example.com/a"),
        scene(tmp_path, "code", "https://github.com/o/r/blob/abc/" + "x" * 60, page_height=2400),
        scene(
            tmp_path, "heading", "https://example.com/b", box=HEADING
        ),
    ]
    plan = VideoPlan(headline="h", summary="s", scenes=[s.directed for s in scenes])
    project = VideoProject(project_name="P", verdict="REJECTED", required_fixes=["Fix A", "Fix B"])
    return build_browser_composition(project, plan, scenes, seed)


def timeline(document: str) -> dict:
    return json.loads(re.search(r"const T=(\{.*?\});\n", document, re.S).group(1))


def test_same_cert_same_video_different_cert_different_motion(tmp_path):
    a, dur_a = build(tmp_path, "cert-1")
    b, _ = build(tmp_path, "cert-1")
    c, _ = build(tmp_path, "cert-2")
    assert a == b
    assert timeline(a)["moves"] != timeline(c)["moves"]
    assert 15 < dur_a < 60


def test_screen_recording_choreography(tmp_path):
    t = timeline(build(tmp_path)[0])
    assert [s["url"] for s in t["scenes"]][0] == "example.com/a"
    short, long = t["typing"][0], t["typing"][1]
    assert len(set(short["times"])) == len(short["text"])  # typed key by key
    assert len(long["text"]) > PASTE_OVER and set(long["times"]) == {0.0}  # pasted
    assert any(s["s"] == 1 for s in t["scrolls"])  # skims the tall code page
    (sel,) = t["selects"]
    assert sel["s"] == 2 and sel["w"] == 400  # drag-selects the target line
    assert t["final"]["items"] == ["Fix A", "Fix B"]
    times = [m["t0"] for m in t["moves"]]
    assert times == sorted(times)


def test_no_explainer_tells(tmp_path):
    document, _ = build(tmp_path)
    for tell in ("01 / 03", "Required<br>fixes", "kicker", "letter-spacing:.14em"):
        assert tell not in document
