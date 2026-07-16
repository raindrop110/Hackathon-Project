import csv
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).parents[3] / "data" / "structured" / "care_gaps.csv"

_by_gap_id: dict[str, dict[str, Any]] = {}
_by_member_measure: dict[tuple[str, str], list[dict[str, Any]]] = {}
_loaded = False


def _load() -> None:
    global _loaded
    if _loaded:
        return
    with open(_DATA_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            _by_gap_id[row["gap_id"]] = row
            key = (row["member_id"], row["measure_id"])
            _by_member_measure.setdefault(key, []).append(row)
    _loaded = True


def lookup_care_gap_by_id(gap_id: str) -> dict[str, Any]:
    """Look up a care gap record by its gap_id.

    Args:
        gap_id: The gap_id field from the campaign_disposition row (e.g. 'GAP000435').

    Returns a dict with 'found' (bool) and either 'care_gap' (the matched row) or
    'message' explaining the miss. Always call this first before the member/measure fallback.
    """
    _load()
    row = _by_gap_id.get(gap_id)
    if row:
        return {"found": True, "care_gap": dict(row)}
    return {"found": False, "message": f"No care gap found for gap_id '{gap_id}'"}


def lookup_care_gap_by_member_measure(member_id: str, measure_id: str) -> dict[str, Any]:
    """Fallback lookup: find care gaps for a member and measure combination.

    Use this only when lookup_care_gap_by_id returns found=False. Returns matches ordered
    by Open status first, then most recent due_date — so the best candidate is always first.

    Args:
        member_id: The member_id from the campaign_disposition row (e.g. 'MBR00159').
        measure_id: The measure_id from the campaign_disposition row (e.g. 'TRC').

    Returns a dict with 'found' (bool), 'count', and either 'care_gaps' (list of matched
    rows, best candidate first) or 'message' explaining the miss.
    """
    _load()
    rows = _by_member_measure.get((member_id, measure_id), [])
    if rows:
        sorted_rows = sorted(
            rows,
            key=lambda r: (r["gap_status"] != "Open", r.get("due_date", "") or ""),
            reverse=False,
        )
        return {"found": True, "count": len(sorted_rows), "care_gaps": sorted_rows}
    return {
        "found": False,
        "message": f"No care gaps found for member_id '{member_id}' and measure_id '{measure_id}'",
    }
