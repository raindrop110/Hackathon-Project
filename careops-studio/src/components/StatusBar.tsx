import { useFileStore } from "../store/fileStore";
import { useWorkflowStore } from "../store/workflowStore";

export function StatusBar() {
  const fileCount = useFileStore((s) => s.nodes.filter((n) => n.kind === "file").length);
  const folderCount = useFileStore((s) => s.nodes.filter((n) => n.kind === "folder").length);
  const selectedId = useFileStore((s) => s.selectedId);
  const nodes = useFileStore((s) => s.nodes);
  const activeRun = useWorkflowStore((s) => s.activeRun);

  const selected = nodes.find((n) => n.id === selectedId);
  const stage =
    activeRun?.stages.find((s) => s.id === activeRun.activeStageId)?.label ??
    (activeRun?.status === "complete" ? "Ready" : "—");

  return (
    <footer className="status-bar">
      <div className="status-bar__left">
        <span>
          {fileCount} files · {folderCount} folders
        </span>
        {selected && (
          <span className="status-bar__path" title={selected.path}>
            {selected.path}
          </span>
        )}
      </div>
      <div className="status-bar__center">
        {activeRun ? (
          <span>
            Run {activeRun.id.slice(0, 12)} · {stage}
          </span>
        ) : (
          <span>No active workflow</span>
        )}
      </div>
      <div className="status-bar__right">
        <span>Humana Hackathon</span>
        <span className="status-bar__env">local</span>
      </div>
    </footer>
  );
}
