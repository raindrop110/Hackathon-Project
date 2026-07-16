"""
test_comparison_agent — End-to-end eval pipeline for the disposition normalization system.

3-stage SequentialAgent pipeline:

  Stage 1 — test_data_generator
    Generates COMPARISON_BATCH_SIZE synthetic disposition records with ground-truth labels
    using the same corpus and rules as the main data generation pipeline.
    → state["ground_truth_data"]

  Stage 2 — batch_normalizer
    Reads each record's raw_payload from state["ground_truth_data"] and independently
    normalizes it using the same logic as disposition_normalization/summarization_agent —
    WITHOUT looking at the ground-truth labels already on the record.
    → state["normalization_results"]

  Stage 3 — accuracy_comparator
    Compares normalization output against ground truth field by field and produces:
      - Overall record accuracy percentage (all 4 fields correct)
      - Per-field accuracy breakdown (disposition_code, care_gap_status, responded, action_taken)
      - Per-source-type accuracy (call_transcript, ivr_result_code, csr_note, web_form)
      - Confidence-stratified accuracy (high vs low confidence records)
      - Full mismatch list
    → state["comparison_report"]

Run with:
    adk web test_comparison_agent
    adk run test_comparison_agent
"""

import os

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, SequentialAgent

from .schemas import ComparisonReport, NormalizationBatch, TestBatch
from .tools import build_corpus_context

load_dotenv()

MODEL = "gemini-2.5-pro"
BATCH_SIZE: int = int(os.getenv("COMPARISON_BATCH_SIZE", "10"))

# Pre-load corpus once at import — same corpus as rag_data_generation pipeline.
_CORPUS_CONTEXT: str = build_corpus_context()


# ---------------------------------------------------------------------------
# Stage 1 — Test Data Generator
# ---------------------------------------------------------------------------

_GENERATE_INSTRUCTION = f"""
You are a synthetic healthcare data generator for pipeline evaluation testing.

═══════════════════════════════════════════════════════════
SINGLE RESPONSIBILITY
═══════════════════════════════════════════════════════════
Generate exactly {BATCH_SIZE} synthetic disposition records with CORRECT ground-truth labels.
These records will be used to test the normalization pipeline — the raw_payload is what
the normalizer will see; all other fields are the expected correct output.

Write your output to state key "ground_truth_data".

═══════════════════════════════════════════════════════════
REFERENCE CORPUS
═══════════════════════════════════════════════════════════
{_CORPUS_CONTEXT}

═══════════════════════════════════════════════════════════
GENERATION RULES
═══════════════════════════════════════════════════════════
SOURCE TYPE DISTRIBUTION (total = {BATCH_SIZE}):
  - call_transcript : ~25% (at least 2)
  - ivr_result_code : ~25% (at least 2)
  - csr_note        : ~25% (at least 2)
  - web_form        : ~25% (at least 2)

OUTCOME DISTRIBUTION:
  - closed               : ~30% — service confirmed, gap creditable
  - attempted_not_closed : ~40% — member reached but gap not closed
  - open_no_contact      : ~20% — member not reached
  - invalid              : ~10% — wrong number / deceased / bad address

MEASURE VARIETY — use at least 5 different HEDIS measures:
  AWC, CBP, CDC-H, COA, COL, FUH, MRP, OMW, SPC, TRC

ID CONVENTIONS:
  - member_id   : MBR00001–MBR00200
  - record_id   : REC-000001–REC-999999
  - hedis_measure : same as care_gap_id

RAW PAYLOAD FORMATS:
  call_transcript : Multi-turn AGENT:/MEMBER: dialogue, 4-12 lines, ending with
                    [Call ended — outcome note]. Include member_id and measure in header.
  ivr_result_code : JSON-like object with ivr_session_id, member_id, raw_result_code
                    (from ivr_codes corpus), ivr_tree_path, duration_seconds.
  csr_note        : 1-4 sentence free-text note. May include shorthand (VM, WN, SCHED).
  web_form        : JSON-like object with submission_id, completion_status, fields_completed,
                    total_fields, member_responses.

TRICKY RECORDS — include at least 3:
  (a) Self-reported completion, no claim → DISP-COMP-UV, attempted_not_closed
  (b) IVR says scheduled but transcript shows refusal → DISP-REFUS
  (c) Wrong-number, next-of-kin reports deceased → DISP-EXCL, invalid
  (d) Partial web form with embedded self-report → DISP-COMP-UV
  (e) Ambiguous SMS reply → confidence ≤ 0.60

CONFIDENCE (float 0.0–1.0):
  0.90–0.99 : clear, unambiguous
  0.75–0.89 : mostly clear
  0.50–0.74 : ambiguous / tricky
  0.35–0.49 : very low signal

CODE VALIDITY — use ONLY values from corpus:
  - disposition_code : one of the "code" values in disposition_codes corpus
  - action_taken     : one of the "maps_to_action" values in disposition_codes corpus
  - care_gap_status  : closed | attempted_not_closed | open_no_contact | invalid

═══════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════
Return ONLY valid JSON matching the TestBatch schema.
Required keys: batch_id, generated_at, batch_size, records.
Each record must have: record_id, source_type, member_id, hedis_measure, raw_payload,
  care_gap_status, disposition_code, responded, action_taken, confidence.
batch_id format: BATCH-YYYYMMDD-HHMMSS
"""

test_data_generator = LlmAgent(
    name="test_data_generator",
    model=MODEL,
    description=(
        f"Generates {BATCH_SIZE} synthetic disposition records with ground-truth labels "
        "across all 4 source types and a realistic outcome distribution."
    ),
    instruction=_GENERATE_INSTRUCTION,
    output_key="ground_truth_data",
    output_schema=TestBatch,
)


# ---------------------------------------------------------------------------
# Stage 2 — Batch Normalizer
# ---------------------------------------------------------------------------

_NORMALIZE_INSTRUCTION = f"""
You are a healthcare disposition normalization agent performing batch evaluation.

═══════════════════════════════════════════════════════════
SINGLE RESPONSIBILITY
═══════════════════════════════════════════════════════════
Read the test records from state key "ground_truth_data" (in the conversation context
above as the previous step's output). For each record, look ONLY at raw_payload and
independently determine the normalized disposition — do NOT use the ground-truth labels
already present on the record.

Write your output to state key "normalization_results".

═══════════════════════════════════════════════════════════
WHAT TO NORMALIZE (from raw_payload only)
═══════════════════════════════════════════════════════════
For each record, determine:

1. disposition_code — canonical DISP-XXX code from corpus
2. care_gap_status  — closed | attempted_not_closed | open_no_contact | invalid
3. responded        — true if member was reached / had any interaction; false if no contact
4. action_taken     — canonical action from disposition_codes corpus
5. confidence       — "high" | "medium" | "low"
     "high"   : clear, unambiguous signal in raw_payload (≥0.80 certainty)
     "medium" : mostly clear with minor uncertainty (0.60–0.79)
     "low"    : ambiguous, conflicting, or very sparse signal (<0.60)

═══════════════════════════════════════════════════════════
NORMALIZATION RULES
═══════════════════════════════════════════════════════════
{_CORPUS_CONTEXT}

STATUS COHERENCE:
  care_gap_status="closed"             → action_taken="already_completed" AND responded=true
  care_gap_status="open_no_contact"    → responded=false
  care_gap_status="invalid"            → action_taken in [wrong_number, excluded, no_action]
  care_gap_status="attempted_not_closed" → responded=true (usually)

Self-reported completion (no verified claim) → DISP-COMP-UV, attempted_not_closed
IVR code shows scheduled but transcript shows refusal → DISP-REFUS, refused
Deceased / wrong number → DISP-EXCL or DISP-WN, invalid

═══════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════
Return ONLY valid JSON matching the NormalizationBatch schema.
Required keys: batch_id, total_records, records.
Use the same batch_id from state["ground_truth_data"].
Each record must have: record_id, confidence, disposition_code, care_gap_status,
  responded, action_taken.
Process ALL records — do not skip any.
"""

batch_normalizer = LlmAgent(
    name="batch_normalizer",
    model=MODEL,
    description=(
        "Reads each raw_payload from the test batch and independently normalizes it "
        "using the same normalization logic as the disposition_normalization pipeline."
    ),
    instruction=_NORMALIZE_INSTRUCTION,
    output_key="normalization_results",
    output_schema=NormalizationBatch,
)


# ---------------------------------------------------------------------------
# Stage 3 — Accuracy Comparator
# ---------------------------------------------------------------------------

_COMPARE_INSTRUCTION = """
You are an accuracy measurement agent for the disposition normalization pipeline.

═══════════════════════════════════════════════════════════
SINGLE RESPONSIBILITY
═══════════════════════════════════════════════════════════
Read state["ground_truth_data"] (ground-truth labels) and state["normalization_results"]
(what the normalizer produced) from the conversation context above.

Match records by record_id. Compare these 4 fields per record:
  1. disposition_code
  2. care_gap_status
  3. responded (boolean — true/false must match exactly)
  4. action_taken

Write your output to state key "comparison_report".

═══════════════════════════════════════════════════════════
SCORING DEFINITIONS
═══════════════════════════════════════════════════════════
Field match: ground_truth value == normalized value (case-insensitive for strings,
  exact for booleans). null normalized values count as incorrect.

Record fully correct: ALL 4 fields match for that record.

record_accuracy_pct = (records_fully_correct / total_records) × 100

field_accuracy: for each of the 4 fields:
  correct = count of records where that field matches
  total = total_records
  accuracy_pct = (correct / total) × 100

accuracy_by_source_type: for each source type, compute:
  percentage of records of that type that are fully correct (all 4 fields)

confidence stratification:
  Map normalization confidence → level:
    "high"   → high stratum
    "medium" → (exclude from stratified metrics)
    "low"    → low stratum
  high_confidence_record_accuracy_pct = fully_correct among "high" records / total "high" × 100
  low_confidence_record_accuracy_pct  = fully_correct among "low" records  / total "low"  × 100
  If a stratum has 0 records, set its accuracy_pct to 0.0.

mismatches: collect every (record_id, field) pair where values differ.
  Include source_type, hedis_measure (from ground_truth record), ground_truth value,
  normalized value, and normalization_confidence.

total_field_mismatches = len(mismatches)

═══════════════════════════════════════════════════════════
SUMMARY NARRATIVE
═══════════════════════════════════════════════════════════
Write 3-4 sentences covering:
  - Overall record accuracy and which field had the highest/lowest accuracy
  - Whether low-confidence records explain most of the errors
  - Which source type the normalizer handles best vs worst
  - The most common type of mismatch (e.g., over-closing gaps, wrong action codes)

═══════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════
Return ONLY valid JSON matching the ComparisonReport schema.
Required keys: batch_id, total_records, records_fully_correct, record_accuracy_pct,
  field_accuracy, accuracy_by_source_type, high_confidence_record_accuracy_pct,
  low_confidence_record_accuracy_pct, total_field_mismatches, mismatches, summary.
All percentage values are 0.0–100.0 floats.
"""

accuracy_comparator = LlmAgent(
    name="accuracy_comparator",
    model=MODEL,
    description=(
        "Compares normalization output against ground-truth labels and produces "
        "overall accuracy %, per-field breakdown, per-source-type breakdown, "
        "confidence-stratified accuracy, and a full mismatch list."
    ),
    instruction=_COMPARE_INSTRUCTION,
    output_key="comparison_report",
    output_schema=ComparisonReport,
)


# ---------------------------------------------------------------------------
# Root Agent — 3-stage SequentialAgent pipeline
# ---------------------------------------------------------------------------

root_agent = SequentialAgent(
    name="test_comparison_agent",
    description=(
        "3-stage evaluation pipeline that benchmarks the disposition normalization pipeline: "
        "(1) test_data_generator creates synthetic records with ground-truth labels; "
        "(2) batch_normalizer independently normalizes each raw_payload; "
        "(3) accuracy_comparator compares results field-by-field and reports overall "
        "accuracy percentage with per-field, per-source-type, and confidence-stratified breakdowns."
    ),
    sub_agents=[
        test_data_generator,
        batch_normalizer,
        accuracy_comparator,
    ],
)
