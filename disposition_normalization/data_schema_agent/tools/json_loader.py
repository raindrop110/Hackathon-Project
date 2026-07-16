import json
from pathlib import Path
from typing import Any


def load_input_json(file_path: str) -> dict[str, Any]:
    """Load a JSON file from disk and return its parsed contents.

    Handles both a single JSON object and files containing multiple JSON objects
    (e.g. an interaction record followed by a disposition summary).

    Args:
        file_path: Absolute or relative path to the .json input file.

    Returns a dict with 'records' (list of parsed JSON objects) and 'count'.
    If the file cannot be found or parsed, returns an 'error' key with details.
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    text = path.read_text(encoding="utf-8").strip()

    # Try single JSON object first
    try:
        return {"records": [json.loads(text)], "count": 1}
    except json.JSONDecodeError:
        pass

    # Try streaming parse for multiple top-level JSON objects in one file
    decoder = json.JSONDecoder()
    objects: list[Any] = []
    pos = 0
    while pos < len(text):
        stripped = text[pos:].lstrip()
        if not stripped:
            break
        pos += len(text[pos:]) - len(stripped)
        try:
            obj, offset = decoder.raw_decode(stripped)
            objects.append(obj)
            pos += offset
        except json.JSONDecodeError:
            break

    if objects:
        return {"records": objects, "count": len(objects)}

    return {"error": "Could not parse JSON from file", "preview": text[:300]}
