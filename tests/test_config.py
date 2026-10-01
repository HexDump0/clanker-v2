from __future__ import annotations

from re import search

from clanker.config import Settings, _httpx_excluded_urls


def test_httpx_exclusions_hide_only_pending_queue_polls():
    settings = Settings(_env_file=None)
    pattern = _httpx_excluded_urls(settings)

    assert search(
        pattern,
        "https://ds.shipwrights.dev/api/v1/workplaces/stardance/"
        "certifications?page=1&status=PENDING",
    )
    assert search(
        pattern,
        "https://ds.shipwrights.dev/api/v1/workplaces/stardance/"
        "certifications?status=PENDING&page=2",
    )
    assert not search(
        pattern,
        "https://ds.shipwrights.dev/api/v1/workplaces/stardance/certifications/c1",
    )
    assert not search(
        pattern,
        "https://ds.shipwrights.dev/api/v1/workplaces/stardance/"
        "certifications?page=1&status=APPROVED",
    )
    assert not search(pattern, "https://api.github.com/repos/hackclub/clanker")


def test_httpx_exclusions_preserve_existing_patterns_without_duplicates():
    settings = Settings(_env_file=None)
    first = _httpx_excluded_urls(settings, r"healthcheck$")
    second = _httpx_excluded_urls(settings, first)

    assert second == first
    assert second.startswith(r"healthcheck$,")


def test_video_music_is_off_by_default_and_can_be_enabled(monkeypatch):
    monkeypatch.delenv("VIDEO_MUSIC_ENABLED", raising=False)
    assert Settings(_env_file=None).video_music_enabled is False
    monkeypatch.setenv("VIDEO_MUSIC_ENABLED", "true")
    assert Settings(_env_file=None).video_music_enabled is True
