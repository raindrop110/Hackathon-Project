import type { ComparisonResult, WorkflowEvent } from "../types";

const API_BASE = "/api";

export const comparisonClient = {
  async start(): Promise<{ runId: string }> {
    const res = await fetch(`${API_BASE}/comparison/run`, { method: "POST" });
    if (!res.ok) {
      throw new Error(`Failed to start comparison: ${res.status} ${res.statusText}`);
    }
    return res.json() as Promise<{ runId: string }>;
  },

  subscribe(
    runId: string,
    onEvent: (e: WorkflowEvent) => void,
    onResult: (r: ComparisonResult) => void,
  ) {
    const es = new EventSource(`${API_BASE}/comparison/${runId}/stream`);

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as WorkflowEvent;
        if (event.type === "run_complete" && event.result) {
          onResult(event.result as ComparisonResult);
        }
        onEvent(event);
      } catch {
        // ignore malformed frames
      }
    };

    es.onerror = () => {
      onEvent({ type: "run_error", error: "Connection to comparison server lost" });
      es.close();
    };

    return () => es.close();
  },
};
