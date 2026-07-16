import asyncio
import json
import tempfile
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from disposition_normalization.orchestrator_agent import root_agent as orchestrator
from test_comparison_agent import root_agent as comparison_agent

app = FastAPI(title="Disposition Normalization API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TMP_DIR = Path(tempfile.gettempdir()) / "disposition_normalization"
TMP_DIR.mkdir(exist_ok=True)

# Maps each sub-agent name → frontend stage ID
_AGENT_STAGE = {
    "disposition_summarization_agent": "summarization",
    "data_schema_agent": "schema_normalization",
    "data_connection_agent": "care_gap_connection",
}

# Per-run SSE queues
_queues: dict[str, asyncio.Queue] = {}


# ── Workflow runner ──────────────────────────────────────────────────────────

def _run_orchestrator_sync(
    file_path: str,
    run_id: str,
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
    session_service: InMemorySessionService,
    session_id: str,
) -> None:
    """Run the GADK orchestrator synchronously in a thread.

    Intercepts events by author so we can emit per-agent SSE stages
    without breaking the single-Runner GADK pattern.
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

    for event in runner.run(
        user_id="workflow",
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        author: str = getattr(event, "author", "") or ""
        stage = _AGENT_STAGE.get(author)

        # Emit stage_start when we first see a sub-agent event
        if stage and stage not in stages_started:
            stages_started.add(stage)
            emit({"type": "stage_start", "stageId": stage, "message": f"{author} is processing…"})

        # Emit stage_complete when a sub-agent emits its final response
        if stage and event.is_final_response() and stage not in stages_completed:
            stages_completed.add(stage)
            text = ""
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        text += part.text
            try:
                result = json.loads(text.strip())
            except json.JSONDecodeError:
                result = {"raw": text.strip()}
            agent_results[stage] = result
            emit({
                "type": "stage_complete",
                "stageId": stage,
                "message": f"{stage.replace('_', ' ').title()} complete",
                "result": result,
            })

        # Orchestrator itself finished — flush any stages that never fired
        # (guards against GADK versions that don't surface AgentTool sub-events)
        if author == orchestrator.name and event.is_final_response():
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


async def _run_workflow(run_id: str, file_path: str, queue: asyncio.Queue) -> None:
    loop = asyncio.get_running_loop()

    # Create session here in async context — create_session is a coroutine
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="disposition_normalization",
        user_id="workflow",
    )

    try:
        await asyncio.to_thread(
            _run_orchestrator_sync,
            file_path, run_id, loop, queue, session_service, session.id,
        )
    except Exception as exc:
        queue.put_nowait({"type": "run_error", "error": str(exc)})
    finally:
        for suffix in ["summary", "disposition"]:
            p = TMP_DIR / f"{run_id}_{suffix}.json"
            p.unlink(missing_ok=True)
        Path(file_path).unlink(missing_ok=True)


# Per-run SSE queues for comparison runs
_cmp_queues: dict[str, asyncio.Queue] = {}

# Maps sub-agent name → frontend stage ID
_CMP_STAGE = {
    "test_data_generator": "cmp_generate",
    "batch_normalizer": "cmp_normalize",
    "accuracy_comparator": "cmp_compare",
}

_CMP_STAGE_LABELS = {
    "cmp_generate": "Generating test data",
    "cmp_normalize": "Normalizing records",
    "cmp_compare": "Comparing results",
}


def _run_comparison_sync(
    run_id: str,
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
    session_service: InMemorySessionService,
    session_id: str,
) -> None:
    """Run the comparison SequentialAgent synchronously in a thread."""
    runner = Runner(
        agent=comparison_agent,
        app_name="test_comparison",
        session_service=session_service,
    )

    def emit(event_dict: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event_dict)

    stages_started: set[str] = set()
    stages_completed: set[str] = set()
    comparison_report: dict | None = None

    for event in runner.run(
        user_id="comparison",
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text="Run the full normalization accuracy comparison.")],
        ),
    ):
        author: str = getattr(event, "author", "") or ""
        stage = _CMP_STAGE.get(author)

        if stage and stage not in stages_started:
            stages_started.add(stage)
            emit({
                "type": "stage_start",
                "stageId": stage,
                "message": f"{_CMP_STAGE_LABELS.get(stage, stage)}…",
            })

        if stage and event.is_final_response() and stage not in stages_completed:
            stages_completed.add(stage)
            text = ""
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        text += part.text
            try:
                result = json.loads(text.strip())
            except json.JSONDecodeError:
                result = {"raw": text.strip()}

            if author == "accuracy_comparator":
                comparison_report = result

            emit({
                "type": "stage_complete",
                "stageId": stage,
                "message": f"{_CMP_STAGE_LABELS.get(stage, stage)} complete",
                "result": result,
            })

        # Root SequentialAgent finished — guard against missing sub-events
        if author == comparison_agent.name and event.is_final_response():
            for stage_id in ("cmp_generate", "cmp_normalize", "cmp_compare"):
                if stage_id not in stages_started:
                    emit({"type": "stage_start", "stageId": stage_id})
                if stage_id not in stages_completed:
                    emit({"type": "stage_complete", "stageId": stage_id, "message": "Complete"})
            emit({"type": "stage_complete", "stageId": "cmp_complete", "message": "Comparison complete"})
            emit({"type": "run_complete", "result": comparison_report})


async def _run_comparison(run_id: str, queue: asyncio.Queue) -> None:
    loop = asyncio.get_running_loop()
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="test_comparison",
        user_id="comparison",
    )
    try:
        await asyncio.to_thread(
            _run_comparison_sync,
            run_id, loop, queue, session_service, session.id,
        )
    except Exception as exc:
        queue.put_nowait({"type": "run_error", "error": str(exc)})


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

    asyncio.create_task(_run_workflow(runId, str(file_path), queue))

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


@app.post("/api/comparison/run")
async def start_comparison():
    run_id = uuid.uuid4().hex[:12]
    queue: asyncio.Queue = asyncio.Queue()
    _cmp_queues[run_id] = queue
    asyncio.create_task(_run_comparison(run_id, queue))
    return {"runId": run_id}


@app.get("/api/comparison/{run_id}/stream")
async def stream_comparison(run_id: str):
    queue = _cmp_queues.get(run_id)
    if queue is None:
        async def _not_found():
            yield f"data: {json.dumps({'type': 'run_error', 'error': 'Run not found'})}\n\n"
        return StreamingResponse(_not_found(), media_type="text/event-stream")

    async def _generate():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event["type"] in ("run_complete", "run_error"):
                _cmp_queues.pop(run_id, None)
                break

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
