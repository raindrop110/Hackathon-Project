import { create } from "zustand";
import { createInitialStages } from "../data/seed";
import { agentWorkflowClient } from "../lib/agentWorkflowClient";
import { createId } from "../lib/files";
import type { AgentStatus, FileNode, WorkflowEvent, WorkflowRun } from "../types";
import { useFileStore } from "./fileStore";

interface WorkflowStore {
  agentStatus: AgentStatus;
  activeRun: WorkflowRun | null;
  runs: WorkflowRun[];
  unsubscribe: (() => void) | null;
  startForFiles: (files: FileNode[]) => Promise<void>;
  applyEvent: (event: WorkflowEvent) => void;
  resetToIdle: () => void;
}

export const useWorkflowStore = create<WorkflowStore>((set, get) => ({
  agentStatus: "idle",
  activeRun: null,
  runs: [],
  unsubscribe: null,

  resetToIdle: () => {
    get().unsubscribe?.();
    set({ agentStatus: "idle", activeRun: null, unsubscribe: null });
  },

  applyEvent: (event) => {
    const { activeRun } = get();
    if (!activeRun) return;

    const pushLog = (line: string) => [...activeRun.logs, line];

    if (event.type === "stage_start") {
      set({
        activeRun: {
          ...activeRun,
          activeStageId: event.stageId,
          logs: pushLog(event.message ?? `Stage ${event.stageId} started`),
          stages: activeRun.stages.map((s) =>
            s.id === event.stageId
              ? { ...s, status: "active", message: event.message }
              : s.status === "active"
                ? { ...s, status: "completed" }
                : s,
          ),
        },
        agentStatus: "running",
      });
      return;
    }

    if (event.type === "stage_progress") {
      set({
        activeRun: {
          ...activeRun,
          logs: pushLog(
            event.message ??
              `Progress ${event.stageId}${event.pct != null ? ` (${event.pct}%)` : ""}`,
          ),
          stages: activeRun.stages.map((s) =>
            s.id === event.stageId
              ? { ...s, message: event.message, status: "active" }
              : s,
          ),
        },
      });
      return;
    }

    if (event.type === "stage_complete") {
      set({
        activeRun: {
          ...activeRun,
          logs: pushLog(event.message ?? `Stage ${event.stageId} complete`),
          stages: activeRun.stages.map((s) =>
            s.id === event.stageId
              ? { ...s, status: "completed", message: event.message }
              : s,
          ),
        },
      });
      return;
    }

    if (event.type === "stage_error") {
      set({
        agentStatus: "error",
        activeRun: {
          ...activeRun,
          status: "error",
          logs: pushLog(`Error: ${event.error}`),
          stages: activeRun.stages.map((s) =>
            s.id === event.stageId
              ? { ...s, status: "error", message: event.error }
              : s,
          ),
        },
      });
      activeRun.fileIds.forEach((id) =>
        useFileStore.getState().setFileStatus(id, "error"),
      );
      return;
    }

    if (event.type === "run_complete") {
      get().unsubscribe?.();
      set({
        agentStatus: "complete",
        unsubscribe: null,
        activeRun: {
          ...activeRun,
          status: "complete",
          activeStageId: "complete",
          logs: pushLog("Run complete — files ready in workspace"),
          stages: activeRun.stages.map((s) => ({
            ...s,
            status: "completed",
          })),
        },
      });
      activeRun.fileIds.forEach((id) =>
        useFileStore.getState().setFileStatus(id, "new"),
      );
      return;
    }

    if (event.type === "run_error") {
      get().unsubscribe?.();
      set({
        agentStatus: "error",
        unsubscribe: null,
        activeRun: {
          ...activeRun,
          status: "error",
          logs: pushLog(`Run error: ${event.error}`),
        },
      });
      activeRun.fileIds.forEach((id) =>
        useFileStore.getState().setFileStatus(id, "error"),
      );
    }
  },

  startForFiles: async (files) => {
    get().unsubscribe?.();

    const runId = createId("run");
    const run: WorkflowRun = {
      id: runId,
      fileIds: files.map((f) => f.id),
      fileNames: files.map((f) => f.name),
      startedAt: new Date().toISOString(),
      status: "running",
      stages: createInitialStages(),
      activeStageId: "ingest",
      logs: [`Queued ${files.length} file(s) for ingest`],
    };

    set({
      activeRun: run,
      agentStatus: "running",
      runs: [run, ...get().runs],
    });

    files.forEach((f) =>
      useFileStore.getState().setFileStatus(f.id, "processing"),
    );

    // Simulate brief upload, then hand off to agent client
    await new Promise((r) => setTimeout(r, 350));
    files.forEach((f) =>
      useFileStore.getState().setFileStatus(f.id, "processing"),
    );

    await agentWorkflowClient.start({
      runId,
      files: files.map((f) => ({
        id: f.id,
        name: f.name,
        path: f.path,
        mimeType: f.fileKind === "csv" ? "text/csv" : "application/octet-stream",
      })),
    });

    const unsub = agentWorkflowClient.subscribe(runId, (event) => {
      get().applyEvent(event);
    });

    set({ unsubscribe: unsub });
  },
}));
