# RAG Data Generation Sub-System

Generates a **golden dataset** of synthetic care-gap outreach disposition records
(raw input + correct normalised output) for benchmarking the production ingestion agent.

---

## Architecture

```
User trigger message
        │
        ▼
SequentialAgent: rag_data_generation
  │
  ├─ 1. generate_data_agent   ──► state["generated_data"]   (GeneratedDataset)
  │       Synthesises BATCH_SIZE realistic raw disposition items across all four
  │       source types (call transcript, IVR code, CSR note, web form) plus
  │       their correct expected normalised labels, grounded in the HEDIS/IVR/
  │       disposition-code corpus.
  │
  ├─ 2. sme_validator_agent   ──► state["validated_data"]   (ValidatedDataset)
  │       Clinical/business SME reviews each record for measure validity, code
  │       correctness, and status coherence. Fixes or flags issues; attaches
  │       validation_status and validation_notes.
  │
  └─ 3. summary_generator_agent ► state["dataset_summary"]  (DatasetSummary)
          Computes counts by source type, measure, outcome; validation pass rate;
          edge-case inventory.  This summary is consumed by the Comparison step.
```

### Architecture Decision: `output_schema` vs. Tools

ADK raises a validation error if both `output_schema` **and** `tools` are set on the
same `LlmAgent` (Gemini's JSON-controlled-generation mode is incompatible with
parallel function-calling).

**Resolution:** the full corpus (HEDIS specs, IVR codes, disposition codes, care-gap
definitions) is pre-loaded at module import time via `tools.build_corpus_context()` and
injected directly into each agent's `instruction` string.  The `retrieve_reference`
`FunctionTool` still exists in `tools.py` and can be attached to any future
non-schema agent.

**Swap seam** — to move to live Vertex AI RAG:
1. Open `tools.py` and replace the body of `retrieve_reference_raw()` with a
   `VertexAiRagRetrieval` SDK call (see the comment block in that function).
2. Either (a) keep pre-loading but call the live RAG at startup, or (b) remove
   `output_schema` from the schema-constrained agents and attach the RAG tool directly.
3. No other files need to change.

---

## Project Structure

```
Hackathon-Project/
├── main.py                          # headless runner — prints all 3 state outputs
├── rag_data_generation/
│   ├── __init__.py                  # exposes root_agent (ADK convention)
│   ├── agent.py                     # 3 LlmAgents + SequentialAgent root_agent
│   ├── schemas.py                   # Pydantic models (output_schema targets)
│   ├── tools.py                     # retrieve_reference FunctionTool + corpus loader
│   ├── requirements.txt
│   ├── .env.example
│   └── corpus/
│       ├── hedis_measures.json      # 10 HEDIS measure specs
│       ├── ivr_codes.json           # IVR / SMS / Mail result code dictionary
│       ├── disposition_codes.json   # 15 canonical normalised disposition codes
│       └── care_gap_definitions.json# Closure rules, ID formats, edge-case guide
└── data/                            # existing hackathon data (reference only)
```

---

## Setup

### 1. Install dependencies

```bash
# From the project root
pip install -r rag_data_generation/requirements.txt
```

Or install `google-adk` globally if you already have it:

```bash
pip install google-adk pydantic python-dotenv
```

### 2. Configure environment

```bash
cp rag_data_generation/.env.example .env
# Edit .env and add your GOOGLE_API_KEY
```

**Google AI Studio (easiest):**
```
GOOGLE_API_KEY=AIza...
GOOGLE_GENAI_USE_VERTEXAI=FALSE
```

**Vertex AI:**
```
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=my-project
GOOGLE_CLOUD_LOCATION=us-central1
```
Then run `gcloud auth application-default login`.

---

## Running

### Option A — `adk web` (interactive UI)

```bash
# From the project root (where rag_data_generation/ directory lives)
adk web
```

Open `http://localhost:8000`, select the **rag_data_generation** agent, and send
any message to trigger the pipeline.  All three state keys are visible in the
"State" panel.

### Option B — `adk run` (single headless run)

```bash
adk run rag_data_generation
```

### Option C — `python main.py` (headless with printed output)

```bash
python main.py
```

Prints `generated_data`, `validated_data`, and `dataset_summary` to stdout.
Override batch size:

```bash
BATCH_SIZE=5 python main.py
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_API_KEY` | — | Required for Google AI Studio |
| `GOOGLE_GENAI_USE_VERTEXAI` | `FALSE` | Set `TRUE` for Vertex AI |
| `GOOGLE_CLOUD_PROJECT` | — | GCP project (Vertex AI only) |
| `GOOGLE_CLOUD_LOCATION` | — | GCP region (Vertex AI only) |
| `BATCH_SIZE` | `10` | Number of synthetic records to generate |

---

## Output Schemas

| State Key | Schema | Description |
|---|---|---|
| `generated_data` | `GeneratedDataset` | Raw synthetic records + ground-truth labels |
| `validated_data` | `ValidatedDataset` | QA-reviewed records with validation status |
| `dataset_summary` | `DatasetSummary` | Aggregate stats for the Comparison step |

### `DispositionRecord` fields

| Field | Type | Notes |
|---|---|---|
| `record_id` | str | REC-XXXXXX |
| `source_type` | enum | call_transcript / ivr_result_code / csr_note / web_form |
| `raw_payload` | str | Verbatim synthetic input |
| `member_id` | str | MBR00001–MBR00200 |
| `provider_id` | str\|null | PRV0001–PRV0050 |
| `care_gap_id` | str | AWC/CBP/CDC-H/COA/COL/FUH/MRP/OMW/SPC/TRC |
| `hedis_measure` | str | Same as care_gap_id |
| `responded` | bool | True if member was reached |
| `response_summary` | str | Plain-language outcome |
| `action_taken` | str | Canonical action from disposition_codes corpus |
| `care_gap_status` | enum | closed/attempted_not_closed/open_no_contact/invalid |
| `disposition_code` | str | DISP-CLOSED/DISP-SCHED/DISP-COMP-UV/… |
| `confidence` | float 0–1 | Extraction confidence |
| `validation_status` | enum | valid/corrected/rejected (set by SME agent) |
| `validation_notes` | str | SME QA notes |
