"""
main.py — Headless runner for the RAG Data Generation pipeline.

Executes the 3-stage SequentialAgent pipeline once and prints the contents of
all three output state keys: generated_data, validated_data, dataset_summary.

Usage:
    python main.py                  # runs with default BATCH_SIZE=10
    BATCH_SIZE=5 python main.py     # override batch size
"""

import asyncio
import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# Validate required env vars before importing ADK (gives a clearer error message)
if not os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_GENAI_USE_VERTEXAI") != "TRUE":
    print(
        "ERROR: GOOGLE_API_KEY is not set.\n"
        "Copy .env.example to .env and add your key, or set GOOGLE_GENAI_USE_VERTEXAI=TRUE\n"
        "for Vertex AI authentication.",
        file=sys.stderr,
    )
    sys.exit(1)

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from rag_data_generation import root_agent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pretty(value: Any) -> str:
    """Serialise a state value to a readable JSON string, handling Pydantic models."""
    if hasattr(value, "model_dump"):
        # Pydantic v2 model instance
        return json.dumps(value.model_dump(mode="json"), indent=2, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, indent=2, ensure_ascii=False)
    # Fallback: str representation
    return str(value)


def _divider(title: str) -> None:
    width = 70
    print("\n" + "═" * width)
    print(f"  {title}")
    print("═" * width)


# ---------------------------------------------------------------------------
# Main coroutine
# ---------------------------------------------------------------------------

async def run_pipeline() -> None:
    """Run the full 3-stage pipeline and print results from session state."""

    app_name = "rag_data_generation"
    user_id = "system"
    session_id = "run-001"

    # In-memory session service — no persistence between runs.
    # SWAP SEAM: replace with a persistent session service (e.g., Firestore-backed)
    # for production use or multi-turn debugging.
    session_service = InMemorySessionService()
    # InMemorySessionService.create_session is synchronous in google-adk
    session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )

    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
    )

    # The trigger message content doesn't affect the pipeline logic — the agents
    # read from session state and the injected instruction context.
    trigger_message = Content(
        role="user",
        parts=[
            Part(
                text=(
                    f"Generate a batch of {os.getenv('BATCH_SIZE', '10')} synthetic "
                    "care-gap outreach disposition records with ground-truth labels, "
                    "validate them, and produce a dataset summary."
                )
            )
        ],
    )

    print(f"\nStarting RAG Data Generation pipeline  (BATCH_SIZE={os.getenv('BATCH_SIZE', '10')})")
    print("This may take 30–90 seconds depending on model latency...\n")

    # Stream events; the SequentialAgent runs all three sub-agents sequentially.
    event_count = 0
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=trigger_message,
    ):
        event_count += 1
        # Print a progress dot for each event so the user knows work is happening
        if event_count % 5 == 0:
            print(".", end="", flush=True)

    print(f"\n\nPipeline complete ({event_count} events processed).")

    # Retrieve the final session state — get_session is also synchronous
    session = session_service.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )

    state = session.state if session else {}

    # ── Generated Data ──────────────────────────────────────────────────────
    _divider("STAGE 1 OUTPUT — generated_data  (state['generated_data'])")
    generated = state.get("generated_data")
    if generated is None:
        print("  ⚠  'generated_data' not found in session state.")
    else:
        print(_pretty(generated))

    # ── Validated Data ──────────────────────────────────────────────────────
    _divider("STAGE 2 OUTPUT — validated_data  (state['validated_data'])")
    validated = state.get("validated_data")
    if validated is None:
        print("  ⚠  'validated_data' not found in session state.")
    else:
        print(_pretty(validated))

    # ── Dataset Summary ─────────────────────────────────────────────────────
    _divider("STAGE 3 OUTPUT — dataset_summary  (state['dataset_summary'])")
    summary = state.get("dataset_summary")
    if summary is None:
        print("  ⚠  'dataset_summary' not found in session state.")
    else:
        print(_pretty(summary))

    _divider("RUN COMPLETE")
    print(
        "\nAll three state keys are now populated.  "
        "Pass 'validated_data' and 'dataset_summary' to the "
        "downstream Comparison step.\n"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(run_pipeline())
