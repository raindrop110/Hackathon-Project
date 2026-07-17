"""
db_agent.py — after_agent_callback that persists pipeline outputs to a local JSON file.

Attached to the root SequentialAgent via after_agent_callback. Runs after all
three LlmAgent stages complete, with guaranteed access to session state.

File layout:
  db/datasets.json  →  { "<batch_id>": { "generated": {...}, "validated": {...}, "summary": {...} }, ... }
"""

import json
import traceback
from pathlib import Path

_DB_PATH = Path(__file__).parent / "db" / "datasets.json"


def _to_dict(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
    return {"raw": str(value)}


def save_to_json_db(callback_context) -> None:
    """after_agent_callback: writes pipeline outputs to db/datasets.json."""
    try:
        state = callback_context.state

        generated = _to_dict(state.get("generated_data"))
        validated = _to_dict(state.get("validated_data"))
        summary   = _to_dict(state.get("dataset_summary"))

        if not any([generated, validated, summary]):
            print(f"[db_agent] No data to save. State keys present: {list(state.keys())}")
            return None

        batch_id = (
            (generated or {}).get("batch_id")
            or (validated or {}).get("batch_id")
            or (summary   or {}).get("batch_id")
            or "BATCH-UNKNOWN"
        )

        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        db = {}
        if _DB_PATH.exists():
            with open(_DB_PATH, "r", encoding="utf-8") as f:
                try:
                    db = json.load(f)
                except json.JSONDecodeError:
                    db = {}

        db[batch_id] = {
            "generated": generated,
            "validated": validated,
            "summary":   summary,
        }

        with open(_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)

        print(f"[db_agent] Saved batch {batch_id} to {_DB_PATH} "
              f"(total batches: {len(db)})")

    except Exception:
        print(f"[db_agent] ERROR saving to JSON:\n{traceback.format_exc()}")

    return None
