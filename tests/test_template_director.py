import re

from clanker.review.reject_message import RejectContext, compose_reject_message
from clanker.review.video.template_director import RejectVideoInputs, plan_scenes

INPUTS = RejectVideoInputs(
    ctx=RejectContext(readme_url="https://github.com/a/b/blob/main/README.md"),
    repo_url="https://github.com/a/b",
    commit="abc1234",
    readme_markdown="# 🌌 Cool Thing\n\nstuff",
    flagged_code={
        "style.css": "/* ===== HEADER ===== */\n.hero { background: linear-gradient(red, blue); }"
    },
    project_name="untitled",
)


def test_ai_scenes_point_at_nothing_and_ask_for_real_rework():
    specs = plan_scenes(["ai_code", "ai_readme", "ai_undeclared"], INPUTS, "seed")
    ai = [s for s in specs if s.reason in ("ai_code", "ai_readme")]
    assert len(ai) == 2
    for spec in ai:
        assert spec.highlight is None  # highlighting a line implies "delete it and you're done"
        assert re.search(r"won't be enough|from scratch|yourself", spec.caption)
        assert not re.search(r"emoji|comment", spec.caption, re.I)


def test_scene_order_merge_and_cap():
    specs = plan_scenes(
        ["readme_not_raw", "ai_code", "ai_undeclared", "ai_readme", "readme_thin", "untitled"],
        INPUTS,
        "seed",
    )
    assert [s.reason for s in specs] == ["untitled", "readme_not_raw", "ai_code"]
    assert all(s.url is None for s in specs[:2])  # text cards: no public page to capture
    assert specs[2].url == "https://github.com/a/b/blob/abc1234/style.css"


def test_messages_never_suggest_cosmetic_ai_fixes():
    for i in range(40):
        msg = compose_reject_message(["ai_code", "ai_readme"], RejectContext(), f"s{i}")
        assert not re.search(r"remove (the )?(emoji|comment)", msg, re.I), msg


# --- generate_reject_video (no browser, no model) -------------------------------------------

import json  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402

from clanker.review.video.capture import CaptureError  # noqa: E402
from clanker.review.video.compositor import RenderedVideo  # noqa: E402
from clanker.review.video.models import EvidenceCapture  # noqa: E402
from clanker.review.video.pipeline import VideoPipelineError, generate_reject_video  # noqa: E402


def _fake_capture(tmp_path, evidence_id, url=""):
    shot = tmp_path / f"{evidence_id}.png"
    shot.write_bytes(b"png")
    return EvidenceCapture(
        evidence_id=evidence_id,
        requested_url=url,
        final_url=url,
        captured_at=datetime.now(UTC),
        screenshot_path=shot,
        viewport_width=1280,
        viewport_height=720,
    )


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    calls = {"cards": [], "captured": []}

    async def fake_capture(item, output_dir, policy=None):
        if "README" in item.url:
            raise CaptureError("blocked by a bot wall")
        calls["captured"].append(item.id)
        return _fake_capture(tmp_path, item.id, item.url)

    async def fake_card(spec, output_dir):
        calls["cards"].append((spec.id, list(spec.card_lines)))
        return _fake_capture(tmp_path, spec.id)

    async def fake_render(document, duration, output_path, music_path=None):
        calls["document"] = document
        output_path.write_bytes(b"mp4")
        return RenderedVideo(output_path, duration, 3)

    monkeypatch.setattr("clanker.review.video.pipeline.capture_evidence", fake_capture)
    monkeypatch.setattr("clanker.review.video.pipeline.render_text_card", fake_card)
    monkeypatch.setattr("clanker.review.video.pipeline.render_composition", fake_render)
    return calls


async def test_reject_video_uses_no_model_and_falls_back_to_text_cards(fakes, tmp_path):
    result = await generate_reject_video(
        reasons=["readme_not_raw", "ai_code", "ai_readme"],
        inputs=INPUTS,
        seed="cert-1",
        work_dir=tmp_path / "run",
        output_path=tmp_path / "v.mp4",
    )
    manifest = json.loads(result.manifest_path.read_text())
    assert [s["directed"]["evidence_id"] for s in manifest["scenes"]] == [
        "readme-link",
        "ai-code",
        "ai-readme",
    ]
    assert fakes["captured"] == ["ai-code"]
    # raw-link card by design; the README capture failed, so it falls back to a card showing the URL
    assert fakes["cards"][0][0] == "readme-link"
    assert fakes["cards"][1] == ("ai-readme", ["https://github.com/a/b/blob/abc1234/README.md"])
    stages = {a["stage"]: a for a in manifest["audit"]}
    assert stages["template_director"]["model_calls"] == 0
    assert "text_card_fallback" in stages
    assert "Rebuild the design and code yourself" in fakes["document"]
    assert "primary" not in fakes["document"].lower().split("<script>")[0].split("</style>")[1]


async def test_reject_video_without_mappable_reasons_raises(fakes, tmp_path):
    with pytest.raises(VideoPipelineError, match="no reject reason"):
        await generate_reject_video(
            reasons=["something_new"],
            inputs=INPUTS,
            seed="x",
            work_dir=tmp_path / "run",
            output_path=tmp_path / "v.mp4",
        )
