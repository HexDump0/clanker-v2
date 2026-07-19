"""Screenshot-first annotated review videos."""

from clanker.review.video.capture import CapturePolicy, capture_evidence
from clanker.review.video.director import VisionDirector
from clanker.review.video.models import (
    DirectedScene,
    EvidenceCapture,
    Scene,
    SceneTarget,
    VideoPlan,
    VideoProject,
    VideoScript,
)
from clanker.review.video.pipeline import VideoGenerationResult, generate_review_video
from clanker.review.video.recorder import RecordingResult, VideoError, record_video_script

__all__ = [
    "CapturePolicy",
    "DirectedScene",
    "EvidenceCapture",
    "RecordingResult",
    "Scene",
    "SceneTarget",
    "VideoError",
    "VideoGenerationResult",
    "VideoPlan",
    "VideoProject",
    "VideoScript",
    "VisionDirector",
    "capture_evidence",
    "generate_review_video",
    "record_video_script",
]
