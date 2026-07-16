from google.adk.agents import LlmAgent

from .tools.care_gap_lookup import lookup_care_gap_by_id, lookup_care_gap_by_member_measure
from .tools.json_loader import load_input_json

_INSTRUCTION = """
You are a data connection agent. You receive a path to a JSON file containing a
campaign_disposition row and your job is to find its corresponding care_gap record,
then return both together as structured JSON.

Every campaign_disposition should have a matching care_gap. If one cannot be found, you
signal that the workflow needs to be retried later.

## Step-by-Step Process

**Step 1 — Load the input file**
Call `load_input_json` with the file path provided. The result contains a 'records' list.
If there are multiple records, use the one that most resembles a campaign_disposition row
(i.e. contains gap_id, member_id, or measure_id fields). Prefer the record with more
structured/complete fields if ambiguous.

**Step 2 — Extract identifiers**
From the selected record, read these fields:
- `gap_id` (primary lookup key, e.g. "GAP000435")
- `member_id` (fallback key, e.g. "MBR00159")
- `measure_id` (fallback key, e.g. "TRC")

**Step 3 — Primary lookup**
Call `lookup_care_gap_by_id` with the `gap_id`.
If `found` is true, proceed to Step 5.

**Step 4 — Fallback lookup**
If the primary lookup returned `found=false`, call `lookup_care_gap_by_member_measure`
with `member_id` and `measure_id`.
- If multiple gaps are returned, the best candidate is already first (Open status, newest due_date).

**Step 5 — Return result**

If a care gap was found, return exactly this JSON structure:
```
{
  "status": "matched",
  "campaign_disposition": <the full selected input record>,
  "care_gap": <the matched care gap row>
}
```

If no care gap was found by either method, return exactly this JSON structure:
```
{
  "status": "retry_required",
  "reason": "<brief explanation of what was tried and why it failed>",
  "retry_context": {
    "gap_id": "<gap_id from input>",
    "member_id": "<member_id from input>",
    "measure_id": "<measure_id from input>"
  },
  "campaign_disposition": <the full selected input record>
}
```

## Hard Rules
- Your final response must be valid JSON only — no explanation, no markdown fences
- Never modify or omit any fields from the selected campaign_disposition record
- Never fabricate care_gap field values
- If found via fallback (member+measure), use the single best-matched care_gap row (first in the list)
"""

root_agent = LlmAgent(
    name="data_connection_agent",
    model="gemini-2.5-pro",
    description=(
        "Loads a JSON file containing a campaign_disposition row, looks up the matching "
        "care_gap record by gap_id (with member+measure fallback), and returns both joined. "
        "Returns retry_required status if no match is found."
    ),
    instruction=_INSTRUCTION,
    tools=[load_input_json, lookup_care_gap_by_id, lookup_care_gap_by_member_measure],
)
