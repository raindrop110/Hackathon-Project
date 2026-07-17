"""
pipeline_runner.py — synchronous orchestration for the upload-driven generation loop.

disposition_normalization/server.py fires this on every file upload (background,
fire-and-forget — see _run_upload_driven_generation there). It does two things,
in order, so a pattern learned from THIS upload is visible to THIS run's batch:

  1. run_pattern_extraction_sync — ask pattern_extractor_agent whether the upload
     demonstrates something the corpus doesn't already know; persist it if so.
  2. run_generation_batch_sync   — run the normal 3-stage generate/validate/summarize
     pipeline against the (possibly just-updated) corpus. Persistence to
     db/datasets.json happens automatically via save_to_json_db (after_agent_callback).

Both functions are fully synchronous and self-contained (they open their own
InMemorySessionService/session via asyncio.run internally) so the caller can run
them with a plain asyncio.to_thread() — no session plumbing needed across the
async/sync boundary.

If the live model call can't complete (missing credentials, etc. — see the
event.error_code check in _collect_final_json), run_generation_batch_sync falls
back to a locally-computed mock batch so the rest of the app (and workflow 3) keeps
working without a live Gemini connection. Pattern extraction just skips instead —
there's nothing meaningful to fake there.
"""

import asyncio
import json
import random
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agent import build_generation_pipeline, build_pattern_extractor_agent
from .tools import append_learned_pattern, learned_pattern_count

_MEASURES = ["AWC", "CBP", "CDC-H", "COA", "COL", "FUH", "MRP", "OMW", "SPC", "TRC"]
_SOURCE_TYPES = ["call_transcript", "ivr_result_code", "csr_note", "web_form"]
_STATUSES = ["closed", "attempted_not_closed", "open_no_contact", "invalid"]
_ACTIONS = {
    "closed": "already_completed",
    "attempted_not_closed": "scheduled_appt",
    "open_no_contact": "left_voicemail",
    "invalid": "wrong_number",
}
_DISPOSITION_CODES = {
    "closed": "DISP-CLOSED",
    "attempted_not_closed": "DISP-SCHED",
    "open_no_contact": "DISP-VM",
    "invalid": "DISP-WN",
}


def _new_session(app_name: str, user_id: str) -> tuple[InMemorySessionService, str]:
    session_service = InMemorySessionService()
    session = asyncio.run(session_service.create_session(app_name=app_name, user_id=user_id))
    return session_service, session.id


def _collect_final_json(
    runner: Runner, user_id: str, session_id: str, prompt: str, author_name: str
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Run the agent to completion and parse the named author's final response as
    JSON. Returns (result, error_code) — error_code is set when ADK reports a
    model-call failure (e.g. missing credentials) via event.error_code, which it
    does instead of raising — the run just silently produces no final response."""
    text = ""
    error_code: Optional[str] = None
    for event in runner.run(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        if error_code is None and getattr(event, "error_code", None):
            error_code = f"{event.error_code}: {getattr(event, 'error_message', '')}"
        if event.author == author_name and event.is_final_response():
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "text", None):
                        text += part.text

    if error_code:
        return None, error_code
    if not text.strip():
        return None, None
    try:
        return json.loads(text.strip()), None
    except json.JSONDecodeError:
        print(f"[pipeline_runner] {author_name} returned non-JSON output: {text[:200]}")
        return None, None


def run_pattern_extraction_sync(filename: str, file_content: str) -> Optional[dict[str, Any]]:
    """Blocking. Returns the persisted pattern dict if novel, else None (including
    when no live model call was possible — there's nothing meaningful to fake for
    pattern learning, so it's just skipped)."""
    session_service, session_id = _new_session("rag_data_generation_extract", "upload-loop")
    agent = build_pattern_extractor_agent(filename, file_content)
    runner = Runner(agent=agent, app_name="rag_data_generation_extract", session_service=session_service)

    prompt = (
        f"Analyze the uploaded file '{filename}' and decide whether it demonstrates "
        "a new generation pattern."
    )
    pattern, error_code = _collect_final_json(runner, "upload-loop", session_id, prompt, "pattern_extractor_agent")
    if error_code:
        print(f"[pipeline_runner] pattern extraction skipped — live call failed ({error_code})")
        return None
    if not pattern or not pattern.get("is_novel"):
        return None

    pattern["pattern_id"] = f"LP-{learned_pattern_count() + 1:06d}"
    pattern["extracted_from"] = filename
    pattern["extracted_at"] = datetime.now(timezone.utc).isoformat()
    return append_learned_pattern(pattern)


def _measure_summary_key(measure: str) -> str:
    return "CDC_H" if measure == "CDC-H" else measure


def _mock_generation_batch(batch_size: int = 5) -> dict[str, dict[str, Any]]:
    """A locally-computed stand-in batch, same shape as the real pipeline's output,
    used when no live model call is possible (missing credentials, etc.)."""
    now = datetime.now(timezone.utc).isoformat()
    batch_id = f"BATCH-MOCK-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    records = []
    for i in range(batch_size):
        status = random.choice(_STATUSES)
        records.append({
            "record_id": f"REC-{i + 1:06d}",
            "source_type": _SOURCE_TYPES[i % len(_SOURCE_TYPES)],
            "raw_payload": "[MOCK] no live Gemini call — simulated payload for local demo",
            "member_id": f"MBR{random.randint(1, 200):05d}",
            "provider_id": f"PRV{random.randint(1, 50):04d}",
            "care_gap_id": random.choice(_MEASURES),
            "hedis_measure": random.choice(_MEASURES),
            "responded": status != "open_no_contact",
            "response_summary": "[MOCK] simulated response — no live credentials available",
            "action_taken": _ACTIONS[status],
            "care_gap_status": status,
            "disposition_code": _DISPOSITION_CODES[status],
            "confidence": round(random.uniform(0.5, 0.95), 2),
            "validation_status": "valid",
            "validation_notes": "[MOCK] not independently validated — no live credentials",
        })

    validated_data = {
        "records": records,
        "batch_id": batch_id,
        "validated_at": now,
        "total_records": len(records),
        "valid_count": len(records),
        "corrected_count": 0,
        "rejected_count": 0,
    }
    dataset_summary = {
        "batch_id": batch_id,
        "total_records": len(records),
        "by_source_type": {t: sum(1 for r in records if r["source_type"] == t) for t in _SOURCE_TYPES},
        "by_care_gap_measure": {
            _measure_summary_key(m): sum(1 for r in records if r["hedis_measure"] == m) for m in _MEASURES
        },
        "by_disposition_outcome": {s: sum(1 for r in records if r["care_gap_status"] == s) for s in _STATUSES},
        "validation_pass_rate": 1.0,
        "notable_edge_cases": [],
        "summary_notes": "[MOCK] Simulated dataset — no live Gemini credentials were available.",
    }
    return {"validated_data": validated_data, "dataset_summary": dataset_summary}


def run_generation_batch_sync() -> dict[str, Optional[dict[str, Any]]]:
    """Blocking. Runs generate -> validate -> summarize once against the current
    corpus. Returns BOTH the validated records (individual per-record data, needed
    by test_comparison_agent's generation_quality_agent to score the batch) and the
    aggregate dataset_summary. The batch itself is persisted to db/datasets.json
    automatically via the pipeline's after_agent_callback.

    Falls back to _mock_generation_batch() if the live call fails or produces no
    usable records, so workflow 3 always has something to score."""
    session_service, session_id = _new_session("rag_data_generation_batch", "upload-loop")
    pipeline = build_generation_pipeline()
    runner = Runner(agent=pipeline, app_name="rag_data_generation_batch", session_service=session_service)

    author_to_key = {
        "sme_validator_agent": "validated_data",
        "summary_generator_agent": "dataset_summary",
    }
    texts: dict[str, str] = {key: "" for key in author_to_key.values()}
    error_code: Optional[str] = None

    prompt = "Generate a new batch of synthetic disposition records."
    for event in runner.run(
        user_id="upload-loop",
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        if error_code is None and getattr(event, "error_code", None):
            error_code = f"{event.error_code}: {getattr(event, 'error_message', '')}"
        key = author_to_key.get(event.author)
        if key and event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    texts[key] += part.text

    if error_code:
        print(f"[pipeline_runner] generation batch falling back to mock — live call failed ({error_code})")
        return _mock_generation_batch()

    result: dict[str, Optional[dict[str, Any]]] = {}
    for key, text in texts.items():
        if not text.strip():
            result[key] = None
            continue
        try:
            result[key] = json.loads(text.strip())
        except json.JSONDecodeError:
            print(f"[pipeline_runner] {key} returned non-JSON output: {text[:200]}")
            result[key] = None

    if not (result.get("validated_data") or {}).get("records"):
        print("[pipeline_runner] generation batch falling back to mock — no usable records produced")
        return _mock_generation_batch()

    return result


def run_upload_driven_generation_sync(filename: str, file_content: str) -> dict[str, Any]:
    """Entry point for the background task in server.py. Call via asyncio.to_thread().

    Never raises — each stage is isolated so a failure in one doesn't block the other,
    and the caller only needs the returned dict for logging.
    """
    result: dict[str, Any] = {"pattern": None, "batch": None}

    try:
        result["pattern"] = run_pattern_extraction_sync(filename, file_content)
    except Exception:
        print(f"[pipeline_runner] pattern extraction failed:\n{traceback.format_exc()}")

    try:
        result["batch"] = run_generation_batch_sync()
    except Exception:
        print(f"[pipeline_runner] generation batch failed:\n{traceback.format_exc()}")
        result["batch"] = _mock_generation_batch()

    return result
