import itertools
import re

import pytest

from clanker.review.reject_message import (
    ORDER,
    RejectContext,
    compose_reject_message,
    raw_readme_url,
)

CTX = RejectContext(
    submitter="duxredux",
    repo_url="https://github.com/a/b",
    readme_url="https://github.com/a/b/blob/main/README.md",
    project_type="web_app",
    banner_label="code_screenshot",
    bad_hosts=["render_free"],
    ai_style_file=True,
)
REASONS = [r for r in ORDER if r != "ai_readme_thin"]

# Tells that make text read as machine-written, or claims we can't honestly make.
AI_TELLS = re.compile(
    r"—|additionally|furthermore|moreover|i hope this helps|great job|delve|"
    r"\bwhen i (tried|tested|clicked|opened)|\bi (tested|tried|clicked)",
    re.I,
)


@pytest.mark.parametrize("reason", REASONS)
def test_every_reason_renders_cleanly(reason):
    for seed in ("a", "b", "c", "d"):
        msg = compose_reject_message([reason], CTX, seed)
        assert not AI_TELLS.search(msg), msg
        assert "#ask-the-shipwrights" in msg
        assert "{" not in msg and "}" not in msg
        assert not re.search(r"[.!?] [a-z]", msg), msg  # sentence case after sentence ends


def test_same_seed_same_message_and_seeds_vary_wording():
    msg = compose_reject_message(["ai_code"], CTX, "cert-1")
    assert msg == compose_reject_message(["ai_code"], CTX, "cert-1")
    variants = {compose_reject_message(["ai_code"], CTX, f"cert-{i}") for i in range(30)}
    assert len(variants) > 5


def test_many_issues_become_bullets_and_readme_reasons_merge():
    msg = compose_reject_message(["readme_not_raw", "ai_code", "banner_bad"], CTX, "x")
    assert msg.count("\n- ") == 3
    merged = compose_reject_message(["ai_readme", "readme_thin"], CTX, "x")
    assert merged.lower().count("readme") <= 2
    assert "\n- " not in merged


def test_all_pairs_stay_short_and_clean():
    for a, b in itertools.combinations(REASONS, 2):
        msg = compose_reject_message([a, b], CTX, f"{a}{b}")
        assert len(msg) < 700
        assert not AI_TELLS.search(msg), msg


def test_raw_readme_url_conversion():
    assert raw_readme_url("https://github.com/o/r/blob/dev/docs/README.md", None) == (
        "https://raw.githubusercontent.com/o/r/refs/heads/dev/docs/README.md"
    )
    assert raw_readme_url("https://github.com/o/r", None) is None


def test_unknown_reasons_only_raises():
    with pytest.raises(ValueError):
        compose_reject_message(["nope"], CTX, "x")


def test_caps_at_three_issues():
    msg = compose_reject_message(
        ["readme_not_raw", "ai_code", "ai_undeclared", "ai_readme", "banner_bad"], CTX, "x"
    )
    assert msg.count("\n- ") == 3


def test_no_awkward_joins_across_many_seeds():
    combos = [["needs_api_key"], ["ai_undeclared"], ["ai_code"], ["demo_broken"],
              ["ai_code", "ai_readme", "ai_undeclared"], ["banner_bad", "ai_undeclared"],
              ["readme_not_raw"], ["demo_broken", "ai_code"]]
    for reasons in combos:
        for i in range(40):
            msg = compose_reject_message(reasons, CTX, f"s{i}")
            assert not re.search(r"Unfortunately please|project, but your project", msg), msg
            assert not re.search(r"fix it\. Fix it", msg, re.I), msg
            assert not re.search(r", [A-Z][a-z]+ (idea|project)", msg[:40]), msg
