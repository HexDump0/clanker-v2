from __future__ import annotations

import asyncio
import json
import shutil

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
from clanker.review.tools import ReviewTools
from clanker.review.vision import PageRenderer
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


def make_settings(**overrides) -> Settings:
    # _env_file=None keeps the developer's real .env out of the test.
    return Settings(
        _env_file=None,
        shipwrights_session="x",
        openrouter_api_key="k",
        hackclub_api_key="h",
        **overrides,
    )


def test_provider_pin_only_for_openrouter():
    pinned = build_model_settings(make_settings(openrouter_provider_only="alibaba, cerebras"))
    assert pinned["openrouter_provider"] == {
        "only": ["alibaba", "cerebras"],
        "allow_fallbacks": False,
    }

    unpinned = build_model_settings(make_settings())
    assert "openrouter_provider" not in unpinned

    hackclub = build_model_settings(
        make_settings(ai_provider="hackclub", openrouter_provider_only="alibaba")
    )
    assert "openrouter_provider" not in hackclub


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
