#!/usr/bin/env python3
"""Render a review-video bundle with the vision director or a checked-in plan."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from clanker.config import load_settings
from clanker.review.models import VideoEvidence
from clanker.review.video.director import VisionDirector
from clanker.review.video.models import VideoPlan, VideoProject
from clanker.review.video.pipeline import generate_review_video


class PlannedDirector:
    def __init__(self, plan: VideoPlan) -> None:
        self._plan = plan
        self.model_calls = 0
        self.last_usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    async def direct(self, project, evidence, captures) -> VideoPlan:
        return self._plan


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="JSON containing project and evidence")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument(
        "--director-plan",
        type=Path,
        help="Use a saved VideoPlan instead of making the one vision-model call.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    project = VideoProject.model_validate(payload["project"])
    evidence = [VideoEvidence.model_validate(item) for item in payload["evidence"]]
    if args.director_plan:
        director = PlannedDirector(
            VideoPlan.model_validate_json(args.director_plan.read_text(encoding="utf-8"))
        )
    else:
        director = VisionDirector(load_settings())
    work_dir = args.work_dir or Path("data/video-runs") / args.input.stem
    result = await generate_review_video(
        project=project,
        evidence=evidence,
        director=director,
        work_dir=work_dir,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "video": str(result.video.path),
                "manifest": str(result.manifest_path),
                "duration_seconds": result.video.duration_seconds,
                "size_bytes": result.video.size_bytes,
                "capture_failures": result.capture_failures,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
