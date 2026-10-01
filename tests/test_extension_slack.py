from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from clanker.config import Settings
from clanker.results import ResultStore
from clanker.service import review_for_extension
from clanker.shipwrights import CertSummary
from tests.conftest import make_cert
from tests.test_announcer import make_announcer
from tests.test_extension_api import make_outcome


async def test_announce_review_request_is_one_quiet_message_with_thread_note():
    announcer, slack = make_announcer()
    cert = CertSummary.model_validate(make_cert("c1"))
    ts = await announcer.announce_review_request(cert, rereview=True)
    assert ts == "111.222"
    assert slack.chat_postMessage.call_count == 2  # no separate "New ship" ping headline
    parent, note = (c.kwargs for c in slack.chat_postMessage.call_args_list)
    assert "Re-review requested: Project c1" in json.dumps(parent["attachments"])
    assert note["thread_ts"] == "111.222" and "Re-review requested" in note["text"]


def make_ctx(tmp_path, announcer, review):
    cert = CertSummary.model_validate(make_cert("c1"))
    return SimpleNamespace(
        settings=Settings(shipwrights_session="x", results_dir=tmp_path),
        client=SimpleNamespace(get_certification=AsyncMock(return_value=cert)),
        runner=SimpleNamespace(review_cert=review),
        announcer=announcer,
    )


async def test_extension_review_announces_then_posts_outcome(tmp_path):
    announcer = SimpleNamespace(
        announce_review_request=AsyncMock(return_value="9.9"),
        post_outcome=AsyncMock(),
        post_failure=AsyncMock(),
    )
    outcome = make_outcome("c1")
    ctx = make_ctx(tmp_path, announcer, AsyncMock(return_value=outcome))
    await review_for_extension(ctx, "c1")
    assert announcer.announce_review_request.await_args.kwargs == {"rereview": False}
    assert announcer.post_outcome.await_args.args[1:] == (outcome, "9.9")


async def test_extension_re_request_is_flagged_as_rereview(tmp_path):
    ResultStore(tmp_path).save_outcome(make_outcome("c1"))
    announcer = SimpleNamespace(
        announce_review_request=AsyncMock(return_value="9.9"),
        post_outcome=AsyncMock(),
        post_failure=AsyncMock(),
    )
    await review_for_extension(make_ctx(tmp_path, announcer, AsyncMock()), "c1")
    assert announcer.announce_review_request.await_args.kwargs == {"rereview": True}


async def test_failed_review_posts_failure_and_reraises(tmp_path):
    announcer = SimpleNamespace(
        announce_review_request=AsyncMock(return_value="9.9"),
        post_outcome=AsyncMock(),
        post_failure=AsyncMock(),
    )
    ctx = make_ctx(tmp_path, announcer, AsyncMock(side_effect=RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        await review_for_extension(ctx, "c1")
    announcer.post_failure.assert_awaited_once_with("9.9")
    announcer.post_outcome.assert_not_awaited()


async def test_slack_down_does_not_block_the_review(tmp_path):
    announcer = SimpleNamespace(
        announce_review_request=AsyncMock(side_effect=RuntimeError("slack down")),
        post_outcome=AsyncMock(),
        post_failure=AsyncMock(),
    )
    review = AsyncMock(return_value=make_outcome("c1"))
    await review_for_extension(make_ctx(tmp_path, announcer, review), "c1")
    review.assert_awaited_once_with("c1")
    announcer.post_outcome.assert_not_awaited()


async def test_manual_review_flag_goes_in_the_ship_thread_with_the_note():
    announcer, slack = make_announcer()
    await announcer.post_manual_review(
        "c1", "Project c1", parent_ts="5.5", note="it has a README", wrong_reasons=["no README"]
    )
    kwargs = slack.chat_postMessage.call_args.kwargs
    assert kwargs["thread_ts"] == "5.5"
    assert "Clanker got this one wrong, please review manually" in kwargs["text"]
    assert "no README" in kwargs["text"] and "it has a README" in kwargs["text"]


async def test_flag_manual_review_uses_the_stored_thread(tmp_path):
    from clanker.service import flag_manual_review

    store = ResultStore(tmp_path)
    store.save_outcome(make_outcome("c1"))
    store.set_slack_ts("c1", "7.7")
    record = store.set_feedback("c1", "wrong", note="n", wrong_checks=["no_readme"])
    announcer = SimpleNamespace(post_manual_review=AsyncMock())
    await flag_manual_review(SimpleNamespace(announcer=announcer), record)
    kwargs = announcer.post_manual_review.await_args.kwargs
    assert kwargs["parent_ts"] == "7.7" and kwargs["wrong_reasons"] == ["no README"]
    await flag_manual_review(SimpleNamespace(announcer=None), record)  # no Slack: no-op
