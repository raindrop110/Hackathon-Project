# CareOps Studio — Disposition Normalization

Hackathon project for Humana Medicare Advantage. Transforms raw healthcare call transcripts into structured care gap updates using a multi-agent GADK pipeline.

---

## Quick start

```bash
git clone <repo-url> && cd Hackathon-Project
cp .env.example .env        # fill in your GCP project ID
gcloud auth application-default login   # authenticate via ADC
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
| Google Cloud SDK | `gcloud` CLI — for ADC auth |
| GCP project | Vertex AI API enabled |

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

### 2. Authenticate with Vertex AI (Application Default Credentials)

GADK uses Vertex AI when `GOOGLE_GENAI_USE_VERTEXAI=1` is set. Auth is handled via ADC — no API key needed.

```bash
# One-time login (writes creds to ~/.config/gcloud/)
gcloud auth application-default login

# Then copy and edit the env file
cp .env.example .env
```

Edit `.env` and replace `your-gcp-project-id` with your actual GCP project:

```
GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_PROJECT=my-humana-project
GOOGLE_CLOUD_LOCATION=us-central1
```

Make sure the **Vertex AI API** is enabled in that project:
```bash
gcloud services enable aiplatform.googleapis.com --project=my-humana-project
```

> If running inside a GCP environment (Cloud Run, Vertex AI Workbench, etc.) ADC is available automatically — no `gcloud auth` needed.

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
| `GOOGLE_GENAI_USE_VERTEXAI` | Yes | Set to `1` to route all GADK calls through Vertex AI |
| `GOOGLE_CLOUD_PROJECT` | Yes | GCP project ID with Vertex AI API enabled |
| `GOOGLE_CLOUD_LOCATION` | Yes | Region for Vertex AI (e.g. `us-central1`) |

Authentication uses **Application Default Credentials** — run `gcloud auth application-default login` once before starting the servers.

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
