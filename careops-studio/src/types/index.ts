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

// ── Agent result payloads ───────────────────────────────────────────────────

export interface SummaryAgentResult {
  member_id?: string | null;
  gap_id?: string | null;
  measure_id?: string | null;
  measure_name?: string | null;
  interaction_type?: string | null;
  channel?: string | null;
  disposition_code?: string | null;
  interaction_date?: string | null;
  provider_name?: string | null;
  service_completed?: boolean | null;
  member_refused?: boolean | null;
  successful_contact?: boolean | null;
  follow_up_required?: boolean | null;
  key_findings?: string[];
  entities?: string[];
  evidence?: string[];
  confidence?: "high" | "medium" | "low" | string;
  summary?: string;
  [key: string]: unknown;
}

export type DispositionResult = Record<string, string | boolean | number | null>;

export interface CareGapResult {
  success: boolean;
  gap_id?: string;
  changes?: Record<string, { from: string; to: string }>;
  reason?: string;
  status?: string;
}

export interface RunResult {
  summary?: SummaryAgentResult;
  disposition?: DispositionResult;
  careGap?: CareGapResult;
}

// ── Workflow run ────────────────────────────────────────────────────────────

export interface WorkflowRun {
  id: string;
  fileIds: string[];
  fileNames: string[];
  startedAt: string;
  status: AgentStatus;
  stages: WorkflowStage[];
  activeStageId: string | null;
  logs: string[];
  agentResults: Partial<{
    summarization: SummaryAgentResult;
    schema_normalization: DispositionResult;
    care_gap_connection: CareGapResult;
  }>;
  finalResult?: RunResult;
}

// ── Events ──────────────────────────────────────────────────────────────────

export type WorkflowEvent =
  | { type: "stage_start"; stageId: string; message?: string }
  | { type: "stage_progress"; stageId: string; message?: string; pct?: number }
  | { type: "stage_complete"; stageId: string; message?: string; result?: unknown }
  | { type: "stage_error"; stageId: string; error: string }
  | { type: "run_complete"; result?: RunResult }
  | { type: "run_error"; error: string };

// ── Comparison types ────────────────────────────────────────────────────────

export interface FieldAccuracy {
  field_name: string;
  correct: number;
  total: number;
  accuracy_pct: number;
}

export interface RecordMismatch {
  record_id: string;
  source_type: string;
  hedis_measure: string;
  field: string;
  ground_truth: string;
  normalized: string;
  normalization_confidence: string;
}

export interface ComparisonResult {
  batch_id: string;
  total_records: number;
  records_fully_correct: number;
  record_accuracy_pct: number;
  field_accuracy: FieldAccuracy[];
  accuracy_by_source_type: {
    call_transcript: number;
    ivr_result_code: number;
    csr_note: number;
    web_form: number;
  };
  high_confidence_record_accuracy_pct: number;
  low_confidence_record_accuracy_pct: number;
  total_field_mismatches: number;
  mismatches: RecordMismatch[];
  summary: string;
}

// ── Client ──────────────────────────────────────────────────────────────────

export type WorkflowStartPayload = {
  runId: string;
  files: { id: string; name: string; path: string; mimeType: string; rawFile: File }[];
};

export interface AgentWorkflowClient {
  start(payload: WorkflowStartPayload): Promise<{ runId: string }>;
  subscribe(runId: string, onEvent: (e: WorkflowEvent) => void): () => void;
}
