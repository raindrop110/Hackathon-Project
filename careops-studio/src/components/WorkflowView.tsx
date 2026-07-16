import { AlertCircle, Check, Circle, Loader2, RotateCcw } from "lucide-react";
import { useWorkflowStore } from "../store/workflowStore";
import type { WorkflowStage } from "../types";

export function WorkflowView() {
  const activeRun = useWorkflowStore((s) => s.activeRun);
  const resetToIdle = useWorkflowStore((s) => s.resetToIdle);

  if (!activeRun) return null;

  const activeStage =
    activeRun.stages.find((s) => s.id === activeRun.activeStageId) ??
    activeRun.stages.find((s) => s.status === "active") ??
    activeRun.stages[activeRun.stages.length - 1];

  const started = new Date(activeRun.startedAt).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <div className="workflow">
      <header className="workflow__header">
        <div>
          <p className="workflow__eyebrow">Agentic workflow</p>
          <h2 className="workflow__title">
            Run · {activeRun.fileNames.join(", ")}
          </h2>
          <p className="workflow__meta">
            Started {started} · Status{" "}
            <strong className={`text-status text-status--${activeRun.status}`}>
              {activeRun.status}
            </strong>
          </p>
        </div>
        <button type="button" className="btn-ghost" onClick={resetToIdle}>
          <RotateCcw size={14} />
          New upload
        </button>
      </header>

      <StageRail stages={activeRun.stages} />

      <section className="workflow__detail">
        <h3>{activeStage?.label ?? "Workflow"}</h3>
        <p>{activeStage?.description}</p>
        {activeStage?.message && (
          <p className="workflow__stage-msg">{activeStage.message}</p>
        )}
        {activeRun.status === "running" && activeStage?.id === "workflow" && (
          <p className="workflow__integration-note">
            Stage reserved for your teammates&apos; agentic pipeline — wire{" "}
            <code>agentWorkflowClient</code> when ready.
          </p>
        )}
      </section>

      <section className="workflow__logs" aria-label="Run output">
        <div className="workflow__logs-header">Output</div>
        <pre className="workflow__logs-body">
          {activeRun.logs.map((line, i) => (
            <div key={`${i}-${line}`}>{line}</div>
          ))}
        </pre>
      </section>
    </div>
  );
}

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
