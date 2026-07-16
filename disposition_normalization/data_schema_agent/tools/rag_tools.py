from typing import Any

from .csv_loader import all_datasets, dataset_names, get_rows

_DESCRIPTIONS: dict[str, str] = {
    "campaign_dispositions": (
        "Outreach campaign attempts: channels (IVR, Mail, Call Center, Web Form), "
        "raw disposition codes (Wrong number, NO_RESPONSE, REFUSED, PARTIAL_SUBMIT, etc.), "
        "CSR notes, action taken, gap credit status, actual completion likelihood"
    ),
    "care_gaps": (
        "HEDIS measure care gaps per member: measure ID (CBP, TRC, COL, CDC-H, OMW, SPC, MRP, COA), "
        "gap status (Open/Closed), due dates, last service date, outreach attempt count"
    ),
    "claims": (
        "Insurance claims: CPT codes, diagnosis codes, claim status (Paid/Denied/In Review), "
        "denial codes (CO-97, CO-109, CO-50), denial reasons, prior auth, billed/paid amounts, "
        "modifier mismatch, reprocessing days"
    ),
    "members": (
        "Member demographics: age, gender, plan type (HMO/PPO/MAPD/DSNP), "
        "chronic conditions (diabetes, hypertension, cardiovascular), enrollment dates, preferred language"
    ),
    "providers": "Provider NPI, name, specialty, network status, location",
    "appointment_slots": "Available appointment slots: provider, date/time, slot status, specialty",
    "compliance_flags": (
        "Compliance violations: flag type, severity (Medium/High), entity type (Provider/Member), "
        "flag date, denial rate percentage metric"
    ),
    "roi_authorizations": (
        "Release of Information authorizations: authorization status, requester, member ID, dates"
    ),
    "coverage_rules": "CPT code coverage rules: prior auth requirements, coverage status, payer rules",
    "segment_performance": (
        "Performance metrics by demographic segment: measure scores, gap counts, outreach rates"
    ),
    "stars_performance": "HEDIS star ratings summary: measure-level star scores, year-over-year trends",
    "historical_interventions": "Past intervention outcomes: intervention type, cost, ROI, success rate",
}


def list_available_schemas() -> dict[str, Any]:
    """List all available structured dataset schemas with their descriptions.

    Returns a mapping of dataset name to a description of what data it contains.
    Call this first to understand which dataset best matches the unstructured input.
    """
    return {
        "datasets": {
            name: _DESCRIPTIONS.get(name, "")
            for name in dataset_names()
        }
    }


def get_schema(dataset_name: str) -> dict[str, Any]:
    """Get the full schema for a dataset: column names, sample values per column, and row count.

    Args:
        dataset_name: The dataset name returned by list_available_schemas or search_by_keywords.

    Returns a dict with 'columns' (ordered list), 'sample_values' (up to 5 distinct values per
    column), 'row_count', and the dataset description.
    """
    rows = get_rows(dataset_name)
    if not rows:
        return {"error": f"Dataset '{dataset_name}' not found. Call list_available_schemas to see valid names."}

    columns = list(rows[0].keys())
    sample_values: dict[str, list[str]] = {}
    for col in columns:
        seen: list[str] = []
        for row in rows:
            val = row.get(col, "")
            if val and val not in seen:
                seen.append(val)
            if len(seen) >= 5:
                break
        sample_values[col] = seen

    return {
        "dataset": dataset_name,
        "description": _DESCRIPTIONS.get(dataset_name, ""),
        "row_count": len(rows),
        "columns": columns,
        "sample_values": sample_values,
    }


def get_examples(dataset_name: str, n: int = 3) -> dict[str, Any]:
    """Get real example rows from a dataset to use as a formatting reference.

    Args:
        dataset_name: The dataset name returned by list_available_schemas or search_by_keywords.
        n: Number of example rows to return (default 3, capped at 10).

    Returns a dict with 'dataset', 'columns', and 'examples' (list of row dicts).
    Use these examples to understand exact value formats, casing, and conventions before
    mapping unstructured input to the schema.
    """
    rows = get_rows(dataset_name)
    if not rows:
        return {"error": f"Dataset '{dataset_name}' not found. Call list_available_schemas to see valid names."}

    n = min(n, 10, len(rows))
    return {
        "dataset": dataset_name,
        "columns": list(rows[0].keys()),
        "examples": rows[:n],
    }


def search_by_keywords(keywords: list[str]) -> dict[str, Any]:
    """Find the most relevant datasets based on keywords extracted from the unstructured input.

    Args:
        keywords: Domain terms from the input, e.g. ["denial", "CO-109", "claim"] or
                  ["care gap", "TRC", "outreach", "IVR"]. Include IDs, codes, and concept names.

    Returns datasets ranked by keyword match score. Use the top result as the target schema.
    If multiple datasets score equally, call get_schema on each to decide.
    """
    data = all_datasets()
    scores: dict[str, int] = {}

    for name, rows in data.items():
        searchable = name + " " + _DESCRIPTIONS.get(name, "")
        if rows:
            searchable += " " + " ".join(rows[0].keys())
            for row in rows[:5]:
                searchable += " " + " ".join(str(v) for v in row.values())
        searchable = searchable.lower()

        scores[name] = sum(1 for kw in keywords if kw.lower() in searchable)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top = [(name, score) for name, score in ranked if score > 0][:5]

    if not top:
        # No keyword hit — return top 3 candidates without score filter
        top = ranked[:3]

    return {
        "keywords_used": keywords,
        "matches": [
            {
                "dataset": name,
                "score": score,
                "description": _DESCRIPTIONS.get(name, ""),
            }
            for name, score in top
        ],
    }
