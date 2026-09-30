"""Fetch the human Shipwright verdict for each exported attempt (read-only Dashboard GETs).

A cert id *is* one submission attempt. We label each trace with the human review of that
same attempt, so a project that was rejected, fixed, and later approved is judged per
attempt and a newer approval never relabels an older rejection.

    uv run python evals/jev/fetch_labels.py
"""

from __future__ import annotations

import asyncio

from common import LABELS, TRACES, append_jsonl, read_jsonl

from clanker.config import load_settings
from clanker.shipwrights import ShipwrightsClient


async def main() -> None:
    done = {row["cert_id"] for row in read_jsonl(LABELS)}
    cert_ids = [t["cert_id"] for t in read_jsonl(TRACES) if t.get("cert_id")]
    todo = [c for c in dict.fromkeys(cert_ids) if c not in done]
    print(f"{len(todo)} certs to label")

    settings = load_settings()
    async with ShipwrightsClient.from_settings(settings) as client:
        for i, cert_id in enumerate(todo):
            try:
                cert = await client.get_certification(cert_id)
            except Exception as exc:  # label failures are data, not fatal
                append_jsonl(LABELS, {"cert_id": cert_id, "error": str(exc)})
                continue
            attempt = next((a for a in cert.attempts if a.id == cert_id), None)
            reviews = sorted(attempt.reviews if attempt else cert.reviews, key=lambda r: r.created_at)
            status = attempt.status.value if attempt else cert.status.value
            append_jsonl(
                LABELS,
                {
                    "cert_id": cert_id,
                    "attempt_status": status,
                    # First human verdict on this exact attempt is the label.
                    "human_verdict": reviews[0].verdict.value if reviews else None,
                    "human_comment": reviews[0].comment if reviews else None,
                    "human_reviewed_at": reviews[0].created_at.isoformat() if reviews else None,
                    "n_reviews": len(reviews),
                    "return_reason": attempt.return_reason if attempt else cert.return_reason,
                    "later_attempts": sum(
                        1
                        for a in cert.attempts
                        if attempt and a.created_at and attempt.created_at
                        and a.created_at > attempt.created_at
                    ),
                },
            )
            if (i + 1) % 20 == 0:
                print(f"{i + 1}/{len(todo)}")
            await asyncio.sleep(0.2)  # be gentle with the Dashboard


if __name__ == "__main__":
    asyncio.run(main())
