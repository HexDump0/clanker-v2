"""Non-GitHub repo hosts: URL helpers, the packet README fallback, first-layer rules, video."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from clanker.config import Settings
from clanker.forges import fetch_readme, is_raw_file_url, parse_repo, raw_readme_url
from clanker.review.first_layer import FirstLayerResult
from clanker.review.packet import build_packet
from clanker.review.reject_message import ORDER, RejectContext, compose_reject_message
from clanker.review.runner import ReviewRunner
from clanker.review.video.template_director import RejectVideoInputs, plan_scenes
from tests.conftest import make_cert
from tests.test_first_layer import jev_answers, make_reviewer

GITLAB = "https://gitlab.com/IHateGitHub/fleeting-prev"
NOT_GITHUB = {"status": "not_github", "cached": False, "markdown": ""}


@pytest.mark.parametrize(
    ("url", "kind", "path"),
    [
        ("https://github.com/o/r", "github", "o/r"),
        ("https://github.com/o/r.git", "github", "o/r"),
        ("https://raw.githubusercontent.com/o/r/main/README.md", "github", "o/r"),
        ("https://gitlab.com/o/r/-/blob/main/README.md", "gitlab", "o/r"),
        ("https://gitlab.com/group/sub/r", "gitlab", "group/sub/r"),
        ("https://gitlab.example.org/team/r/-/raw/HEAD/x", "gitlab", "team/r"),
        ("https://codeberg.org/o/r/src/branch/main/README.md", "gitea", "o/r"),
        ("https://bitbucket.org/o/r/src/HEAD/README.md", "bitbucket", "o/r"),
        ("https://git.sr.ht/~u/r/tree/HEAD/item/README.md", "sourcehut", "~u/r"),
    ],
)
def test_parse_repo(url, kind, path):
    repo = parse_repo(url)
    assert repo is not None and (repo.kind, repo.path) == (kind, path)


@pytest.mark.parametrize(
    "url", ["https://example.com/o/r", "https://github.com/o", "https://git.sr.ht/u/r", "", None]
)
def test_parse_repo_rejects_unknown(url):
    assert parse_repo(url) is None


@pytest.mark.parametrize(
    ("url", "raw"),
    [
        ("https://raw.githubusercontent.com/o/r/main/README.md", True),
        ("https://github.com/o/r/blob/main/README.md", False),
        ("https://gitlab.com/o/r/-/raw/HEAD/README.md", True),
        ("https://gitlab.com/o/r/-/blob/HEAD/README.md", False),
        ("https://codeberg.org/o/r/raw/branch/main/README.md", True),
        ("https://codeberg.org/o/r/src/branch/main/README.md", False),
        ("https://bitbucket.org/o/r/raw/HEAD/README.md", True),
        ("https://git.sr.ht/~u/r/blob/HEAD/README.md", True),
        ("https://git.sr.ht/~u/r/tree/HEAD/item/README.md", False),
    ],
)
def test_is_raw_file_url(url, raw):
    assert is_raw_file_url(url) is raw


def test_raw_readme_url_per_forge():
    assert raw_readme_url("https://gitlab.com/o/r/-/blob/dev/README.md", None) == (
        "https://gitlab.com/o/r/-/raw/dev/README.md"
    )
    assert raw_readme_url("https://codeberg.org/o/r/src/branch/main/README.md", None) == (
        "https://codeberg.org/o/r/raw/main/README.md"
    )
    assert raw_readme_url(None, GITLAB) == f"{GITLAB}/-/raw/HEAD/README.md"
    # GitHub keeps its old behaviour: only a blob link can be converted with confidence.
    assert raw_readme_url("https://github.com/o/r", None) is None


async def test_fetch_readme_skips_html_pages_and_tries_candidates():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path.endswith("/-/blob/main/README.md"):
            html = {"content-type": "text/html"}
            return httpx.Response(200, text="<html>page</html>", headers=html)
        if request.url.path.endswith("/-/raw/main/README.md"):
            return httpx.Response(404)
        if request.url.path.endswith("/-/raw/HEAD/README.md"):
            return httpx.Response(200, text="# Fleeting", headers={"content-type": "text/plain"})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as web:
        found = await fetch_readme(GITLAB, f"{GITLAB}/-/blob/main/README.md", web)

    assert found == ("# Fleeting", f"{GITLAB}/-/raw/HEAD/README.md")
    assert seen[0] == f"{GITLAB}/-/raw/main/README.md"  # converted link first


async def gitlab_packet(client, dashboard, monkeypatch, fetched, readme_url=None):
    dashboard.readme = NOT_GITHUB
    dashboard.details["c1"] = {
        **make_cert("c1"),
        "repoUrl": GITLAB,
        "readmeUrl": readme_url or f"{GITLAB}/-/raw/HEAD/README.md",
    }

    async def fake_fetch(repo_url, readme_url, web):
        if isinstance(fetched, Exception):
            raise fetched
        return fetched

    monkeypatch.setattr("clanker.review.packet.fetch_readme", fake_fetch)
    return await build_packet(client, "c1")


async def test_packet_fetches_non_github_readme(client, dashboard, monkeypatch):
    source = f"{GITLAB}/-/raw/HEAD/README.md"
    packet = await gitlab_packet(client, dashboard, monkeypatch, ("# Fleeting\nan app", source))
    prompt = packet.to_prompt()
    assert packet.readme == "# Fleeting\nan app"
    assert "## README (fetched from the repo host)" in prompt
    assert f"Source: {source}" in prompt


async def test_gitlab_readme_is_not_flagged_missing_or_not_raw(client, dashboard, monkeypatch):
    packet = await gitlab_packet(
        client, dashboard, monkeypatch, ("# Fleeting\nan app", f"{GITLAB}/-/raw/HEAD/README.md")
    )
    result = await make_reviewer(jev_answers()).review(packet)
    assert result.verdict != "REJECT"
    assert result.facts["readme_url_is_raw"] and result.facts["repo_host"] == "gitlab"


async def test_unreachable_forge_never_rejects_for_readme(client, dashboard, monkeypatch):
    packet = await gitlab_packet(client, dashboard, monkeypatch, httpx.ConnectError("down"))
    assert packet.readme_unverified
    assert "not verified" in packet.to_prompt()
    result = await make_reviewer(jev_answers(readme_thin=0.99, ai_readme=0.99)).review(packet)
    assert result.verdict == "NEEDS_HUMAN"
    assert "couldn't reach the repo host to read the README" in result.unsure


async def test_missing_readme_rejects_once_not_also_thin(client, dashboard, monkeypatch):
    packet = await gitlab_packet(client, dashboard, monkeypatch, None)
    result = await make_reviewer(jev_answers(readme_thin=0.99)).review(packet)
    assert result.reasons == ["no_readme"]


async def test_gitlab_blob_readme_link_gets_gitlab_raw_fix(client, dashboard, monkeypatch):
    blob = f"{GITLAB}/-/blob/main/README.md"
    packet = await gitlab_packet(
        client, dashboard, monkeypatch, ("# Fleeting\nan app", blob), readme_url=blob
    )
    result = await make_reviewer(jev_answers()).review(packet)
    assert result.reasons == ["readme_not_raw"]
    assert f"{GITLAB}/-/raw/main/README.md" in (result.message or "")
    assert "raw.githubusercontent.com" not in (result.message or "")


def test_reject_message_generic_raw_hint_for_unconvertible_forge_link():
    ctx = RejectContext(
        submitter="x", repo_url="https://bitbucket.org/o/r", readme_url="https://bitbucket.org/o/r"
    )
    message = compose_reject_message(["readme_not_raw"], ctx, "seed")
    assert "raw" in message and "github" not in message.lower()


def test_video_scenes_use_the_repos_forge():
    ctx = RejectContext(submitter="x", repo_url=GITLAB, readme_url=None, project_type="web_app")
    inputs = RejectVideoInputs(
        ctx=ctx,
        repo_url=GITLAB,
        flagged_code={"style.css": "body{}"},
        readme_markdown="# Fleeting",
    )
    specs = plan_scenes(["ai_code", "readme_thin", "no_source"], inputs, "seed")
    urls = [spec.url for spec in specs]
    assert urls == [  # message order: missing source first
        GITLAB,
        f"{GITLAB}/-/blob/HEAD/style.css",
        f"{GITLAB}/-/blob/HEAD/README.md",
    ]


# ai_readme_thin is a message-only merge of two reasons, never produced by the rules.
@pytest.mark.parametrize("reason", [r for r in ORDER if r != "ai_readme_thin"])
def test_every_reject_reason_gets_a_scene_without_any_pages(reason):
    # No repo, no demo, no README: nothing live to capture, still one scene (a text card).
    specs = plan_scenes([reason], RejectVideoInputs(ctx=RejectContext(submitter="x")), "s")
    assert len(specs) == 1 and specs[0].reason == reason
    assert specs[0].url is None and specs[0].card_lines and specs[0].title


async def test_runner_makes_a_card_video_when_no_page_can_be_shown(monkeypatch, tmp_path):
    packet = SimpleNamespace(
        cert=SimpleNamespace(
            project_name="P", description="", repo_url=None, demo_url=None, readme_url=None
        ),
        stardance_url=None,
        readme_source=None,
    )
    result = FirstLayerResult(
        verdict="REJECT",
        reasons=["no_readme"],
        answers={},
        facts={},
        project_type="Other",
        message="please add a README",
        video_inputs=RejectVideoInputs(ctx=RejectContext(submitter="x")),
    )
    rendered: list = []

    async def fake_packet(client, cert_id, tools=None):
        return packet

    async def fake_pdf(*args, **kwargs):
        return None

    async def fake_video(**kwargs):
        rendered.append(kwargs)
        return SimpleNamespace(video=SimpleNamespace(path=kwargs["output_path"]))

    monkeypatch.setattr("clanker.review.runner.build_packet", fake_packet)
    monkeypatch.setattr("clanker.review.runner.generate_first_layer_pdf", fake_pdf)
    monkeypatch.setattr("clanker.review.runner.generate_reject_video", fake_video)
    reviewer = SimpleNamespace(review=lambda p: _done(result))
    runner = ReviewRunner(
        first_layer=reviewer,  # type: ignore[arg-type]
        client=object(),  # type: ignore[arg-type]
        settings=Settings(_env_file=None, video_enabled=True, pdf_dir=tmp_path),
    )

    outcome = await runner.review_cert("c1")

    assert outcome.reject_message == "please add a README"
    assert rendered and rendered[0]["reasons"] == ["no_readme"]
    assert outcome.video_error is None


async def _done(value):
    return value
