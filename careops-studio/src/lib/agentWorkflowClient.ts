import type {
  AgentWorkflowClient,
  WorkflowEvent,
  WorkflowStartPayload,
} from "../types";
import { WORKFLOW_STAGE_DEFS } from "../data/seed";

/**
 * Mock agent workflow client.
 * Swap this implementation for the real ADK / teammate pipeline later.
 */
export function createMockAgentWorkflowClient(): AgentWorkflowClient {
  const timers = new Map<string, ReturnType<typeof setTimeout>[]>();

  return {
    async start(payload: WorkflowStartPayload) {
      return { runId: payload.runId };
    },

    subscribe(runId: string, onEvent: (e: WorkflowEvent) => void) {
      const stageIds = WORKFLOW_STAGE_DEFS.map((s) => s.id);
      const runTimers: ReturnType<typeof setTimeout>[] = [];
      let delay = 400;

      for (const stageId of stageIds) {
        const startDelay = delay;
        runTimers.push(
          setTimeout(() => {
            onEvent({
              type: "stage_start",
              stageId,
              message: `Starting ${stageId}…`,
            });
          }, startDelay),
        );

        delay += 900 + Math.random() * 600;

        const progressDelay = delay - 400;
        runTimers.push(
          setTimeout(() => {
            onEvent({
              type: "stage_progress",
              stageId,
              message:
                stageId === "workflow"
                  ? "Awaiting teammate agentic workflow integration…"
                  : `Processing ${stageId}`,
              pct: 55,
            });
          }, progressDelay),
        );

        const completeDelay = delay;
        runTimers.push(
          setTimeout(() => {
            onEvent({
              type: "stage_complete",
              stageId,
              message: `${stageId} complete`,
            });
          }, completeDelay),
        );

        delay += 200;
      }

      runTimers.push(
        setTimeout(() => {
          onEvent({ type: "run_complete" });
        }, delay + 100),
      );

      timers.set(runId, runTimers);

      return () => {
        const list = timers.get(runId) ?? [];
        list.forEach(clearTimeout);
        timers.delete(runId);
      };
    },
  };
}

/** Singleton used by the app until a real client is wired. */
export const agentWorkflowClient = createMockAgentWorkflowClient();
