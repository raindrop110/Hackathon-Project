import type { TreeNode, WorkflowStage } from "../types";

export const WORKFLOW_STAGE_DEFS: Omit<WorkflowStage, "status" | "message">[] = [
  {
    id: "ingest",
    label: "Ingest",
    description: "Accept file into the workspace and register metadata.",
  },
  {
    id: "validate",
    label: "Validate",
    description: "Check schema, encoding, and required columns.",
  },
  {
    id: "profile",
    label: "Profile",
    description: "Summarize rows, keys, and data quality signals.",
  },
  {
    id: "workflow",
    label: "Agent workflow",
    description: "Run the teammate agentic pipeline (open for integration).",
  },
  {
    id: "complete",
    label: "Ready",
    description: "File is available in the explorer for downstream use.",
  },
];

export function createInitialStages(): WorkflowStage[] {
  return WORKFLOW_STAGE_DEFS.map((s, i) => ({
    ...s,
    status: i === 0 ? "active" : "pending",
  }));
}

export const SEED_TREE: TreeNode[] = [
  {
    id: "folder-structured",
    name: "structured",
    path: "data/structured",
    kind: "folder",
    parentId: null,
    collapsed: false,
  },
  {
    id: "folder-unstructured",
    name: "unstructured",
    path: "data/unstructured",
    kind: "folder",
    parentId: null,
    collapsed: false,
  },
  {
    id: "folder-transcripts",
    name: "call_transcripts",
    path: "data/unstructured/call_transcripts",
    kind: "folder",
    parentId: "folder-unstructured",
    collapsed: true,
  },
  {
    id: "folder-uploads",
    name: "uploads",
    path: "data/uploads",
    kind: "folder",
    parentId: null,
    collapsed: false,
  },
  // structured files
  file("claims.csv", "folder-structured", "data/structured/claims.csv", "csv", "880 rows"),
  file("care_gaps.csv", "folder-structured", "data/structured/care_gaps.csv", "csv", "552 rows"),
  file("members.csv", "folder-structured", "data/structured/members.csv", "csv", "200 rows"),
  file("providers.csv", "folder-structured", "data/structured/providers.csv", "csv", "50 rows"),
  file("campaign_dispositions.csv", "folder-structured", "data/structured/campaign_dispositions.csv", "csv", "568 rows"),
  file("compliance_flags.csv", "folder-structured", "data/structured/compliance_flags.csv", "csv", "312 rows"),
  file("roi_authorizations.csv", "folder-structured", "data/structured/roi_authorizations.csv", "csv", "352 rows"),
  file("appointment_slots.csv", "folder-structured", "data/structured/appointment_slots.csv", "csv", "178 rows"),
  file("coverage_rules.csv", "folder-structured", "data/structured/coverage_rules.csv", "csv", "80 rows"),
  file("segment_performance.csv", "folder-structured", "data/structured/segment_performance.csv", "csv", "169 rows"),
  file("historical_interventions.csv", "folder-structured", "data/structured/historical_interventions.csv", "csv", "27 rows"),
  file("stars_performance.csv", "folder-structured", "data/structured/stars_performance.csv", "csv", "10 rows"),
  // unstructured
  file(
    "stars_performance_report.md",
    "folder-unstructured",
    "data/unstructured/stars_performance_report.md",
    "md",
    "report",
  ),
  file("transcript_01_denied_claim_inquiry.txt", "folder-transcripts", "data/unstructured/call_transcripts/transcript_01_denied_claim_inquiry.txt", "txt"),
  file("transcript_02_prior_auth_question.txt", "folder-transcripts", "data/unstructured/call_transcripts/transcript_02_prior_auth_question.txt", "txt"),
  file("transcript_03_care_gap_outreach.txt", "folder-transcripts", "data/unstructured/call_transcripts/transcript_03_care_gap_outreach.txt", "txt"),
  file("transcript_04_roi_missing.txt", "folder-transcripts", "data/unstructured/call_transcripts/transcript_04_roi_missing.txt", "txt"),
  file("transcript_05_benefits_question.txt", "folder-transcripts", "data/unstructured/call_transcripts/transcript_05_benefits_question.txt", "txt"),
  file("transcript_06_claim_status_check.txt", "folder-transcripts", "data/unstructured/call_transcripts/transcript_06_claim_status_check.txt", "txt"),
  file("transcript_07_denied_claim_inquiry.txt", "folder-transcripts", "data/unstructured/call_transcripts/transcript_07_denied_claim_inquiry.txt", "txt"),
  file("transcript_08_prior_auth_question.txt", "folder-transcripts", "data/unstructured/call_transcripts/transcript_08_prior_auth_question.txt", "txt"),
  file("transcript_09_care_gap_outreach.txt", "folder-transcripts", "data/unstructured/call_transcripts/transcript_09_care_gap_outreach.txt", "txt"),
  file("transcript_10_roi_missing.txt", "folder-transcripts", "data/unstructured/call_transcripts/transcript_10_roi_missing.txt", "txt"),
  file("transcript_11_benefits_question.txt", "folder-transcripts", "data/unstructured/call_transcripts/transcript_11_benefits_question.txt", "txt"),
  file("transcript_12_claim_status_check.txt", "folder-transcripts", "data/unstructured/call_transcripts/transcript_12_claim_status_check.txt", "txt"),
];

function file(
  name: string,
  parentId: string,
  path: string,
  fileKind: "csv" | "txt" | "md",
  meta?: string,
): TreeNode {
  return {
    id: `file-${path}`,
    name,
    path,
    kind: "file",
    fileKind,
    meta,
    status: "ready",
    parentId,
  };
}
