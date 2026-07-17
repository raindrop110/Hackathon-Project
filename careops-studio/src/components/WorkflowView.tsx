import { AlertCircle, Check, Circle, Loader2, RotateCcw } from "lucide-react";
import { useWorkflowStore } from "../store/workflowStore";
import { FinalResultCard } from "./FinalResultCard";
import type {
  CareGapResult,
  DispositionResult,
  SummaryAgentResult,
  WorkflowStage,
} from "../types";

const STAGE_AGENT_LABELS: Record<string, string> = {
  ingest: "Ingesting file",
  summarization: "Summarization Agent",
  schema_normalization: "Schema Normalization Agent",
  care_gap_connection: "Care Gap Connection Agent",
  complete: "Complete",
};

// ── Main view ────────────────────────────────────────────────────────────────

export function WorkflowView() {
  const activeRun = useWorkflowStore((s) => s.activeRun);
  const resetToIdle = useWorkflowStore((s) => s.resetToIdle);

  if (!activeRun) return null;

  const started = new Date(activeRun.startedAt).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  const { summarization, schema_normalization, care_gap_connection } = activeRun.agentResults;

  return (
    <div className="workflow">
      <header className="workflow__header">
        <div>
          <p className="workflow__eyebrow">Agentic workflow</p>
          <h2 className="workflow__title">Run · {activeRun.fileNames.join(", ")}</h2>
          <p className="workflow__meta">
            Started {started} · Status{" "}
            <strong className={`text-status text-status--${activeRun.status}`}>
              {activeRun.status.charAt(0).toUpperCase() + activeRun.status.slice(1)}
            </strong>
          </p>
        </div>
        <button type="button" className="btn-ghost" onClick={resetToIdle}>
          <RotateCcw size={14} />
          New upload
        </button>
      </header>

      <StageRail stages={activeRun.stages} />

      {activeRun.status === "complete" && <FinalResultCard run={activeRun} />}

      {activeRun.status === "running" && activeRun.activeStageId && (
        <div className="active-agent-banner">
          <Loader2 size={13} className="spin" />
          <span className="active-agent-banner__name">
            {STAGE_AGENT_LABELS[activeRun.activeStageId] ?? activeRun.activeStageId}
          </span>
          <span className="active-agent-banner__suffix">is processing…</span>
        </div>
      )}

      <section className="workflow__logs" aria-label="Run output">
        <div className="workflow__logs-header">Output</div>
        <pre className="workflow__logs-body">
          {activeRun.logs.map((line, i) => (
            <div className="workflow__logs-line" key={`${i}-${line.slice(0, 24)}`}>
              {line}
            </div>
          ))}
        </pre>
      </section>

      {summarization && <SummarizationPanel data={summarization} />}
      {schema_normalization && <DispositionPanel data={schema_normalization} />}
      {care_gap_connection && <CareGapPanel data={care_gap_connection} />}
    </div>
  );
}

// ── Stage rail ───────────────────────────────────────────────────────────────

function StageRail({ stages }: { stages: WorkflowStage[] }) {
  return (
    <ol className="stage-rail" aria-label="Workflow stages">
      {stages.map((stage, index) => (
        <li key={stage.id} className={`stage-rail__item stage-rail__item--${stage.status}`}>
          {index > 0 && <span className="stage-rail__connector" aria-hidden />}
          <span className="stage-rail__dot" aria-hidden>
            <StageIcon status={stage.status} />
          </span>
          <span className="stage-rail__label">{stage.label}</span>
        </li>
      ))}
    </ol>
  );
}

function StageIcon({ status }: { status: WorkflowStage["status"] }) {
  if (status === "completed") return <Check size={12} strokeWidth={3} />;
  if (status === "active") return <Loader2 size={12} className="spin" />;
  if (status === "error") return <AlertCircle size={12} />;
  return <Circle size={10} />;
}

// ── Summarization panel ──────────────────────────────────────────────────────

function SummarizationPanel({ data }: { data: SummaryAgentResult }) {
  const chips = [
    { label: "Member", value: data.member_id },
    { label: "Gap", value: data.gap_id },
    { label: "Measure", value: data.measure_name ?? data.measure_id },
    { label: "Channel", value: data.channel ?? data.interaction_type },
    { label: "Date", value: data.interaction_date },
    { label: "Provider", value: data.provider_name },
  ].filter((c) => c.value);

  return (
    <section className="result-panel result-panel--summary">
      <div className="result-panel__header">
        <span className="result-panel__eyebrow">Summarization Agent</span>
        {data.confidence && (
          <span className={`confidence-badge confidence-badge--${data.confidence}`}>
            {data.confidence} confidence
          </span>
        )}
      </div>

      {chips.length > 0 && (
        <div className="result-chips">
          {chips.map((c) => (
            <span key={c.label} className="result-chip">
              <span className="result-chip__label">{c.label}</span>
              <span className="result-chip__value">{String(c.value)}</span>
            </span>
          ))}
        </div>
      )}

      {data.key_findings && data.key_findings.length > 0 && (
        <div className="result-panel__section">
          <p className="result-panel__section-title">Key Findings</p>
          <ul className="result-findings">
            {data.key_findings.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
        </div>
      )}

      {data.evidence && data.evidence.length > 0 && (
        <div className="result-panel__section">
          <p className="result-panel__section-title">Evidence</p>
          {data.evidence.map((e, i) => (
            <blockquote key={i} className="result-evidence">{e}</blockquote>
          ))}
        </div>
      )}
    </section>
  );
}

// ── Disposition panel ────────────────────────────────────────────────────────

function DispositionPanel({ data }: { data: DispositionResult }) {
  const entries = Object.entries(data).filter(([, v]) => v !== null && v !== "" && v !== undefined);

  return (
    <section className="result-panel result-panel--disposition">
      <div className="result-panel__header">
        <span className="result-panel__eyebrow">Schema Normalization Agent</span>
        <span className="result-panel__badge">campaign_disposition</span>
      </div>
      <table className="result-table">
        <tbody>
          {entries.map(([key, value]) => (
            <tr key={key}>
              <td className="result-table__key">{key}</td>
              <td className="result-table__value">{String(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

// ── Care gap panel ───────────────────────────────────────────────────────────

function CareGapPanel({ data }: { data: CareGapResult }) {
  const hasChanges = data.success && data.changes && Object.keys(data.changes).length > 0;

  return (
    <section className="result-panel result-panel--caregap">
      <div className="result-panel__header">
        <span className="result-panel__eyebrow">Care Gap Connection Agent</span>
        <span className={`result-panel__badge result-panel__badge--${data.success ? "success" : "warn"}`}>
          {data.success ? "updated" : "retry required"}
        </span>
      </div>

      {data.gap_id && (
        <p className="result-panel__gap-id">
          Gap ID: <strong>{data.gap_id}</strong>
        </p>
      )}

      {hasChanges && data.changes && (
        <table className="diff-table">
          <thead>
            <tr>
              <th>Field</th>
              <th>Before</th>
              <th>After</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.changes).map(([field, { from, to }]) => (
              <tr key={field}>
                <td className="diff-table__field">{field}</td>
                <td className="diff-table__from">{from || "—"}</td>
                <td className="diff-table__to">{to}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!data.success && data.reason && (
        <p className="result-panel__retry-note">{data.reason}</p>
      )}
    </section>
  );
}
