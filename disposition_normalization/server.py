import asyncio
import json
import random
import re
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from data_generation_pipeline.rag_data_generation.pipeline_runner import (
    run_upload_driven_generation_sync,
)
from disposition_normalization.data_connection_agent.tools.care_gap_lookup import update_care_gap
from disposition_normalization.orchestrator_agent import root_agent as orchestrator
from test_comparison_agent.pipeline_runner import run_generation_quality_sync

app = FastAPI(title="Disposition Normalization API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TMP_DIR = Path(tempfile.gettempdir()) / "disposition_normalization"
TMP_DIR.mkdir(exist_ok=True)

# Repo-relative dataset directory — the only place file-editor reads/writes reach.
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = (REPO_ROOT / "data").resolve()


def _safe_data_path(rel_path: str) -> Path:
    """Resolve a client-supplied relative path and confirm it stays inside DATA_DIR."""
    resolved = (REPO_ROOT / rel_path).resolve()
    if not resolved.is_relative_to(DATA_DIR):
        raise HTTPException(status_code=400, detail="Path outside data directory")
    return resolved

# Maps each sub-agent name → frontend stage ID
_AGENT_STAGE = {
    "disposition_summarization_agent": "summarization",
    "data_schema_agent": "schema_normalization",
    "data_connection_agent": "care_gap_connection",
}

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


def _strip_code_fences(text: str) -> str:
    """Strip a wrapping ```json ... ``` fence a sub-agent's raw text output may
    carry despite being instructed to return JSON only, so json.loads doesn't choke on it."""
    match = _CODE_FENCE_RE.match(text.strip())
    return match.group(1).strip() if match else text

# Per-run SSE queues
_queues: dict[str, asyncio.Queue] = {}

# Workflow 1's summarization result, stashed per run_id once the pipeline finishes —
# this is the "real reference record" the generation-quality loop below compares
# the synthetic batch against.
_run_summaries: dict[str, dict] = {}


# ── Mock fallback (no live Gemini credentials) ──────────────────────────────
# ADK doesn't raise on a model-call failure (missing ADC, bad API key, etc.) — it
# yields a single event with event.error_code set and no final response. When that
# happens (or the run otherwise produces no usable output), fall back to locally
# computed mock data so the app stays fully demoable without live credentials.

_MOCK_MEASURES = ["AWC", "CBP", "CDC-H", "COA", "COL", "FUH", "MRP", "OMW", "SPC", "TRC"]


def _mock_summary_result(file_path: str) -> dict:
    name = Path(file_path).stem
    return {
        "member_id": f"MBR{random.randint(1, 200):05d}",
        "gap_id": f"GAP{random.randint(100, 999):06d}",
        "measure_id": random.choice(_MOCK_MEASURES),
        "measure_name": "Colorectal Cancer Screening",
        "interaction_type": "call_transcript",
        "channel": "phone",
        "disposition_code": "DISP-SCHED",
        "interaction_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "provider_name": "Dr. Avery Chen",
        "service_completed": False,
        "member_refused": False,
        "successful_contact": True,
        "follow_up_required": True,
        "key_findings": [
            "[MOCK] No live Gemini credentials — this is placeholder output for local demo purposes.",
            "Member agreed to schedule screening within 30 days.",
        ],
        "entities": [name],
        "evidence": ["[MOCK] Simulated evidence line — no live model call was made."],
        "confidence": "medium",
        "summary": f"[MOCK] Simulated summary for '{name}' — no live Gemini credentials were available.",
    }


def _mock_disposition_result(summary: dict) -> dict:
    return {
        "disposition_id": f"DISP-{random.randint(100000, 999999)}",
        "member_id": summary["member_id"],
        "gap_id": summary["gap_id"],
        "measure_id": summary["measure_id"],
        "disposition_code": summary["disposition_code"],
        "channel": summary["channel"],
        "interaction_date": summary["interaction_date"],
        "outcome": "scheduled_appt",
        "confidence": 0.62,
    }


def _mock_care_gap_result(summary: dict) -> dict:
    return {
        "success": True,
        "gap_id": summary["gap_id"],
        "changes": {
            "status": {"from": "open", "to": "attempted_not_closed"},
            "last_outreach_date": {"from": "", "to": summary["interaction_date"]},
        },
        "status": "[MOCK] simulated update — no live Gemini credentials were available",
    }


# ── Workflow runner ──────────────────────────────────────────────────────────

def _run_orchestrator_sync(
    file_path: str,
    run_id: str,
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
    session_service: InMemorySessionService,
    session_id: str,
) -> dict[str, object]:
    """Run the GADK orchestrator synchronously in a thread.

    Intercepts each AgentTool call/response pair so we can emit per-agent SSE
    stages without breaking the single-Runner GADK pattern.
    Session is pre-created in async context and passed in to avoid awaiting here.
    """
    runner = Runner(
        agent=orchestrator,
        app_name="disposition_normalization",
        session_service=session_service,
    )

    prompt = f"file_path: {file_path}\nrun_id: {run_id}"

    def emit(event_dict: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event_dict)

    stages_started: set[str] = set()
    stages_completed: set[str] = set()
    agent_results: dict[str, object] = {}
    error_code: str | None = None

    for event in runner.run(
        user_id="workflow",
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        if error_code is None and getattr(event, "error_code", None):
            error_code = f"{event.error_code}: {getattr(event, 'error_message', '')}"

        author: str = getattr(event, "author", "") or ""

        # AgentTool runs each sub-agent in its own private nested Runner and never
        # surfaces that sub-agent's internal events to this top-level loop — every
        # event we see here is authored by the orchestrator itself. The only trace
        # of a sub-agent invocation at this level is the orchestrator's own
        # function_call (tool invoked) / function_response (tool returned) parts,
        # named after the tool (== the sub-agent's name), so we key off those
        # instead of event.author.
        for call in event.get_function_calls():
            stage = _AGENT_STAGE.get(call.name)
            if stage and stage not in stages_started:
                stages_started.add(stage)
                emit({"type": "stage_start", "stageId": stage, "message": f"{call.name} is processing…"})

        for resp in event.get_function_responses():
            stage = _AGENT_STAGE.get(resp.name)
            if stage and stage not in stages_completed:
                stages_completed.add(stage)
                raw = (resp.response or {}).get("result", "")
                text = raw if isinstance(raw, str) else json.dumps(raw)
                text = _strip_code_fences(text)
                try:
                    result = json.loads(text)
                except (json.JSONDecodeError, AttributeError):
                    result = {"raw": text}
                agent_results[stage] = result
                emit({
                    "type": "stage_complete",
                    "stageId": stage,
                    "message": f"{stage.replace('_', ' ').title()} complete",
                    "result": result,
                })

        # Orchestrator itself finished — flush any stages that never fired
        # (guards against GADK versions that don't surface AgentTool sub-events).
        # error_code guard: an error-terminated turn also reports is_final_response()
        # True, but nothing actually ran — let the mock fallback below handle it
        # instead of flushing fake "Complete" stages with null results.
        if error_code is None and author == orchestrator.name and event.is_final_response():
            for stage_id in ("summarization", "schema_normalization", "care_gap_connection"):
                if stage_id not in stages_started:
                    emit({"type": "stage_start", "stageId": stage_id})
                if stage_id not in stages_completed:
                    emit({"type": "stage_complete", "stageId": stage_id, "message": "Complete"})
            emit({"type": "stage_complete", "stageId": "complete", "message": "All agents finished"})
            emit({
                "type": "run_complete",
                "result": {
                    "summary": agent_results.get("summarization"),
                    "disposition": agent_results.get("schema_normalization"),
                    "careGap": agent_results.get("care_gap_connection"),
                },
            })

    if "care_gap_connection" not in agent_results:
        # Live run never completed (missing credentials, etc.) — fall back to mock
        # output so the workflow tab and downstream generation-quality loop both
        # still have something real-shaped to work with.
        reason = error_code or "no usable output from live run"
        print(f"[workflow] falling back to mock output ({reason})")

        summary = _mock_summary_result(file_path)
        disposition = _mock_disposition_result(summary)
        care_gap = _mock_care_gap_result(summary)
        agent_results = {
            "summarization": summary,
            "schema_normalization": disposition,
            "care_gap_connection": care_gap,
        }

        for stage_id in ("summarization", "schema_normalization", "care_gap_connection"):
            emit({"type": "stage_start", "stageId": stage_id, "message": "[MOCK] simulated (no live credentials)"})
            emit({
                "type": "stage_complete",
                "stageId": stage_id,
                "message": "[MOCK] complete",
                "result": agent_results[stage_id],
            })
        emit({"type": "stage_complete", "stageId": "complete", "message": "All agents finished (mock)"})
        emit({
            "type": "run_complete",
            "result": {
                "summary": agent_results["summarization"],
                "disposition": agent_results["schema_normalization"],
                "careGap": agent_results["care_gap_connection"],
            },
        })

    return agent_results


async def _run_workflow(run_id: str, file_path: str, queue: asyncio.Queue) -> None:
    loop = asyncio.get_running_loop()

    # Create session here in async context — create_session is a coroutine
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="disposition_normalization",
        user_id="workflow",
    )

    try:
        agent_results = await asyncio.to_thread(
            _run_orchestrator_sync,
            file_path, run_id, loop, queue, session_service, session.id,
        )
        if agent_results.get("summarization"):
            _run_summaries[run_id] = agent_results["summarization"]
    except Exception as exc:
        queue.put_nowait({"type": "run_error", "error": str(exc)})
    finally:
        for suffix in ["summary", "disposition"]:
            p = TMP_DIR / f"{run_id}_{suffix}.json"
            p.unlink(missing_ok=True)
        Path(file_path).unlink(missing_ok=True)


# ── Workflows 2 + 3: upload-driven generation, then generator-quality scoring ──
# Fire-and-forget, chained: every text upload feeds the RAG data generator (see
# data_generation_pipeline/rag_data_generation) two ways — (1) a pattern-
# extraction pass may add a new entry to corpus/learned_patterns.json if the
# file demonstrates something the corpus doesn't already know, and (2) a fresh
# generation batch runs against that (possibly just-updated) corpus and is
# persisted to db/datasets.json. Once that batch exists AND workflow 1 (above)
# has produced its real summary for the SAME upload, workflow 3
# (generation_quality_agent) scores every record in the batch against that real
# summary and streams a heatmap-ready report to the frontend. Runs alongside the
# main summarization workflow, never blocks it, and never surfaces errors to
# the client — failures are logged to the server console only.

_TEXT_UPLOAD_EXTS = {".csv", ".txt", ".md"}
_MAX_UPLOAD_TEXT_CHARS = 8000
_data_gen_lock = asyncio.Lock()

# Per-run SSE queues for the generation-quality stream
_quality_queues: dict[str, asyncio.Queue] = {}

# Generated batches (real or mock), keyed by batch_id — lets the frontend open a
# just-generated batch as a read-only file tab without needing it on disk inside
# DATA_DIR. Populated below as soon as a batch exists, whether real or mock.
_generated_batches: dict[str, dict] = {}


async def _run_generation_and_quality_pipeline(
    run_id: str,
    filename: str,
    raw_bytes: bytes,
    workflow_task: "asyncio.Task[None]",
) -> None:
    queue = _quality_queues[run_id]

    def emit(event: dict) -> None:
        queue.put_nowait(event)

    ext = Path(filename).suffix.lower()
    if ext not in _TEXT_UPLOAD_EXTS:
        emit({"type": "run_error", "error": f"'{ext}' files aren't used for data generation"})
        return

    text = raw_bytes.decode("utf-8", errors="ignore")[:_MAX_UPLOAD_TEXT_CHARS]
    if not text.strip():
        emit({"type": "run_error", "error": "File has no readable text content"})
        return

    try:
        async with _data_gen_lock:
            emit({"type": "stage_start", "stageId": "pattern_extraction", "message": "Checking for new patterns…"})
            gen_result = await asyncio.to_thread(run_upload_driven_generation_sync, filename, text)

        pattern = gen_result.get("pattern")
        batch = gen_result.get("batch") or {}
        validated_data = batch.get("validated_data") or {}
        dataset_summary = batch.get("dataset_summary") or {}
        synthetic_records = validated_data.get("records") or []
        batch_id = dataset_summary.get("batch_id") or validated_data.get("batch_id") or "BATCH-UNKNOWN"

        if synthetic_records:
            _generated_batches[batch_id] = {"validated_data": validated_data, "dataset_summary": dataset_summary}

        emit({
            "type": "stage_complete",
            "stageId": "pattern_extraction",
            "message": f"Learned new pattern {pattern['pattern_id']}" if pattern else "No novel pattern found",
        })
        emit({
            "type": "stage_complete",
            "stageId": "generation_batch",
            "message": f"Generated batch {batch_id} ({len(synthetic_records)} records)",
            "result": dataset_summary,
        })

        if not synthetic_records:
            emit({"type": "run_error", "error": "Generation batch produced no records to score"})
            return

        emit({"type": "stage_start", "stageId": "quality_scoring", "message": "Waiting for real-file summary…"})
        await workflow_task  # workflow 1 handles its own errors internally; never raises here
        real_summary = _run_summaries.get(run_id)

        emit({"type": "stage_progress", "stageId": "quality_scoring", "message": "Scoring batch against real summary…"})
        report = await asyncio.to_thread(run_generation_quality_sync, batch_id, real_summary, synthetic_records)

        if not report:
            emit({"type": "run_error", "error": "Quality scoring produced no usable output"})
            return

        emit({"type": "stage_complete", "stageId": "quality_scoring", "message": "Scoring complete"})
        emit({"type": "run_complete", "result": report})
    except Exception:
        print(f"[generation_quality_loop] ERROR:\n{traceback.format_exc()}")
        emit({"type": "run_error", "error": "Generation-quality pipeline failed — see server logs"})


# ── API endpoints ────────────────────────────────────────────────────────────

@app.post("/api/workflow/start")
async def start_workflow(
    runId: str = Form(...),
    file: UploadFile = File(...),
):
    content = await file.read()
    file_path = TMP_DIR / f"{runId}_{file.filename}"
    file_path.write_bytes(content)

    queue: asyncio.Queue = asyncio.Queue()
    _queues[runId] = queue

    # Ingest stage completes immediately on receipt
    await queue.put({
        "type": "stage_complete",
        "stageId": "ingest",
        "message": f"'{file.filename}' received ({len(content):,} bytes)",
    })

    workflow_task = asyncio.create_task(_run_workflow(runId, str(file_path), queue))

    _quality_queues[runId] = asyncio.Queue()
    asyncio.create_task(
        _run_generation_and_quality_pipeline(runId, file.filename, content, workflow_task)
    )

    return {"runId": runId}


@app.get("/api/workflow/{run_id}/stream")
async def stream_events(run_id: str):
    queue = _queues.get(run_id)
    if queue is None:
        async def _not_found():
            yield f"data: {json.dumps({'type': 'run_error', 'error': 'Run not found'})}\n\n"
        return StreamingResponse(_not_found(), media_type="text/event-stream")

    async def _generate():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event["type"] in ("run_complete", "run_error"):
                _queues.pop(run_id, None)
                break

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class CareGapFieldEdit(BaseModel):
    field: str
    value: str


@app.post("/api/care-gap/{gap_id}/field")
async def edit_care_gap_field(gap_id: str, payload: CareGapFieldEdit):
    """Manual correction endpoint — writes a single field straight to care_gaps.csv."""
    return update_care_gap(gap_id, {payload.field: payload.value})


@app.get("/api/generation-quality/{run_id}/stream")
async def stream_generation_quality(run_id: str):
    """Workflow 3 — streams pattern-extraction/generation-batch/scoring progress for
    the given upload's run_id, ending with the heatmap-ready GenerationQualityReport."""
    queue = _quality_queues.get(run_id)
    if queue is None:
        async def _not_found():
            yield f"data: {json.dumps({'type': 'run_error', 'error': 'Run not found'})}\n\n"
        return StreamingResponse(_not_found(), media_type="text/event-stream")

    async def _generate():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event["type"] in ("run_complete", "run_error"):
                _quality_queues.pop(run_id, None)
                break

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/files/content")
async def get_file_content(path: str):
    """Read a text file from the dataset directory for the IDE editor tab."""
    file_path = _safe_data_path(path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=415, detail="File is not text-readable")
    return {"path": path, "content": content}


class FileContentEdit(BaseModel):
    path: str
    content: str


@app.post("/api/files/content")
async def save_file_content(payload: FileContentEdit):
    """Write editor changes for a dataset file straight back to disk."""
    file_path = _safe_data_path(payload.path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.write_text(payload.content, encoding="utf-8")
    return {"success": True}


@app.get("/api/generated-batches/{batch_id}")
async def get_generated_batch(batch_id: str):
    """Read-only — serves a workflow-2 batch (real or mock) for the IDE's
    auto-opened 'generated data' file tab. In-memory only, not backed by disk."""
    batch = _generated_batches.get(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
