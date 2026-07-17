import type { AgentWorkflowClient, WorkflowEvent, WorkflowStartPayload } from "../types";

const API_BASE = "/api";

function createRealAgentWorkflowClient(): AgentWorkflowClient {
  return {
    async start(payload: WorkflowStartPayload) {
      const formData = new FormData();
      formData.append("runId", payload.runId);
      // Send the first file (workflow processes one file at a time)
      const first = payload.files[0];
      if (first?.rawFile) {
        formData.append("file", first.rawFile, first.name);
      }

      const res = await fetch(`${API_BASE}/workflow/start`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error(`Failed to start workflow: ${res.status} ${res.statusText}`);
      }

      return res.json() as Promise<{ runId: string }>;
    },

    subscribe(runId: string, onEvent: (e: WorkflowEvent) => void) {
      const es = new EventSource(`${API_BASE}/workflow/${runId}/stream`);

      es.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data) as WorkflowEvent;
          onEvent(event);
        } catch {
          // ignore malformed frames
        }
      };

      es.onerror = () => {
        onEvent({ type: "run_error", error: "Connection to server lost" });
        es.close();
      };

      return () => es.close();
    },
  };
}

export const agentWorkflowClient = createRealAgentWorkflowClient();

export async function updateCareGapField(
  gapId: string,
  field: string,
  value: string,
): Promise<{ success: boolean; error?: string }> {
  try {
    const res = await fetch(`${API_BASE}/care-gap/${encodeURIComponent(gapId)}/field`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ field, value }),
    });
    const body = await res.json();
    if (!res.ok || body.success === false) {
      return { success: false, error: body.error ?? `${res.status} ${res.statusText}` };
    }
    return { success: true };
  } catch {
    return { success: false, error: "Network error" };
  }
}
