from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import httpx
import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from clanker.config import Settings
from clanker.review.agent import (
    build_chat_instructions,
    build_model_settings,
    build_review_instructions,
    create_review_agent,
)
from clanker.review.browser import RenderResult, render_page
from clanker.review.models import (
    CheckResult,
    ChecksResult,
    CheckStatus,
    ReviewOutput,
    ReviewVerdict,
)
from clanker.review.packet import build_packet
from clanker.review.pdf import generate_review_pdf
from clanker.review.runner import PrivateContextLeakError, _guard_private_context
from clanker.review.tools import ReviewTools, _extract_stardance_project
from clanker.review.vision import PageRenderer, build_vision_model_settings
from tests.conftest import make_cert


def make_checks(**overrides: CheckResult) -> ChecksResult:
    default = CheckResult(status=CheckStatus.PASS, details="ok")
    fields = {name: default for name in ChecksResult.model_fields}
    fields.update(overrides)
    return ChecksResult(**fields)


def make_review(**overrides) -> ReviewOutput:
    kwargs = dict(
        verdict=ReviewVerdict.APPROVE,
        project_type="Web App",
        checks=make_checks(),
        reasoning="All checks passed. The project is solid.",
    )
    kwargs.update(overrides)
    return ReviewOutput(**kwargs)


def test_checks_as_pdf_rows_covers_full_rubric():
    rows = make_checks(
        demo_validity=CheckResult(status=CheckStatus.FAIL, details="demo is a Drive link")
    ).as_pdf_rows()
    assert len(rows) == 13
    by_name = {r["name"]: r for r in rows}
    assert by_name["demo_validity"]["status"] == "fail"
    assert by_name["pre_event_commits"]["status"] == "pass"


async def test_build_packet_prompt(client, dashboard):
    dashboard.details["c1"] = {
        **make_cert("c1"),
        "aiDeclaration": "Used Copilot for boilerplate",
        "reviews": [
            {
                "id": "r1",
                "certId": "c1",
                "verdict": "REJECTED",
                "comment": "README too thin",
                "createdAt": "2026-07-01T00:00:00.000Z",
            }
        ],
    }
    packet = await build_packet(client, "c1")
    prompt = packet.to_prompt()
    assert "cert id: c1" in prompt
    assert "Used Copilot for boilerplate" in prompt
    assert "REJECTED: README too thin" in prompt
    assert "# Hi" in prompt  # cached README included


async def test_packet_includes_attempts_notes_templates_but_not_ai_summary(client, dashboard):
    private_note = "Investigate the unusual ownership evidence before deciding."
    fixture = Path(__file__).parent / "fixtures" / "dashboard_cert_detail.json"
    dashboard.details["c1"] = json.loads(fixture.read_text(encoding="utf-8"))
    dashboard.feedback_templates["shared"] = [
        {"id": "t1", "title": "Functionality", "body": "Explain the broken feature."}
    ]

    packet = await build_packet(client, "c1")
    prompt = packet.to_prompt()

    assert private_note in prompt
    assert packet.private_context == [private_note]
    assert "Submission attempts and review history" in prompt
    assert "The primary feature did not work" in prompt
    assert "Resubmit with the missing functionality" in prompt
    assert "Explain the broken feature" in prompt
    assert "Dashboard AI says reject immediately" not in prompt
    assert "ai_summary" not in packet.cert.model_dump()
    assert "aiSummary" not in packet.cert.model_dump(by_alias=True)


async def test_build_packet_prefetches_tree_languages_and_stardance(client, dashboard):
    dashboard.details["c1"] = {**make_cert("c1"), "externalId": "5257"}

    def github_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/git/trees/HEAD"):
            tree = [{"path": "index.html", "type": "blob"}, {"path": "src", "type": "tree"}]
            return httpx.Response(200, json={"tree": tree})
        if path.endswith("/languages"):
            return httpx.Response(200, json={"HTML": 1234, "CSS": 567})
        return httpx.Response(404)

    def web_handler(request: httpx.Request) -> httpx.Response:
        assert "stardance.hackclub.com" in request.url.host
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=(
                '<html><head><meta property="og:title" content="My Project"></head>'
                "<body>devlog: built the thing</body></html>"
            ),
        )

    tools = ReviewTools()
    tools._github = httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(github_handler)
    )
    tools._web = httpx.AsyncClient(transport=httpx.MockTransport(web_handler))

    packet = await build_packet(client, "c1", tools=tools)
    prompt = packet.to_prompt()

    assert "## Repo structure (pre-fetched" in prompt
    assert "HTML (1234 bytes)" in prompt
    assert "- index.html" in prompt
    assert "## Stardance ship page (pre-fetched" in prompt
    assert "title: My Project" in prompt
    assert "devlog: built the thing" in prompt
    await tools.aclose()


async def test_build_packet_without_tools_skips_enrichment(client, dashboard):
    dashboard.details["c1"] = make_cert("c1")
    packet = await build_packet(client, "c1")
    prompt = packet.to_prompt()
    assert packet.tree is None and packet.languages is None and packet.stardance is None
    assert "pre-fetched" not in prompt


async def test_fetch_page_text_reports_reachability():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html"}, text="<html><body>hi there</body></html>"
        )

    tools = ReviewTools()
    tools._web = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    payload = json.loads(await tools.fetch_page_text("https://example.up.railway.app/"))
    assert payload["ok"] is True
    assert payload["reachable"] is True
    assert payload["status_code"] == 200
    assert payload["final_url"] == "https://example.up.railway.app/"
    assert payload["flags"] == ["railway"]
    assert "hi there" in payload["text"]
    await tools.aclose()


@pytest.mark.parametrize(
    "configured_cookie",
    ["current-session-token", "_stardance_session_4=current-session-token"],
)
async def test_stardance_fetch_sends_current_cookie_name(configured_cookie):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["cookie"] == "_stardance_session_4=current-session-token"
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text='<meta property="og:title" content="Ship"><body>One devlog</body>',
        )

    tools = ReviewTools(stardance_session=configured_cookie)
    tools._web = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    payload = json.loads(
        await tools.fetch_stardance_project(
            "https://stardance.hackclub.com/admin/certification/ship/123"
        )
    )
    assert payload["ok"] is True
    assert payload["summary"]["title"] == "Ship"
    await tools.aclose()


def test_stardance_parser_returns_structured_deduplicated_history():
    def card(devlog_id: str, created_at: str, text: str) -> str:
        return (
            '<div data-feed-engagement-post-type-value="Post::Devlog" '
            f'data-card-link-url-value="/projects/42/devlogs/{devlog_id}">'
            f'<time datetime="{created_at}"></time>'
            f'<div class="feed-post-card__body markdown-content">{text}</div>'
            '<img class="feed-post-card__avatar" src="/avatar.png">'
            f'<img class="feed-post-card__image" src="/media/{devlog_id}.png">'
            "</div>"
        )

    html = (
        '<meta property="og:title" content="Project by @maker | Stardance">'
        '<meta property="og:url" content="https://stardance.hackclub.com/projects/42">'
        '<meta name="author" content="maker">'
        '<img class="project-show__banner-image" src="/assets/profile/default-banner.png">'
        '<strong class="project-show__stats-num">3</strong>'
        '<span class="project-show__stats-label">Devlogs</span>'
        '<strong class="project-show__stats-num">12.5</strong>'
        '<span class="project-show__stats-label">Total hours</span>'
        + card("3", "2026-08-03T00:00:00Z", "Newest")
        + card("2", "2026-08-02T00:00:00Z", "Middle")
        + card("1", "2026-08-01T00:00:00Z", "Oldest")
        + card("3", "2026-08-03T00:00:00Z", "Newest")
    )

    data = _extract_stardance_project(html, max_devlogs=2)
    assert data["summary"]["project_id"] == "42"
    assert data["summary"]["banner_is_default"] is True
    assert data["summary"]["total_hours"] == 12.5
    assert [item["id"] for item in data["devlogs"]] == ["3", "1"]
    assert data["devlogs"][0]["media"] == [
        {"type": "image", "url": "https://stardance.hackclub.com/media/3.png"}
    ]
    assert data["completeness"] == {
        "total_devlogs": 3,
        "parsed_devlogs": 3,
        "returned_devlogs": 2,
        "truncated": True,
        "selection": "newest_and_oldest",
    }


async def test_stardance_rejects_lookalike_host():
    tools = ReviewTools(stardance_session="secret")
    payload = json.loads(
        await tools.fetch_stardance_project("https://stardance.hackclub.com.evil.test/project")
    )
    assert payload["ok"] is False
    assert "Not a Stardance URL" in payload["error"]
    await tools.aclose()


async def test_stardance_cookie_never_follows_cross_origin_redirect():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://evil.test/steal"})

    tools = ReviewTools(stardance_session="secret")
    tools._web = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    payload = json.loads(
        await tools.fetch_stardance_project(
            "https://stardance.hackclub.com/admin/certification/ship/123"
        )
    )
    assert payload["ok"] is False
    assert payload["error_category"] == "request_failed"
    assert len(requests) == 1
    assert requests[0].headers["cookie"] == "_stardance_session_4=secret"
    await tools.aclose()


async def test_fetch_one_stardance_devlog():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                '<div data-feed-engagement-post-type-value="Post::Devlog" '
                'data-card-link-url-value="/projects/42/devlogs/7">'
                '<time datetime="2026-08-01T00:00:00Z"></time>'
                '<div class="feed-post-card__body">Built the launch flow.</div>'
                '<video class="feed-post-card__video" src="/launch.mp4"></video>'
                "</div>"
            ),
        )

    tools = ReviewTools(stardance_session="secret")
    tools._web = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    payload = json.loads(
        await tools.fetch_stardance_devlog(
            "https://stardance.hackclub.com/projects/42/devlogs/7"
        )
    )
    assert payload["ok"] is True
    assert payload["devlog"]["id"] == "7"
    assert payload["devlog"]["text"] == "Built the launch flow."
    assert payload["devlog"]["media"][0]["type"] == "video"
    await tools.aclose()


def test_private_note_guard_blocks_verbatim_public_output():
    note = "Investigate private authorship evidence before approving this project."
    review = make_review(reasoning=f"The internal note said: {note}")
    with pytest.raises(PrivateContextLeakError):
        _guard_private_context(review, [note])


def test_private_note_guard_allows_independent_public_evidence():
    review = make_review(reasoning="The repository and live demo satisfy every check.")
    _guard_private_context(review, ["Investigate private authorship evidence before approval."])


@pytest.mark.parametrize(
    ("url", "expected_flag"),
    [
        ("https://demo.streamlit.app/", "streamlit"),
        ("https://project.trycloudflare.com/", "cloudflared"),
        ("https://project.duckdns.org/", "duckdns"),
    ],
)
async def test_url_checks_flag_current_disallowed_hosts(url, expected_flag):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text="ok")

    tools = ReviewTools()
    tools._web = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    payload = json.loads(await tools.check_url(url))
    assert payload["flags"] == [expected_flag]
    await tools.aclose()


async def test_url_checks_flag_disallowed_redirect_destination():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "https://redirected.streamlit.app/"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="ok")

    tools = ReviewTools()
    tools._web = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    )
    payload = json.loads(await tools.fetch_page_text("https://example.com/demo"))
    assert payload["final_url"] == "https://redirected.streamlit.app/"
    assert payload["flags"] == ["streamlit"]
    await tools.aclose()


async def test_render_page_rejects_invalid_url():
    result = await render_page("ftp://nope")
    assert result.ok is False
    assert "Invalid URL" in (result.error or "")


async def test_render_tool_without_renderer_errors():
    tools = ReviewTools()
    payload = json.loads(await tools.render_page("https://example.com"))
    assert payload["ok"] is False
    assert "not available" in payload["error"]
    await tools.aclose()


async def test_page_renderer_describes_screenshot(monkeypatch):
    async def fake_render(url, *, load_timeout):
        return RenderResult(
            ok=True,
            url=url,
            final_url=url,
            status_code=200,
            text="Welcome to my site",
            viewport_mostly_empty=False,
            screenshot=b"\xff\xd8fake-jpeg",
        )

    monkeypatch.setattr("clanker.review.vision.render_page", fake_render)
    vision = Agent(TestModel(custom_output_text="A landing page with a large purple heading."))
    renderer = PageRenderer(make_settings(), agent=vision)

    payload = await renderer.render_payload("https://demo.example.com")
    assert payload["ok"] is True
    assert payload["reachable"] is True
    assert payload["rendered_text"] == "Welcome to my site"
    assert payload["screenshot_description"] == "A landing page with a large purple heading."


class FakeRenderer:
    async def render_json(self, url: str) -> str:
        return json.dumps(
            {
                "ok": True,
                "url": url,
                "final_url": url,
                "status_code": 200,
                "reachable": True,
                "viewport_mostly_empty": False,
                "rendered_text": "Welcome to my site",
                "screenshot_description": "A landing page with a large purple heading.",
            }
        )


async def test_build_packet_includes_demo_render(client, dashboard):
    dashboard.details["c1"] = make_cert("c1")
    tools = ReviewTools(renderer=FakeRenderer())
    not_found = httpx.MockTransport(lambda request: httpx.Response(404))
    tools._github = httpx.AsyncClient(base_url="https://api.github.com", transport=not_found)
    tools._web = httpx.AsyncClient(transport=not_found)

    packet = await build_packet(client, "c1", tools=tools)
    prompt = packet.to_prompt()
    assert "## Demo page render (pre-fetched" in prompt
    assert "A landing page with a large purple heading." in prompt
    assert "Welcome to my site" in prompt
    await tools.aclose()


async def test_render_page_real_chromium():
    body = (
        b"<html><body><h1>Hello Render</h1>"
        b"<p>from a real browser, with enough visible text on the page that the "
        b"mostly-empty viewport heuristic does not trip on this fixture</p>"
        b"</body></html>"
    )

    async def handle(reader, writer):
        await reader.read(2048)
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        result = await render_page(f"http://127.0.0.1:{port}/")
    finally:
        server.close()
        await server.wait_closed()

    if not result.ok and "install" in (result.error or "").lower():
        pytest.skip(f"chromium not installed: {result.error}")
    assert result.ok, result.error
    assert result.status_code == 200
    assert "Hello Render" in result.text
    assert result.viewport_mostly_empty is False
    assert result.screenshot and result.screenshot[:2] == b"\xff\xd8"  # JPEG magic


@pytest.mark.skipif(shutil.which("typst") is None, reason="typst not installed")
async def test_generate_pdf(tmp_path):
    review = make_review(
        verdict=ReviewVerdict.REJECT,
        required_fixes=["Add a real README"],
        special_flags=["AI UNDISCLOSED"],
    )
    path = await generate_review_pdf(
        review,
        output_path=tmp_path / "out.pdf",
        project_name="Test Project",
        project_desc="A test",
        repo_url="https://github.com/x/y",
        demo_url="https://example.com",
    )
    assert path.exists()
    assert path.read_bytes()[:5] == b"%PDF-"


def test_review_instructions_reference_real_tools():
    text = build_review_instructions()
    # every tool named in the prompts must exist on the toolset (v1 pain point #11)
    import re

    tools = ReviewTools()
    tool_names = {fn.__name__ for fn in tools.all()}
    referenced = set(re.findall(r"review_[a-z_]+", text))
    assert referenced <= tool_names, f"prompt references unknown tools: {referenced - tool_names}"
    assert "review_generate_pdf" not in text


def test_review_and_chat_prompts_include_current_shipwright_rules():
    review = build_review_instructions()
    chat = build_chat_instructions()

    for text in (review, chat):
        assert "Streamlit Community Cloud" in text
        assert "submitted to another competition, game jam, or hackathon" in text
        assert "OAuth option" in text
        assert "completely vibe-coded generic project" in text
        assert "GitHub Actions workflow" in text
        assert "does **not** satisfy this proof-video requirement" in text

    assert "GitHub Releases as the distribution" in review
    assert "OR a GitHub Release containing the mod's `.jar`" not in review
    assert "Models made in Tinkercad" not in review


def test_chat_prompt_handles_vibe_coder_cases_internally():
    chat = build_chat_instructions()

    assert "private Shipwrights help threads" in chat
    assert "speaking to Shipwrights staff" in chat
    assert "strictly forbidden from using that protocol" in chat
    assert "Never send, simulate," in chat
    assert "shipper-facing message with the `?<message>` syntax" in chat
    assert "DRAFT FOR HUMAN TO SEND" in chat
    assert "Keep that hostility completely out of every shipper-facing draft" in chat
    assert "Never compare commit author names or emails" in chat
    assert "Do not invoke `run_review` automatically" in chat


def make_settings(**overrides) -> Settings:
    # _env_file=None keeps the developer's real .env out of the test.
    return Settings(
        _env_file=None,
        shipwrights_session="x",
        openrouter_api_key="k",
        hackclub_api_key="h",
        **overrides,
    )


def test_default_review_and_vision_models_are_current():
    settings = make_settings()
    assert settings.model_name == "deepseek/deepseek-v4-flash-0731"
    assert settings.vision_model_name == "qwen/qwen3.8-flash"


def test_vision_disables_reasoning_and_uses_dynamic_routing():
    settings = build_vision_model_settings(make_settings())
    assert settings["openrouter_reasoning"] == {"enabled": False}
    assert settings["openrouter_provider"]["sort"] == "throughput"


def test_dynamic_provider_routing_applies_to_openrouter_and_hackclub():
    expected = {
        "sort": "throughput",
        "preferred_max_latency": 2.0,
        "max_price": {"prompt": 0.5, "completion": 1.0},
        "require_parameters": True,
        "allow_fallbacks": True,
    }

    unpinned = build_model_settings(make_settings())
    assert unpinned["openrouter_provider"] == expected

    hackclub = build_model_settings(make_settings(ai_provider="hackclub"))
    assert hackclub["openrouter_provider"] == expected


def test_explicit_provider_pin_remains_available_as_an_override():
    pinned = build_model_settings(
        make_settings(
            openrouter_provider_only="alibaba, cerebras",
            openrouter_allow_fallbacks=False,
        )
    )
    assert pinned["openrouter_provider"] == {
        "only": ["alibaba", "cerebras"],
        "allow_fallbacks": False,
    }


async def test_review_agent_uses_prompted_output_and_keeps_tools_optional():
    tools = ReviewTools()
    agent = create_review_agent(make_settings(), tools)
    model = TestModel(custom_output_text=make_review().model_dump_json())

    result = await agent.run("Review this project", model=model)

    assert result.output == make_review()
    request = model.last_model_request_parameters
    assert request is not None
    assert request.output_mode == "prompted"
    assert request.output_tools == []
    assert {tool.name for tool in request.function_tools} == {
        tool.__name__ for tool in tools.all()
    }


async def test_web_search_requires_key():
    tools = ReviewTools()
    payload = json.loads(await tools.web_search("what is somehost.io"))
    assert payload["ok"] is False
    assert "not available" in payload["error"]
    await tools.aclose()


async def test_web_search_returns_trimmed_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://ai.hackclub.com/proxy/v1/exa/search"
        assert request.headers["authorization"] == "Bearer hc-key"
        body = json.loads(request.content)
        assert body["query"] == "is somehost.io a tunnel service"
        assert body["numResults"] == 3
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Somehost docs",
                        "url": "https://somehost.io/docs",
                        "publishedDate": "2026-01-01",
                        "text": "Somehost tunnels local ports to public URLs.",
                        "id": "ignored",
                    }
                ],
                "costDollars": {"total": 0.005},
            },
        )

    tools = ReviewTools(hackclub_ai_key="hc-key")
    tools._web = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    payload = json.loads(
        await tools.web_search("is somehost.io a tunnel service", num_results=3)
    )
    assert payload["ok"] is True
    assert payload["results"] == [
        {
            "title": "Somehost docs",
            "url": "https://somehost.io/docs",
            "published_date": "2026-01-01",
            "snippet": "Somehost tunnels local ports to public URLs.",
        }
    ]
    await tools.aclose()
