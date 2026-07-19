"""Annotated review walkthrough videos (VideoScript -> recorded MP4)."""

from clanker.review.video.models import Scene, SceneTarget, VideoScript
from clanker.review.video.recorder import RecordingResult, VideoError, record_video_script

__all__ = [
    "RecordingResult",
    "Scene",
    "SceneTarget",
    "VideoError",
    "VideoScript",
    "record_video_script",
]
