"""
agent.py — generation_quality_agent: scores a synthetic data batch against real data.

This is the third of three workflows that fire on every file upload:
  1. disposition_normalization  — processes the real uploaded file, ends with a
     structured summary (disposition_summarization_agent's output).
  2. rag_data_generation         — generates + SME-validates a batch of synthetic
     disposition records, informed by the uploaded file.
  3. generation_quality_agent (here) — takes #1's summary and #2's entire batch and
     scores EVERY synthetic record against the one real record across 5 alignment
     dimensions, producing a heatmap-ready report: does the generator's output
     actually resemble real production data?

Unlike the other two pipelines, this agent's instruction is built fresh per call
from run-specific data (the real summary + the synthetic batch) rather than from
static corpus files — see build_generation_quality_agent below and
pipeline_runner.py for the orchestration that calls it after both #1 and #2 finish.

Run with:
    adk web test_comparison_agent
    adk run test_comparison_agent
(the CLI root_agent below uses placeholder/empty inputs since real data only
exists at request time — genuinely useful runs go through pipeline_runner.py.)
"""

import json
from typing import Any

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

from .schemas import GenerationQualityReport

load_dotenv()

MODEL = "gemini-2.5-pro"

# Sentinels substituted via str.replace() rather than f-string/str.format() — the
# real summary and synthetic records are arbitrary JSON and can contain literal
# `{`/`}` that .format() would try to parse as fields.
_REAL_SUMMARY_PLACEHOLDER = "__REAL_SUMMARY_PLACEHOLDER__"
_SYNTHETIC_RECORDS_PLACEHOLDER = "__SYNTHETIC_RECORDS_PLACEHOLDER__"
_BATCH_ID_PLACEHOLDER = "__BATCH_ID_PLACEHOLDER__"

_QUALITY_INSTRUCTION_TEMPLATE = """
You are a data-generation quality analyst. Your job is to score how well a BATCH of
synthetic disposition records resembles ONE real disposition record extracted from
actual production data — a proxy for "how good is our synthetic data generator?"

═══════════════════════════════════════════════════════════
SINGLE RESPONSIBILITY
═══════════════════════════════════════════════════════════
Score EVERY record in the synthetic batch against the real reference record across
the 5 dimensions below. Write your output to state key "generation_quality_report".
Use this exact batch_id in your output: __BATCH_ID_PLACEHOLDER__

═══════════════════════════════════════════════════════════
REAL REFERENCE RECORD (extracted from an actual uploaded file by
disposition_summarization_agent)
═══════════════════════════════════════════════════════════
""" + _REAL_SUMMARY_PLACEHOLDER + """

═══════════════════════════════════════════════════════════
SYNTHETIC BATCH TO SCORE (generated + SME-validated by rag_data_generation)
═══════════════════════════════════════════════════════════
""" + _SYNTHETIC_RECORDS_PLACEHOLDER + """

═══════════════════════════════════════════════════════════
SCORING DIMENSIONS (0-100 each, per synthetic record)
═══════════════════════════════════════════════════════════
1. measure_alignment — how well does the record's hedis_measure/care_gap_id match
   or plausibly relate to the real record's measure_id/measure_name?
2. channel_alignment — how well does source_type match the real record's
   channel/interaction_type?
3. disposition_plausibility — do care_gap_status/action_taken represent a plausible
   outcome given the real record's service_completed/member_refused/successful_contact?
4. confidence_calibration — is the record's confidence in a similar band to the real
   record's confidence (map the real record's "high"/"medium"/"low" to roughly
   0.85/0.65/0.45 for comparison)?
5. structural_realism — does raw_payload's structure/style look like something that
   could plausibly have produced a summary shaped like the real one?

overall = mean of the 5 dimension scores for that record.

If the real reference record is missing or empty, still score every synthetic
record using only general realism/internal-consistency judgment for each
dimension, and say so plainly in the narrative.

═══════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════
Return ONLY a valid JSON object matching the GenerationQualityReport schema.
Do NOT include markdown fences, commentary, or extra keys.
dimensions must be exactly: ["measure_alignment", "channel_alignment",
  "disposition_plausibility", "confidence_calibration", "structural_realism"]
cells must have exactly one entry per record in the synthetic batch — do not skip any.
overall_score = mean of all cells' overall scores.
narrative: 3-4 sentences on what this run reveals about generator quality — strong
  across the board, struggles with a particular dimension or source type, etc.
"""

_GENERATION_QUALITY_AGENT_DESCRIPTION = (
    "Scores an entire batch of synthetic disposition records against one real "
    "disposition summary across 5 alignment dimensions, producing a heatmap-ready "
    "generator-quality report."
)


def _sanitize_json(obj: Any) -> str:
    """Serialize to JSON and swap ASCII braces for full-width lookalikes so ADK's
    {state_var} template regex never mistakes real JSON structure for a state ref."""
    raw = json.dumps(obj, indent=2, ensure_ascii=False)
    return raw.replace("{", "｛").replace("}", "｝")


def build_generation_quality_agent(
    batch_id: str,
    real_summary: dict | None,
    synthetic_records: list[dict],
) -> LlmAgent:
    """Fresh per-call — instruction is built from this run's actual data, not a
    static corpus, so there's nothing meaningful to cache at import time."""
    instruction = (
        _QUALITY_INSTRUCTION_TEMPLATE.replace(
            _REAL_SUMMARY_PLACEHOLDER, _sanitize_json(real_summary or {})
        )
        .replace(_SYNTHETIC_RECORDS_PLACEHOLDER, _sanitize_json(synthetic_records))
        .replace(_BATCH_ID_PLACEHOLDER, batch_id)
    )
    return LlmAgent(
        name="generation_quality_agent",
        model=MODEL,
        description=_GENERATION_QUALITY_AGENT_DESCRIPTION,
        instruction=instruction,
        output_key="generation_quality_report",
        output_schema=GenerationQualityReport,
    )


# CLI convenience (`adk web test_comparison_agent`) — empty placeholder inputs so
# the module import succeeds; genuinely useful runs go through pipeline_runner.py.
root_agent = build_generation_quality_agent("BATCH-EXAMPLE", None, [])
