"""
agent.py — 3-stage SequentialAgent pipeline for RAG Data Generation.

Pipeline stages
---------------
1. generate_data_agent   : Synthesise BATCH_SIZE realistic disposition records with
                           ground-truth labels, grounded in the HEDIS/IVR/code corpus.
2. sme_validator_agent   : Clinical SME review — validate, correct, or reject each
                           record for internal consistency and code compliance.
3. summary_generator_agent: Compute aggregate statistics and produce a golden-dataset
                            summary consumed by the downstream Comparison step.

Architecture note — output_schema vs. tools
--------------------------------------------
ADK does not allow `tools` and `output_schema` on the same LlmAgent (Gemini cannot
simultaneously be in JSON-controlled-generation mode and open function-calling mode).

Chosen resolution: corpus context is pre-loaded at module import time via
`build_corpus_context()` and injected directly into the `instruction` strings of
generate_data_agent and sme_validator_agent.  The `retrieve_reference_tool` FunctionTool
still exists in tools.py and is ready to attach to any future non-schema agent.

To swap in Vertex AI RAG Engine: see the SWAP SEAM comments in tools.py.
"""

import os

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, SequentialAgent

from .schemas import DatasetSummary, GeneratedDataset, ValidatedDataset
from .tools import build_corpus_context

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "gemini-2.5-flash"  # change this constant to switch models globally
BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "10"))

# Pre-load full corpus context once at import time.
# SWAP SEAM: remove this line when Vertex AI RAG is wired up.
_CORPUS_CONTEXT: str = build_corpus_context()


# ---------------------------------------------------------------------------
# Agent 1 — Generate Data Agent
# ---------------------------------------------------------------------------

_GENERATE_INSTRUCTION = f"""
You are a synthetic healthcare data generator specialising in Medicare/Medicaid care-gap
outreach disposition records.

═══════════════════════════════════════════════════════════
SINGLE RESPONSIBILITY
═══════════════════════════════════════════════════════════
Generate exactly {BATCH_SIZE} synthetic raw campaign disposition items — one per record —
covering ALL four source types (call_transcript, ivr_result_code, csr_note, web_form)
and a realistic mix of outcomes.  For each item also produce the CORRECT expected
normalized disposition (the ground-truth label).

Write your output to state key "generated_data".

═══════════════════════════════════════════════════════════
REFERENCE CORPUS (pre-loaded from local JSON files;
in production this will come from a Vertex AI RAG Engine corpus)
═══════════════════════════════════════════════════════════
{_CORPUS_CONTEXT}

═══════════════════════════════════════════════════════════
GENERATION RULES
═══════════════════════════════════════════════════════════
BATCH SIZE & SOURCE TYPE DISTRIBUTION (total = {BATCH_SIZE}):
  - call_transcript : ~25 % of records (at least 2)
  - ivr_result_code : ~25 % of records (at least 2)
  - csr_note        : ~25 % of records (at least 2)
  - web_form        : ~25 % of records (at least 2)

OUTCOME DISTRIBUTION:
  - closed                  : ~30 % — service confirmed, gap creditable
  - attempted_not_closed    : ~40 % — member reached but gap not closed
  - open_no_contact         : ~20 % — member not reached
  - invalid                 : ~10 % — wrong number, deceased, bad address

MEASURE VARIETY — use at least 5 different measures from the corpus:
  AWC, CBP, CDC-H, COA, COL, FUH, MRP, OMW, SPC, TRC

ID CONVENTIONS (match real hackathon data):
  - member_id : MBR00001–MBR00200  (e.g., MBR00042)
  - provider_id : PRV0001–PRV0050 or null  (e.g., PRV0017)
  - record_id : REC-000001–REC-999999  (e.g., REC-000007)
  - care_gap_id : same as hedis_measure  (e.g., COL, CBP, TRC)

RAW PAYLOAD FORMATS:
  call_transcript:
    Multi-turn dialogue. Include AGENT: and MEMBER: lines (4-12 lines total).
    End with a bracketed summary line: [Call ended — brief outcome note]
    Optionally add: CSR NOTES: <short free-text>
    Example opening: "Date: 2026-03-14 | Member ID: MBR00042 | Gap ID: GAP000123 | Measure: COL"

  ivr_result_code:
    JSON-like object containing: ivr_session_id, member_id, gap_id, measure_id,
    call_date, ivr_tree_path (array of menu choices), raw_result_code, duration_seconds,
    transferred_to (null or "live_agent"/"nurse_line"/"interpreter").
    Use raw_result_codes from the ivr_codes corpus.

  csr_note:
    1-4 sentences of plain prose as entered by a CSR.  May include shorthand
    (VM, WN, SCHED, COMP_STATED, LANG_BARRIER).  Should reference member_id and
    measure context naturally.

  web_form:
    JSON-like object containing: submission_id, member_id, gap_id, measure_id,
    submitted_at, form_version, completion_status (COMPLETE / PARTIAL / ABANDONED),
    fields_completed (int), total_fields (int), member_responses (object with form
    field answers).

CODE VALIDITY — use ONLY values from the corpus:
  - disposition_code : one of the "code" values in disposition_codes corpus
  - action_taken     : one of the "maps_to_action" values in disposition_codes corpus
  - care_gap_status  : closed | attempted_not_closed | open_no_contact | invalid
  - hedis_measure / care_gap_id : from measures list in hedis_measures corpus

TRICKY / AMBIGUOUS RECORDS (include at least 3):
  Use the edge cases described in care_gap_definitions corpus:
  (a) Member self-reports completion but no claim exists → DISP-COMP-UV, attempted_not_closed
  (b) IVR raw_code says "Member confirmed appointment scheduled" but transcript body
      shows member actually refused → use refused / DISP-REFUS
  (c) Wrong-number call where next-of-kin reveals member is deceased → DISP-EXCL / invalid
  (d) Partial web form that contains embedded self-report of completion → DISP-COMP-UV
  (e) SMS REPLIED_YES to an ambiguous prompt → engaged_sms / attempted_not_closed, confidence ≤0.60

CONFIDENCE SCORING:
  - 0.90–0.99 : clear, unambiguous cases
  - 0.75–0.89 : mostly clear but minor uncertainty
  - 0.50–0.74 : ambiguous or tricky cases
  - 0.35–0.49 : very low signal, high ambiguity

INITIAL VALIDATION FIELDS:
  - validation_status : "valid" for ALL generated records (SME agent updates this)
  - validation_notes  : "" (empty string) for ALL generated records

═══════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════
Return ONLY a valid JSON object matching the GeneratedDataset schema.
Do NOT include markdown fences, commentary, or extra keys.
Required top-level keys: records, batch_id, generated_at, batch_size.
batch_id format: BATCH-YYYYMMDD-HHMMSS  (use a plausible 2026 datetime)
generated_at format: ISO-8601 UTC string
"""

generate_data_agent = LlmAgent(
    name="generate_data_agent",
    model=MODEL,
    description=(
        "Synthesises a batch of realistic synthetic care-gap outreach disposition records "
        "across all four source types, with correct ground-truth normalised labels, "
        "grounded in the HEDIS/IVR/disposition code corpus."
    ),
    instruction=_GENERATE_INSTRUCTION,
    output_key="generated_data",
    output_schema=GeneratedDataset,
    # No tools here — output_schema + tools cannot coexist on the same LlmAgent in ADK.
    # Corpus data is pre-loaded into the instruction string above.
    # SWAP SEAM: to use live Vertex AI RAG, remove output_schema and add a preceding
    # retrieval agent that writes corpus to state, then reference it here.
)


# ---------------------------------------------------------------------------
# Agent 2 — SME Data Validator Agent
# ---------------------------------------------------------------------------

_VALIDATE_INSTRUCTION = f"""
You are a clinical and business subject-matter expert (SME) performing quality assurance
on synthetic healthcare care-gap disposition data.

═══════════════════════════════════════════════════════════
SINGLE RESPONSIBILITY
═══════════════════════════════════════════════════════════
Read the generated dataset from state key "generated_data".
Validate every record against the HEDIS specifications, disposition code rules,
and clinical coherence requirements.  Fix correctable errors in-place, reject
unsalvageable records, and attach validation_status + validation_notes to each.

Write your output to state key "validated_data".

═══════════════════════════════════════════════════════════
HOW TO READ THE INPUT
═══════════════════════════════════════════════════════════
The generated_data is available in the conversation context above (output of the
previous pipeline step) and also as session state["generated_data"].
Parse the JSON and process every record in the "records" array.

═══════════════════════════════════════════════════════════
REFERENCE CORPUS (pre-loaded; Vertex AI RAG Engine in production)
═══════════════════════════════════════════════════════════
{_CORPUS_CONTEXT}

═══════════════════════════════════════════════════════════
VALIDATION CHECKLIST — apply to EVERY record
═══════════════════════════════════════════════════════════
1. MEASURE CONSISTENCY
   - hedis_measure must be a valid measure_id in the corpus (AWC/CBP/CDC-H/COA/COL/FUH/MRP/OMW/SPC/TRC)
   - care_gap_id must equal hedis_measure (they are the same in this dataset)

2. DISPOSITION CODE VALIDITY
   - disposition_code must be one of the "code" values in the disposition_codes corpus
   - action_taken must match the "maps_to_action" of that disposition_code

3. IVR CODE VALIDITY (for ivr_result_code source_type)
   - raw_payload must contain a raw_result_code that exists in ivr_codes corpus
   - The expected action_taken must match what the IVR code maps to

4. STATUS COHERENCE RULES (from care_gap_definitions corpus):
   - care_gap_status="closed"  → action_taken MUST be "already_completed"  AND responded=true
     (NOT "already_completed_unverified" — self-reports cannot close a gap)
   - care_gap_status="open_no_contact"  → responded MUST be false
   - care_gap_status="invalid"  → action_taken MUST be one of:
     wrong_number, excluded, no_action (for address invalid)
   - care_gap_status="attempted_not_closed"  → responded SHOULD be true
     (exception: opted_out, language_barrier may have responded=true even if gap not closed)

5. RESPONSE COHERENCE
   - response_summary must logically match raw_payload content
   - If raw_payload shows a refusal, action_taken must be "refused", not "scheduled_appt"
   - Unverified self-reports must use DISP-COMP-UV, NOT DISP-CLOSED

6. CONFIDENCE VALIDITY
   - Must be between 0.0 and 1.0
   - Tricky/ambiguous records should have confidence ≤0.75
   - Clear, unambiguous records should have confidence ≥0.80

7. REQUIRED FIELDS
   - record_id, source_type, raw_payload, member_id, care_gap_id, hedis_measure,
     response_summary, action_taken, disposition_code must all be non-empty strings
   - responded, care_gap_status, confidence, validation_status must be present

═══════════════════════════════════════════════════════════
VALIDATION ACTIONS
═══════════════════════════════════════════════════════════
For each record, set:
  validation_status = "valid"     → all checks passed, no changes needed
  validation_status = "corrected" → you fixed one or more fields; describe what and why
  validation_status = "rejected"  → record is fundamentally broken and cannot be fixed
                                    (e.g., measure_id not in corpus, raw_payload empty,
                                     impossible combination that cannot be resolved)

validation_notes must be specific:
  - "valid": "All fields consistent: COL measure, DISP-NOCON code, open_no_contact status, responded=false. IVR code 'No answer / voicemail' correctly mapped."
  - "corrected": "Corrected care_gap_status from 'closed' to 'attempted_not_closed': member self-report (already_completed_unverified) cannot close a gap without claim verification. disposition_code changed from DISP-CLOSED to DISP-COMP-UV."
  - "rejected": "Rejected: hedis_measure 'XYZ' is not in the known measure corpus. Cannot assign valid coding."

═══════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════
Return ONLY a valid JSON object matching the ValidatedDataset schema.
Do NOT include markdown fences, commentary, or extra keys.
Required top-level keys: records, batch_id, validated_at, total_records,
                         valid_count, corrected_count, rejected_count.
validated_at: ISO-8601 UTC string (a few seconds after generated_at)
Counts must correctly reflect the validation_status values in the records array.
"""

sme_validator_agent = LlmAgent(
    name="sme_validator_agent",
    model=MODEL,
    description=(
        "Clinical/business SME agent that reads generated disposition records, "
        "validates measure codes, disposition codes, and status coherence against "
        "the corpus, then fixes or flags each record with validation_status and notes."
    ),
    instruction=_VALIDATE_INSTRUCTION,
    output_key="validated_data",
    output_schema=ValidatedDataset,
    # No tools — same output_schema constraint as Agent 1.
    # Corpus pre-loaded into instruction; previous agent's output is in conversation context.
)


# ---------------------------------------------------------------------------
# Agent 3 — Summary Generator Agent
# ---------------------------------------------------------------------------

_SUMMARY_INSTRUCTION = """
You are a data analytics specialist summarising a validated synthetic healthcare dataset.

═══════════════════════════════════════════════════════════
SINGLE RESPONSIBILITY
═══════════════════════════════════════════════════════════
Read the validated dataset from state key "validated_data" (available in the
conversation context above as the output of the previous pipeline step).
Compute aggregate statistics and produce a structured golden-dataset summary.

Write your output to state key "dataset_summary".

This summary is the artifact consumed downstream by the Comparison step, which
benchmarks a production disposition-ingestion agent against the golden records.

═══════════════════════════════════════════════════════════
WHAT TO COMPUTE
═══════════════════════════════════════════════════════════
1. total_records: total number of records in validated_data.records

2. by_source_type: count records by source_type field
   Keys must be: call_transcript, ivr_result_code, csr_note, web_form

3. by_care_gap_measure: count records by hedis_measure field
   Keys: AWC, CBP, CDC-H, COA, COL, FUH, MRP, OMW, SPC, TRC
   NOTE: in the JSON output key "CDC-H" must be written as "CDC_H"
   (Pydantic alias: the schema field is CDC_H with alias "CDC-H")

4. by_disposition_outcome: count records by care_gap_status field
   Keys: closed, attempted_not_closed, open_no_contact, invalid

5. validation_pass_rate: (valid_count + corrected_count) / total_records as float
   Use the validated_dataset's valid_count and corrected_count fields.

6. notable_edge_cases: list of strings for records where ANY of:
   - confidence < 0.70
   - validation_status = "corrected" OR "rejected"
   - care_gap_status = "invalid"
   Format each entry: "REC-XXXXXX: <one-line description of what makes it notable>"

7. summary_notes: 2-3 sentences covering:
   - Overall dataset quality (validation pass rate, any patterns in corrections)
   - Distribution highlights (dominant measure, dominant outcome)
   - Fitness for use as a Comparison benchmark (are tricky cases well-represented?)

═══════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════
Return ONLY a valid JSON object matching the DatasetSummary schema.
Do NOT include markdown fences, commentary, or extra keys.
Required top-level keys: batch_id, total_records, by_source_type,
  by_care_gap_measure, by_disposition_outcome, validation_pass_rate,
  notable_edge_cases, summary_notes.

For by_care_gap_measure, use the field name "CDC_H" (with underscore) for CDC-H records.
All other measure keys use their standard abbreviation (AWC, CBP, COA, COL, etc.).
"""

summary_generator_agent = LlmAgent(
    name="summary_generator_agent",
    model=MODEL,
    description=(
        "Analytics agent that reads validated disposition records and produces "
        "aggregate statistics by source type, measure, and outcome — plus edge-case "
        "identification — for consumption by the downstream Comparison step."
    ),
    instruction=_SUMMARY_INSTRUCTION,
    output_key="dataset_summary",
    output_schema=DatasetSummary,
    # No tools needed — pure computation over session state data in conversation context.
)


# ---------------------------------------------------------------------------
# Root Agent — 3-stage SequentialAgent pipeline
# ---------------------------------------------------------------------------

root_agent = SequentialAgent(
    name="rag_data_generation",
    description=(
        "3-stage pipeline: "
        "(1) generate_data_agent synthesises BATCH_SIZE synthetic disposition records "
        "with ground-truth labels; "
        "(2) sme_validator_agent performs clinical/business QA on each record; "
        "(3) summary_generator_agent produces the golden-dataset summary for the "
        "downstream Comparison step."
    ),
    sub_agents=[
        generate_data_agent,
        sme_validator_agent,
        summary_generator_agent,
    ],
)
