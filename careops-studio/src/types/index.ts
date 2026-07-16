export type FileKind = "csv" | "txt" | "md" | "zip" | "other";

export type FileStatus = "ready" | "uploading" | "processing" | "error" | "new";

export interface FileNode {
  id: string;
  name: string;
  path: string;
  kind: "file";
  fileKind: FileKind;
  meta?: string;
  status: FileStatus;
  parentId: string | null;
  sizeBytes?: number;
  uploadedAt?: string;
}

export interface FolderNode {
  id: string;
  name: string;
  path: string;
  kind: "folder";
  parentId: string | null;
  collapsed?: boolean;
}

export type TreeNode = FileNode | FolderNode;

export type StageStatus = "pending" | "active" | "completed" | "error";

export interface WorkflowStage {
  id: string;
  label: string;
  description: string;
  status: StageStatus;
  message?: string;
}

export type AgentStatus = "idle" | "running" | "error" | "complete";

export interface WorkflowRun {
  id: string;
  fileIds: string[];
  fileNames: string[];
  startedAt: string;
  status: AgentStatus;
  stages: WorkflowStage[];
  activeStageId: string | null;
  logs: string[];
}

export type WorkflowStartPayload = {
  runId: string;
  files: { id: string; name: string; path: string; mimeType: string }[];
};

export type WorkflowEvent =
  | { type: "stage_start"; stageId: string; message?: string }
  | { type: "stage_progress"; stageId: string; message?: string; pct?: number }
  | { type: "stage_complete"; stageId: string; message?: string }
  | { type: "stage_error"; stageId: string; error: string }
  | { type: "run_complete" }
  | { type: "run_error"; error: string };

export interface AgentWorkflowClient {
  start(payload: WorkflowStartPayload): Promise<{ runId: string }>;
  subscribe(runId: string, onEvent: (e: WorkflowEvent) => void): () => void;
}
