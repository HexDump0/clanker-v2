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
from clanker.review.video.pipeline import (
    VideoGenerationResult,
    generate_reject_video,
    generate_review_video,
)
from clanker.review.video.recorder import RecordingResult, VideoError, record_video_script
from clanker.review.video.template_director import RejectVideoInputs, TemplateDirector

__all__ = [
    "CapturePolicy",
    "DirectedScene",
    "EvidenceCapture",
    "RecordingResult",
    "RejectVideoInputs",
    "Scene",
    "SceneTarget",
    "TemplateDirector",
    "VideoError",
    "VideoGenerationResult",
    "VideoPlan",
    "VideoProject",
    "VideoScript",
    "VisionDirector",
    "capture_evidence",
    "generate_reject_video",
    "generate_review_video",
    "record_video_script",
]
