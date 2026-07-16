# CareOps Studio — Disposition Normalization

Hackathon project for Humana Medicare Advantage. Transforms raw healthcare call transcripts into structured care gap updates using a multi-agent GADK pipeline.

---

## Quick start

```bash
git clone <repo-url> && cd Hackathon-Project
cp .env.example .env        # add your GOOGLE_API_KEY
make install                # install all Python + Node deps
make dev                    # launch backend :8000 + frontend :5173
```

Open http://localhost:5173 — drop a transcript in, watch the pipeline run.

---

## What it does

1. **Upload** a call transcript (`.txt`) or report (`.md`) via the web UI
2. **Summarization Agent** extracts member ID, gap ID, measure, disposition, key findings
3. **Schema Normalization Agent** maps the summary to the `campaign_dispositions` schema using RAG over structured CSVs
4. **Care Gap Connection Agent** finds the matching row in `care_gaps.csv`, updates it, and returns a before/after diff
5. Results stream back to the frontend in real time via SSE

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| Google ADK | `pip install google-adk` |
| Gemini API key | [ai.google.dev](https://ai.google.dev/gemini-api/docs/api-key) |

---

## Project structure

```
Hackathon-Project/
├── data/
│   ├── structured/          # 12 reference CSVs (care_gaps, claims, members, etc.)
│   └── unstructured/        # call transcripts + reports
├── disposition_normalization/
│   ├── __init__.py
│   ├── server.py            # FastAPI backend — SSE + file upload
│   ├── requirements.txt
│   ├── orchestrator_agent/  # Root GADK agent — coordinates all three sub-agents
│   ├── summarization_agent/ # Reads raw file, extracts structured JSON summary
│   ├── data_schema_agent/   # RAG over CSVs → maps summary to campaign_disposition schema
│   └── data_connection_agent/ # Looks up + updates care_gaps.csv
└── careops-studio/          # React + Vite frontend
```

---

## Setup

### 1. Clone and enter the repo

```bash
git clone <repo-url>
cd Hackathon-Project
```

### 2. Set your API key

```bash
cp .env.example .env          # or create .env manually
# Edit .env and set:
# GOOGLE_API_KEY=your_key_here
```

> Get a key at https://ai.google.dev/gemini-api/docs/api-key

### 3. Install Python dependencies

```bash
pip install -r disposition_normalization/requirements.txt
```

### 4. Install frontend dependencies

```bash
cd careops-studio
npm install
cd ..
```

---

## Running — Option A: GADK web UI (agent testing only)

Use this to test and chat with any individual agent directly via the GADK browser UI.

```bash
# From Hackathon-Project/
adk web
```

Open http://localhost:8000. You can select any agent:
- `disposition_normalization/orchestrator_agent` — full pipeline
- `disposition_normalization/summarization_agent` — summarize a transcript
- `disposition_normalization/data_schema_agent` — normalize a JSON file
- `disposition_normalization/data_connection_agent` — look up and update a care gap

To run a specific agent directly in the terminal:

```bash
adk run disposition_normalization/orchestrator_agent
```

---

## Running — Option B: Full stack (frontend + backend)

```bash
make dev
```

Starts both servers in one command. Ctrl+C kills both cleanly.

- Backend: http://localhost:8000
- Frontend: http://localhost:5173

Drop a `.txt` transcript from `data/unstructured/call_transcripts/` into the upload zone to trigger the full pipeline.

---

## Testing the pipeline

Sample input files are in `data/unstructured/call_transcripts/`. Good ones to start with:

| File | Scenario |
|---|---|
| `transcript_03_care_gap_outreach.txt` | Outbound care gap call — member claims completion |
| `transcript_01_denied_claim_inquiry.txt` | Denied claim — CO-109 coordination of benefits |
| `transcript_09_care_gap_outreach.txt` | Another care gap outreach scenario |

There is also a pre-built test JSON in `disposition_normalization/test_json/2nd_input.json` that can be fed directly to the `data_connection_agent`.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | Gemini API key for all GADK agents |

---

## Agent pipeline (GADK)

```
orchestrator_agent  (LlmAgent)
├── AgentTool → summarization_agent     reads raw file → structured JSON
├── AgentTool → data_schema_agent       JSON → campaign_disposition row (RAG)
├── AgentTool → data_connection_agent   disposition → care_gap lookup + CSV update
└── Tool      → save_intermediate       writes temp files between stages
```

The server calls the orchestrator via a single GADK `Runner`. Sub-agent events are intercepted by `event.author` to drive the per-stage SSE stream to the frontend.
