import { AlertCircle, Check, Circle, FlaskConical, Loader2, RotateCcw } from "lucide-react";
import { useRef, useState } from "react";
import { comparisonClient } from "../lib/comparisonClient";
import type { ComparisonResult, FieldAccuracy, RecordMismatch, WorkflowStage } from "../types";

// ── Stage definitions ────────────────────────────────────────────────────────

const INITIAL_STAGES: WorkflowStage[] = [
  { id: "cmp_generate", label: "Generate Test Data", description: "Synthetic ground-truth records", status: "pending" },
  { id: "cmp_normalize", label: "Normalize Records", description: "Run normalization pipeline", status: "pending" },
  { id: "cmp_compare", label: "Compare Results", description: "Accuracy vs ground truth", status: "pending" },
  { id: "cmp_complete", label: "Complete", description: "", status: "pending" },
];

type RunStatus = "idle" | "running" | "complete" | "error";

// ── Main view ────────────────────────────────────────────────────────────────

export function ComparisonView() {
  const [status, setStatus] = useState<RunStatus>("idle");
  const [stages, setStages] = useState<WorkflowStage[]>(INITIAL_STAGES);
  const [activeStageId, setActiveStageId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const unsubRef = useRef<(() => void) | null>(null);

  function addLog(msg: string) {
    const ts = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    setLogs((prev) => [...prev, `[${ts}] ${msg}`]);
  }

  function setStageStatus(id: string, s: WorkflowStage["status"]) {
    setStages((prev) => prev.map((st) => (st.id === id ? { ...st, status: s } : st)));
  }

  async function handleRun() {
    setStatus("running");
    setStages(INITIAL_STAGES.map((st) => ({ ...st, status: "pending" })));
    setLogs([]);
    setResult(null);
    setErrorMsg(null);
    addLog("Starting comparison run…");

    let runId: string;
    try {
      const resp = await comparisonClient.start();
      runId = resp.runId;
      addLog(`Run ID: ${runId}`);
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "Failed to start");
      return;
    }

    unsubRef.current = comparisonClient.subscribe(
      runId,
      (event) => {
        if (event.type === "stage_start") {
          setActiveStageId(event.stageId);
          setStageStatus(event.stageId, "active");
          addLog(event.message ?? `Stage started: ${event.stageId}`);
        } else if (event.type === "stage_progress") {
          addLog(event.message ?? `Progress: ${event.stageId}`);
        } else if (event.type === "stage_complete") {
          setStageStatus(event.stageId, "completed");
          addLog(event.message ?? `Stage complete: ${event.stageId}`);
        } else if (event.type === "stage_error") {
          setStageStatus(event.stageId, "error");
          setStatus("error");
          setErrorMsg(event.error);
          addLog(`Error in ${event.stageId}: ${event.error}`);
        } else if (event.type === "run_complete") {
          setActiveStageId(null);
          setStageStatus("cmp_complete", "completed");
          setStatus("complete");
          addLog("Comparison complete.");
        } else if (event.type === "run_error") {
          setStatus("error");
          setErrorMsg(event.error);
          addLog(`Run error: ${event.error}`);
        }
      },
      (r) => setResult(r),
    );
  }

  function handleReset() {
    unsubRef.current?.();
    unsubRef.current = null;
    setStatus("idle");
    setStages(INITIAL_STAGES);
    setActiveStageId(null);
    setLogs([]);
    setResult(null);
    setErrorMsg(null);
  }

  if (status === "idle") {
    return (
      <div className="comparison comparison--idle">
        <div className="comparison__idle-icon">
          <FlaskConical size={36} />
        </div>
        <h2 className="comparison__idle-title">Pipeline Accuracy Test</h2>
        <p className="comparison__idle-hint">
          Generates synthetic records with ground-truth labels, runs them through the
          normalization pipeline, then reports accuracy across all fields and source types.
        </p>
        <button type="button" className="btn-primary" onClick={handleRun}>
          Run Comparison
        </button>
      </div>
    );
  }

  return (
    <div className="comparison">
      <header className="workflow__header">
        <div>
          <p className="workflow__eyebrow">Evaluation pipeline</p>
          <h2 className="workflow__title">Normalization Accuracy Test</h2>
          <p className="workflow__meta">
            Status{" "}
            <strong className={`text-status text-status--${status}`}>
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </strong>
          </p>
        </div>
        {(status === "complete" || status === "error") && (
          <button type="button" className="btn-ghost" onClick={handleReset}>
            <RotateCcw size={14} />
            Run again
          </button>
        )}
      </header>

      <ComparisonStageRail stages={stages} />

      {status === "running" && activeStageId && (
        <div className="active-agent-banner">
          <Loader2 size={13} className="spin" />
          <span className="active-agent-banner__name">
            {stages.find((s) => s.id === activeStageId)?.label ?? activeStageId}
          </span>
          <span className="active-agent-banner__suffix">is processing…</span>
        </div>
      )}

      <section className="workflow__logs" aria-label="Comparison output">
        <div className="workflow__logs-header">Output</div>
        <pre className="workflow__logs-body">
          {logs.map((line, i) => (
            <div key={i}>{line}</div>
          ))}
        </pre>
      </section>

      {status === "error" && errorMsg && (
        <section className="result-panel">
          <div className="result-panel__header">
            <span className="result-panel__eyebrow">Error</span>
            <span className="result-panel__badge result-panel__badge--warn">failed</span>
          </div>
          <p className="result-panel__retry-note">{errorMsg}</p>
        </section>
      )}

      {result && (
        <>
          <AccuracyOverview result={result} />
          <SourceTypePanel result={result} />
          <ConfidencePanel result={result} />
          {result.mismatches.length > 0 && <MismatchPanel mismatches={result.mismatches} />}
        </>
      )}
    </div>
  );
}

// ── Stage rail ───────────────────────────────────────────────────────────────

function ComparisonStageRail({ stages }: { stages: WorkflowStage[] }) {
  return (
    <ol className="stage-rail" aria-label="Comparison stages">
      {stages.map((stage, index) => (
        <li key={stage.id} className={`stage-rail__item stage-rail__item--${stage.status}`}>
          {index > 0 && <span className="stage-rail__connector" aria-hidden />}
          <span className="stage-rail__dot" aria-hidden>
            {stage.status === "completed" && <Check size={12} strokeWidth={3} />}
            {stage.status === "active" && <Loader2 size={12} className="spin" />}
            {stage.status === "error" && <AlertCircle size={12} />}
            {stage.status === "pending" && <Circle size={10} />}
          </span>
          <span className="stage-rail__label">{stage.label}</span>
        </li>
      ))}
    </ol>
  );
}

// ── Accuracy overview panel ──────────────────────────────────────────────────

function AccuracyOverview({ result }: { result: ComparisonResult }) {
  const pct = result.record_accuracy_pct;
  const colorClass = pct >= 80 ? "accuracy-hero--high" : pct >= 60 ? "accuracy-hero--medium" : "accuracy-hero--low";

  return (
    <section className="result-panel result-panel--comparison">
      <div className="result-panel__header">
        <span className="result-panel__eyebrow">Accuracy Overview</span>
        <span className="result-panel__badge result-panel__badge--success">
          Batch {result.batch_id}
        </span>
      </div>

      <div className={`accuracy-hero ${colorClass}`}>
        <span className="accuracy-hero__number">{pct.toFixed(1)}%</span>
        <span className="accuracy-hero__label">
          records fully correct ({result.records_fully_correct}/{result.total_records})
        </span>
      </div>

      <p className="comparison__summary">{result.summary}</p>

      <div className="result-panel__section">
        <p className="result-panel__section-title">Field-Level Accuracy</p>
        <table className="result-table">
          <thead>
            <tr>
              <th className="result-table__key">Field</th>
              <th className="result-table__value">Correct</th>
              <th className="result-table__value">Accuracy</th>
            </tr>
          </thead>
          <tbody>
            {result.field_accuracy.map((f: FieldAccuracy) => (
              <tr key={f.field_name}>
                <td className="result-table__key">{f.field_name}</td>
                <td className="result-table__value">{f.correct}/{f.total}</td>
                <td className="result-table__value">
                  <span className={`accuracy-inline ${f.accuracy_pct >= 80 ? "accuracy-inline--high" : f.accuracy_pct >= 60 ? "accuracy-inline--medium" : "accuracy-inline--low"}`}>
                    {f.accuracy_pct.toFixed(1)}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ── Source type panel ────────────────────────────────────────────────────────

function SourceTypePanel({ result }: { result: ComparisonResult }) {
  const rows = [
    { label: "Call Transcript", value: result.accuracy_by_source_type.call_transcript },
    { label: "IVR Result Code", value: result.accuracy_by_source_type.ivr_result_code },
    { label: "CSR Note", value: result.accuracy_by_source_type.csr_note },
    { label: "Web Form", value: result.accuracy_by_source_type.web_form },
  ];

  return (
    <section className="result-panel">
      <div className="result-panel__header">
        <span className="result-panel__eyebrow">Accuracy by Source Type</span>
      </div>
      <table className="result-table">
        <tbody>
          {rows.map(({ label, value }) => (
            <tr key={label}>
              <td className="result-table__key">{label}</td>
              <td className="result-table__value">
                <span className={`accuracy-inline ${value >= 80 ? "accuracy-inline--high" : value >= 60 ? "accuracy-inline--medium" : "accuracy-inline--low"}`}>
                  {value.toFixed(1)}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

// ── Confidence panel ─────────────────────────────────────────────────────────

function ConfidencePanel({ result }: { result: ComparisonResult }) {
  return (
    <section className="result-panel">
      <div className="result-panel__header">
        <span className="result-panel__eyebrow">Accuracy by Confidence Stratum</span>
      </div>
      <table className="result-table">
        <tbody>
          <tr>
            <td className="result-table__key">High-confidence records</td>
            <td className="result-table__value">
              <span className={`accuracy-inline ${result.high_confidence_record_accuracy_pct >= 80 ? "accuracy-inline--high" : "accuracy-inline--medium"}`}>
                {result.high_confidence_record_accuracy_pct.toFixed(1)}%
              </span>
            </td>
          </tr>
          <tr>
            <td className="result-table__key">Low-confidence records</td>
            <td className="result-table__value">
              <span className={`accuracy-inline ${result.low_confidence_record_accuracy_pct >= 60 ? "accuracy-inline--medium" : "accuracy-inline--low"}`}>
                {result.low_confidence_record_accuracy_pct.toFixed(1)}%
              </span>
            </td>
          </tr>
          <tr>
            <td className="result-table__key">Total field mismatches</td>
            <td className="result-table__value">{result.total_field_mismatches}</td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}

// ── Mismatch panel ───────────────────────────────────────────────────────────

function MismatchPanel({ mismatches }: { mismatches: RecordMismatch[] }) {
  const shown = mismatches.slice(0, 15);
  const overflow = mismatches.length - shown.length;

  return (
    <section className="result-panel">
      <div className="result-panel__header">
        <span className="result-panel__eyebrow">Mismatches</span>
        <span className="result-panel__badge result-panel__badge--warn">
          {mismatches.length} total
        </span>
      </div>
      <table className="diff-table">
        <thead>
          <tr>
            <th>Record</th>
            <th>Source</th>
            <th>Field</th>
            <th>Ground Truth</th>
            <th>Normalized</th>
            <th>Confidence</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((m, i) => (
            <tr key={i}>
              <td className="diff-table__field">{m.record_id}</td>
              <td>{m.source_type.replace("_", " ")}</td>
              <td className="diff-table__field">{m.field}</td>
              <td className="diff-table__from">{m.ground_truth}</td>
              <td className="diff-table__to">{m.normalized}</td>
              <td>
                <span className={`confidence-badge confidence-badge--${m.normalization_confidence}`}>
                  {m.normalization_confidence}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {overflow > 0 && (
        <p className="result-panel__retry-note">…and {overflow} more mismatches not shown.</p>
      )}
    </section>
  );
}
