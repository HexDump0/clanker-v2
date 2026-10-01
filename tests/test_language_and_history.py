"""README language and pre-event (started before June 1, not declared as an update) rules."""

from __future__ import annotations

import httpx
import pytest

from clanker.review.first_layer.evidence import _github_history
from clanker.review.first_layer.language import guess_readme_language, readme_not_english
from clanker.review.first_layer.report import build_report_data
from tests.test_first_layer import jev_answers, make_reviewer, packet_for

SPANISH = (
    "# Mi Proyecto\n\nEste es un proyecto que hice para aprender a programar. La aplicación "
    "permite a los usuarios crear tareas y organizarlas por categorías. Para usar el proyecto, "
    "primero tienes que instalar las dependencias con npm y luego ejecutar el servidor. Me gustó "
    "mucho hacer este proyecto porque aprendí cómo funciona React y cómo se conecta con una base "
    "de datos.\n```bash\nnpm install\nnpm run dev\n```\n"
)
CHINESE = (
    "# 我的项目\n\n这是一个用来管理日常任务的网页应用。用户可以创建、编辑和删除任务，并且可以按照"
    "优先级进行排序。我在这个项目中学习了很多关于前端开发的知识，包括组件化设计和状态管理。使用方法："
    "先安装依赖，然后运行开发服务器，就可以在浏览器中打开应用了。"
)
ENGLISH_TERSE = (
    "# TaskBoard\n\n## Features\n- Drag and drop\n- Dark mode\n- Keyboard shortcuts\n"
    "- Offline sync\n- Markdown notes\n- Tags, filters, search\n## Stack\nReact Vite Tailwind "
    "Zustand IndexedDB Workbox Vitest Playwright ESLint Prettier Husky GitHub Actions Vercel "
    "Sentry Plausible Analytics Storybook Chromatic Docker Postgres Redis Prisma tRPC"
)


@pytest.mark.parametrize(("markdown", "language"), [(SPANISH, "spanish"), (CHINESE, "cjk")])
def test_non_english_readmes_are_caught(markdown, language):
    guess = readme_not_english(markdown)
    assert guess is not None and guess.language == language


def test_english_and_unclear_readmes_pass():
    assert readme_not_english(ENGLISH_TERSE) is None  # few stopwords, but no other language
    assert readme_not_english("# Hola\n\nUn proyecto.") is None  # too short to judge
    assert guess_readme_language("This is my app. You can use it to track your tasks. " * 8).english


def test_linked_english_version_is_enough():
    assert readme_not_english("[English version](README.en.md)\n\n" + SPANISH) is None


async def test_spanish_readme_rejects_without_ai_or_thin_reasons(client, dashboard):
    dashboard.readme = {"status": "ok", "cached": True, "markdown": SPANISH}
    packet = await packet_for(client, dashboard)
    result = await make_reviewer(jev_answers(ai_readme=0.99, readme_thin=0.99)).review(packet)
    assert result.reasons == ["readme_not_english"]
    assert "English" in (result.message or "")


HISTORY = {"total_commits": 40, "pre_cutoff_commits": 12, "oldest_own_commit": "2025-11-02"}


@pytest.mark.parametrize(
    ("own_before", "declared", "rejects"),
    [(12, None, True), (12, "Added multiplayer since the last ship", False), (2, None, False)],
)
async def test_pre_event_rule(client, dashboard, own_before, declared, rejects):
    packet = await packet_for(client, dashboard, updatedProject=declared)
    history = {**HISTORY, "pre_cutoff_own_commits": own_before}
    result = await make_reviewer(jev_answers(), history=history).review(packet)
    assert ("pre_event_undeclared" in result.reasons) is rejects
    if rejects:
        assert "updated project" in (result.message or "")
        evidence = build_report_data(result, packet)["reasons"][0]["evidence"]
        assert evidence == [
            "12 of 40 commits before June 1 (oldest 2025-11-02); not declared as an updated project"
        ]


async def test_github_history_counts_only_the_owners_old_commits():
    def commit(login, date):
        return {"author": {"login": login} if login else None, "commit": {"author": {"date": date}}}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("until"):
            return httpx.Response(
                200,
                json=[
                    commit("me", "2026-05-02T10:00:00Z"),
                    commit(None, "2026-04-01T10:00:00Z"),  # unlinked email: counts as owner
                    commit("template-author", "2024-01-01T10:00:00Z"),
                ],
            )
        last = '<https://api.github.com/repos/me/r/commits?per_page=1&page=57>; rel="last"'
        newest = [commit("me", "2026-09-01T00:00:00Z")]
        return httpx.Response(200, json=newest, headers={"link": last})

    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)
    ) as gh:
        history = await _github_history(gh, "/repos/me/r", "abc123", "me")

    assert history == {
        "total_commits": 57,
        "pre_cutoff_commits": 3,
        "pre_cutoff_own_commits": 2,
        "oldest_own_commit": "2026-04-01",
    }
