import { Activity, Settings } from "lucide-react";
import { useWorkflowStore } from "../store/workflowStore";

export function TitleBar() {
  const agentStatus = useWorkflowStore((s) => s.agentStatus);

  const statusLabel =
    agentStatus === "idle"
      ? "Idle"
      : agentStatus === "running"
        ? "Running"
        : agentStatus === "complete"
          ? "Complete"
          : "Error";

  return (
    <header className="title-bar">
      <div className="title-bar__brand">
        <span className="title-bar__mark" aria-hidden>
          H
        </span>
        <div className="title-bar__names">
          <span className="title-bar__product">CareOps Studio</span>
          <span className="title-bar__project">hackathon-data</span>
        </div>
      </div>

      <div className="title-bar__center" aria-hidden>
        <span className="title-bar__path">humana · medicare advantage · synthetic</span>
      </div>

      <div className="title-bar__actions">
        <span className={`agent-pill agent-pill--${agentStatus}`}>
          <Activity size={12} strokeWidth={2.5} />
          Agent: {statusLabel}
        </span>
        <button type="button" className="icon-btn" aria-label="Settings" title="Settings">
          <Settings size={15} />
        </button>
      </div>
    </header>
  );
}
