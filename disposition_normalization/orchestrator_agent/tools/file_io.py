import tempfile
from pathlib import Path
from typing import Any

TMP_DIR = Path(tempfile.gettempdir()) / "disposition_normalization"
TMP_DIR.mkdir(exist_ok=True)


def save_intermediate(data: str, run_id: str, step: str) -> dict[str, Any]:
    """Save an agent's JSON output to a temp file and return its path.

    Use this between pipeline stages so the next agent can read the previous
    agent's output as a file path (which is how schema and connection agents accept input).

    Args:
        data: The raw JSON string output from the previous agent.
        run_id: The workflow run ID — used to make the filename unique.
        step: A short label for this stage, e.g. 'summary' or 'disposition'.

    Returns a dict with 'file_path' (the absolute path to the saved file).
    """
    TMP_DIR.mkdir(exist_ok=True)
    path = TMP_DIR / f"{run_id}_{step}.json"
    path.write_text(data, encoding="utf-8")
    return {"file_path": str(path), "step": step, "run_id": run_id}
