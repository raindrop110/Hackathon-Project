"""
firestore_agent.py — Custom ADK agent that persists pipeline outputs to Firestore.

Runs as the 4th (final) step in the SequentialAgent pipeline.
Reads generated_data, validated_data, and dataset_summary from session state
and writes each to its own Firestore collection, keyed by batch_id.

Collections created:
  generated_datasets/<batch_id>  — raw synthetic records + ground-truth labels
  validated_datasets/<batch_id>  — QA-reviewed records with validation status
  dataset_summaries/<batch_id>   — aggregate stats for the Comparison step
"""

import os
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.cloud import firestore
from google.genai.types import Content, Part


class FirestoreSaveAgent(BaseAgent):
    """Saves all three pipeline state outputs to Firestore after the pipeline completes."""

    async def _run_async_impl(self, ctx) -> AsyncGenerator[Event, None]:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        db = firestore.Client(project=project)
        state = ctx.session.state

        def _to_dict(value):
            if value is None:
                return None
            if hasattr(value, "model_dump"):
                return value.model_dump(mode="json")
            if isinstance(value, dict):
                return value
            return {"raw": str(value)}

        generated = _to_dict(state.get("generated_data"))
        validated = _to_dict(state.get("validated_data"))
        summary   = _to_dict(state.get("dataset_summary"))

        batch_id = (
            (generated or {}).get("batch_id")
            or (validated or {}).get("batch_id")
            or (summary   or {}).get("batch_id")
            or "BATCH-UNKNOWN"
        )

        saved = []

        if generated:
            db.collection("generated_datasets").document(batch_id).set(generated)
            saved.append("generated_datasets")

        if validated:
            db.collection("validated_datasets").document(batch_id).set(validated)
            saved.append("validated_datasets")

        if summary:
            db.collection("dataset_summaries").document(batch_id).set(summary)
            saved.append("dataset_summaries")

        msg = (
            f"Saved batch {batch_id} to Firestore: {', '.join(saved)}"
            if saved
            else "No state data found to save."
        )

        yield Event(
            author=self.name,
            content=Content(parts=[Part(text=msg)]),
        )
