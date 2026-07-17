import { create } from "zustand";
import { createInitialStages } from "../data/seed";
import { agentWorkflowClient } from "../lib/agentWorkflowClient";
import { createId } from "../lib/files";
import type {
  AgentStatus,
  CareGapResult,
  DispositionResult,
  FileNode,
  RunResult,
  SummaryAgentResult,
  WorkflowEvent,
  WorkflowRun,
} from "../types";
import { useFileStore } from "./fileStore";

interface WorkflowStore {
  agentStatus: AgentStatus;
  activeRun: WorkflowRun | null;
  runs: WorkflowRun[];
  unsubscribe: (() => void) | null;
  startForFiles: (files: FileNode[], rawFiles: File[]) => Promise<void>;
  applyEvent: (event: WorkflowEvent) => void;
  applyCareGapEdit: (field: string, value: string) => void;
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

    const pushLog = (line: string) => [...activeRun.logs, `[${new Date().toLocaleTimeString()}] ${line}`];

    if (event.type === "stage_start") {
      set({
        activeRun: {
          ...activeRun,
          activeStageId: event.stageId,
          logs: pushLog(event.message ?? `${event.stageId} started`),
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
          logs: pushLog(event.message ?? `${event.stageId} in progress`),
          stages: activeRun.stages.map((s) =>
            s.id === event.stageId ? { ...s, message: event.message, status: "active" } : s,
          ),
        },
      });
      return;
    }

    if (event.type === "stage_complete") {
      const updatedResults = { ...activeRun.agentResults };
      if (event.result !== undefined) {
        if (event.stageId === "summarization") {
          updatedResults.summarization = event.result as SummaryAgentResult;
        } else if (event.stageId === "schema_normalization") {
          updatedResults.schema_normalization = event.result as DispositionResult;
        } else if (event.stageId === "care_gap_connection") {
          updatedResults.care_gap_connection = event.result as CareGapResult;
        }
      }

      set({
        activeRun: {
          ...activeRun,
          agentResults: updatedResults,
          logs: pushLog(event.message ?? `${event.stageId} complete`),
          stages: activeRun.stages.map((s) =>
            s.id === event.stageId ? { ...s, status: "completed", message: event.message } : s,
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
          logs: pushLog(`Error in ${event.stageId}: ${event.error}`),
          stages: activeRun.stages.map((s) =>
            s.id === event.stageId ? { ...s, status: "error", message: event.error } : s,
          ),
        },
      });
      activeRun.fileIds.forEach((id) => useFileStore.getState().setFileStatus(id, "error"));
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
          finalResult: event.result as RunResult | undefined,
          completedAt: new Date().toISOString(),
          logs: pushLog("Workflow complete — all agents finished"),
          stages: activeRun.stages.map((s) => ({ ...s, status: "completed" })),
        },
      });
      activeRun.fileIds.forEach((id) => useFileStore.getState().setFileStatus(id, "new"));
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
          logs: pushLog(`Run failed: ${event.error}`),
        },
      });
      activeRun.fileIds.forEach((id) => useFileStore.getState().setFileStatus(id, "error"));
    }
  },

  applyCareGapEdit: (field, value) => {
    const { activeRun } = get();
    const careGap = activeRun?.agentResults.care_gap_connection;
    if (!activeRun || !careGap?.changes?.[field]) return;

    const updatedCareGap: CareGapResult = {
      ...careGap,
      changes: {
        ...careGap.changes,
        [field]: { ...careGap.changes[field], to: value },
      },
    };

    set({
      activeRun: {
        ...activeRun,
        agentResults: { ...activeRun.agentResults, care_gap_connection: updatedCareGap },
        finalResult: activeRun.finalResult
          ? { ...activeRun.finalResult, careGap: updatedCareGap }
          : activeRun.finalResult,
        manualEdits: activeRun.manualEdits?.includes(field)
          ? activeRun.manualEdits
          : [...(activeRun.manualEdits ?? []), field],
        logs: [
          ...activeRun.logs,
          `[${new Date().toLocaleTimeString()}] Manually corrected ${field} → ${value}`,
        ],
      },
    });
  },

  startForFiles: async (files, rawFiles) => {
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
      logs: [`[${new Date().toLocaleTimeString()}] Queued ${files.length} file(s) for processing`],
      agentResults: {},
    };

    set({ activeRun: run, agentStatus: "running", runs: [run, ...get().runs] });
    files.forEach((f) => useFileStore.getState().setFileStatus(f.id, "processing"));

    await agentWorkflowClient.start({
      runId,
      files: files.map((f, i) => ({
        id: f.id,
        name: f.name,
        path: f.path,
        mimeType: f.fileKind === "csv" ? "text/csv" : "text/plain",
        rawFile: rawFiles[i],
      })),
    });

    const unsub = agentWorkflowClient.subscribe(runId, (event) => {
      get().applyEvent(event);
    });

    set({ unsubscribe: unsub });
  },
}));
