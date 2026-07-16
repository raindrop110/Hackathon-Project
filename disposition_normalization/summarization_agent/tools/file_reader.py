from pathlib import Path
from typing import Any


def load_raw_file(file_path: str) -> dict[str, Any]:
    """Read a raw text, markdown, or JSON file and return its full contents as a string.

    Args:
        file_path: Absolute path to the uploaded file (.txt, .md, or .json).

    Returns a dict with 'content' (full file text), 'filename', and 'extension'.
    If the file cannot be found, returns an 'error' key.
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}
    return {
        "content": path.read_text(encoding="utf-8"),
        "filename": path.name,
        "extension": path.suffix,
    }
