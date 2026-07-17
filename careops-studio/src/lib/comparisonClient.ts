import type { GenerationQualityReport, WorkflowEvent } from "../types";

const API_BASE = "/api";

/**
 * Workflow 3 fires automatically on the backend the moment a file is uploaded —
 * there's no "start" call. This just subscribes to that upload's run_id to watch
 * pattern-extraction/generation/scoring progress and receive the final heatmap.
 */
export const comparisonClient = {
  subscribe(
    runId: string,
    onEvent: (e: WorkflowEvent) => void,
    onResult: (r: GenerationQualityReport) => void,
  ) {
    const es = new EventSource(`${API_BASE}/generation-quality/${runId}/stream`);
    let done = false;

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as WorkflowEvent;
        if (event.type === "run_complete" && event.result) {
          onResult(event.result as GenerationQualityReport);
        }
        if (event.type === "run_complete" || event.type === "run_error") {
          // The backend closes its end right after this — close ours too so the
          // browser doesn't treat that expected closure as a connection error.
          done = true;
          es.close();
        }
        onEvent(event);
      } catch {
        // ignore malformed frames
      }
    };

    es.onerror = () => {
      if (done) return;
      onEvent({ type: "run_error", error: "Connection to generation-quality stream lost" });
      es.close();
    };

    return () => es.close();
  },
};
