# CareOps Studio

Humana-themed IDE shell for the hackathon dataset workspace.

## Features

- **Left panel** (light green): file explorer seeded with hackathon datasets
- **Right panel** (white): drag-and-drop upload zone
- **On upload**: file appears under `uploads/` and a mock agentic workflow run starts
- **Workflow stages**: Ingest → Validate → Profile → Agent workflow → Ready  
  The `agent workflow` stage is a placeholder for your teammates’ ADK pipeline

## Run

```bash
cd Hackathon-Project/careops-studio
npm install
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173).

## Integrating the real agent

Replace the mock in `src/lib/agentWorkflowClient.ts` with your ADK / AG-UI client.  
The UI only depends on:

```ts
interface AgentWorkflowClient {
  start(payload: WorkflowStartPayload): Promise<{ runId: string }>;
  subscribe(runId: string, onEvent: (e: WorkflowEvent) => void): () => void;
}
```

See `src/types/index.ts` for event shapes.
