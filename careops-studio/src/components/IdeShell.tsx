import { Group, Panel, Separator } from "react-resizable-panels";
import { useWorkflowStore } from "../store/workflowStore";
import { DropZone } from "./DropZone";
import { FileExplorer } from "./FileExplorer";
import { StatusBar } from "./StatusBar";
import { TitleBar } from "./TitleBar";
import { WorkflowView } from "./WorkflowView";

export function IdeShell() {
  const activeRun = useWorkflowStore((s) => s.activeRun);

  return (
    <div className="ide">
      <TitleBar />
      <div className="ide__body">
        <Group orientation="horizontal" className="ide__panels">
          <Panel defaultSize={28} minSize={18} maxSize={42} className="ide__left">
            <FileExplorer />
          </Panel>
          <Separator className="resize-handle" />
          <Panel defaultSize={72} minSize={40} className="ide__right">
            <main className="workbench">
              {activeRun ? <WorkflowView /> : <DropZone />}
            </main>
          </Panel>
        </Group>
      </div>
      <StatusBar />
    </div>
  );
}
