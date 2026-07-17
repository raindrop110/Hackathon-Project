"""
pipeline_runner.py — synchronous orchestration for generation_quality_agent.

Mirrors data_generation_pipeline/rag_data_generation/pipeline_runner.py: a single
blocking function meant to be called via asyncio.to_thread() from
disposition_normalization/server.py, once both the real-file summary (workflow 1)
and the synthetic batch (workflow 2) are available for the same upload.

Falls back to a locally-computed mock GenerationQualityReport when the live model
call can't complete — see _mock_quality_report and the ADK error_code check below.
"""

import asyncio
import json
import random
from datetime import datetime, timezone
from typing import Any, Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agent import build_generation_quality_agent

_DIMENSIONS = [
    "measure_alignment",
    "channel_alignment",
    "disposition_plausibility",
    "confidence_calibration",
    "structural_realism",
]


def _new_session(app_name: str, user_id: str) -> tuple[InMemorySessionService, str]:
    session_service = InMemorySessionService()
    session = asyncio.run(session_service.create_session(app_name=app_name, user_id=user_id))
    return session_service, session.id


def _mock_quality_report(
    batch_id: str,
    real_summary: Optional[dict[str, Any]],
    synthetic_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Deterministically-random scores over the ACTUAL synthetic records passed in,
    so the heatmap shape (record count, IDs, source types) is always truthful even
    when no live model call was possible — only the scores themselves are fake."""
    cells = []
    for rec in synthetic_records:
        scores = {d: round(random.uniform(45, 92), 1) for d in _DIMENSIONS}
        overall = round(sum(scores.values()) / len(scores), 1)
        cells.append({
            "record_id": rec.get("record_id", "REC-UNKNOWN"),
            "source_type": rec.get("source_type", "unknown"),
            **scores,
            "overall": overall,
            "notes": "[MOCK] simulated score — no live Gemini credentials available",
        })

    if cells:
        dim_avgs = {d: sum(c[d] for c in cells) / len(cells) for d in _DIMENSIONS}
        strongest = max(dim_avgs, key=lambda d: dim_avgs[d])
        weakest = min(dim_avgs, key=lambda d: dim_avgs[d])
        overall_score = round(sum(c["overall"] for c in cells) / len(cells), 1)
    else:
        strongest = weakest = _DIMENSIONS[0]
        overall_score = 0.0

    ref_id = "MOCK-REFERENCE"
    if real_summary:
        ref_id = real_summary.get("member_id") or real_summary.get("gap_id") or ref_id

    return {
        "batch_id": batch_id,
        "reference_record_id": ref_id,
        "dimensions": _DIMENSIONS,
        "cells": cells,
        "overall_score": overall_score,
        "strongest_dimension": strongest,
        "weakest_dimension": weakest,
        "narrative": (
            "[MOCK] No live Gemini credentials were available, so these scores are "
            "randomly simulated for local demo purposes — not a real quality assessment. "
            f"Generated at {datetime.now(timezone.utc).isoformat()}."
        ),
    }


def run_generation_quality_sync(
    batch_id: str,
    real_summary: Optional[dict[str, Any]],
    synthetic_records: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Blocking. Scores the synthetic batch against the real summary and returns
    the GenerationQualityReport as a plain dict. Falls back to a mock report if the
    live call fails (missing credentials, etc.) or produces no usable output —
    never returns None so the frontend heatmap always has something to render."""
    session_service, session_id = _new_session("generation_quality", "upload-loop")
    agent = build_generation_quality_agent(batch_id, real_summary, synthetic_records)
    runner = Runner(agent=agent, app_name="generation_quality", session_service=session_service)

    prompt = "Score the synthetic batch against the real reference record."
    text = ""
    error_code: Optional[str] = None
    for event in runner.run(
        user_id="upload-loop",
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        if error_code is None and getattr(event, "error_code", None):
            error_code = f"{event.error_code}: {getattr(event, 'error_message', '')}"
        if event.author == "generation_quality_agent" and event.is_final_response():
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "text", None):
                        text += part.text

    if error_code:
        print(f"[test_comparison_agent.pipeline_runner] live call failed ({error_code}) — using mock report")
        return _mock_quality_report(batch_id, real_summary, synthetic_records)

    if not text.strip():
        print("[test_comparison_agent.pipeline_runner] live call produced no output — using mock report")
        return _mock_quality_report(batch_id, real_summary, synthetic_records)

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        print(f"[test_comparison_agent.pipeline_runner] non-JSON output, using mock report: {text[:200]}")
        return _mock_quality_report(batch_id, real_summary, synthetic_records)
