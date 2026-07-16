import { useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { useWorkflowStore } from "../store/workflowStore";
import { ComparisonView } from "./ComparisonView";
import { DropZone } from "./DropZone";
import { FileExplorer } from "./FileExplorer";
import { StatusBar } from "./StatusBar";
import { TitleBar } from "./TitleBar";
import { WorkflowView } from "./WorkflowView";

type Tab = "workflow" | "comparison";

export function IdeShell() {
  const activeRun = useWorkflowStore((s) => s.activeRun);
  const [tab, setTab] = useState<Tab>("workflow");

  return (
    <div className="ide">
      <TitleBar />
      <div className="ide__body">
        <Group orientation="horizontal" className="ide__panels">
          <Panel
            id="explorer"
            defaultSize="28%"
            minSize="16%"
            maxSize="45%"
            className="ide__left"
          >
            <FileExplorer />
          </Panel>
          <Separator className="resize-handle" />
          <Panel id="workbench" defaultSize="72%" minSize="40%" className="ide__right">
            <div className="workbench-shell">
              <div className="tab-bar" role="tablist">
                <button
                  role="tab"
                  aria-selected={tab === "workflow"}
                  className={`tab ${tab === "workflow" ? "tab--active" : ""}`}
                  onClick={() => setTab("workflow")}
                >
                  Workflow
                </button>
                <button
                  role="tab"
                  aria-selected={tab === "comparison"}
                  className={`tab ${tab === "comparison" ? "tab--active" : ""}`}
                  onClick={() => setTab("comparison")}
                >
                  Comparison
                </button>
              </div>
              <main className="workbench">
                {tab === "workflow"
                  ? activeRun ? <WorkflowView /> : <DropZone />
                  : <ComparisonView />}
              </main>
            </div>
          </Panel>
        </Group>
      </div>
      <StatusBar />
    </div>
  );
}
