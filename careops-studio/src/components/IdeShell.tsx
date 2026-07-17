import { useRef } from "react";
import { X } from "lucide-react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { useFileStore } from "../store/fileStore";
import { useUiStore, type WorkbenchTabId } from "../store/uiStore";
import { useWorkflowStore } from "../store/workflowStore";
import { ComparisonView } from "./ComparisonView";
import { DropZone } from "./DropZone";
import { FileEditorView } from "./FileEditorView";
import { FileExplorer } from "./FileExplorer";
import { StatusBar } from "./StatusBar";
import { TitleBar } from "./TitleBar";
import { WorkflowView } from "./WorkflowView";

/** Stable, colon-free DOM ids for tab/tabpanel ARIA wiring. */
const domId = (tab: WorkbenchTabId) => tab.replace(":", "-");
const tabElId = (tab: WorkbenchTabId) => `tab-${domId(tab)}`;
const panelElId = (tab: WorkbenchTabId) => `panel-${domId(tab)}`;

export function IdeShell() {
  const activeRun = useWorkflowStore((s) => s.activeRun);
  const nodes = useFileStore((s) => s.nodes);
  const activeTab = useUiStore((s) => s.activeTab);
  const setActiveTab = useUiStore((s) => s.setActiveTab);
  const openFileIds = useUiStore((s) => s.openFileIds);
  const closeFile = useUiStore((s) => s.closeFile);
  const tablistRef = useRef<HTMLDivElement>(null);

  const visibleFileIds = openFileIds.filter((id) => nodes.some((n) => n.id === id));
  const tabOrder: WorkbenchTabId[] = [
    "workflow",
    "comparison",
    ...visibleFileIds.map((id) => `file:${id}` as WorkbenchTabId),
  ];

  const focusTab = (tab: WorkbenchTabId) => {
    tablistRef.current
      ?.querySelector<HTMLButtonElement>(`[data-tab-id="${domId(tab)}"]`)
      ?.focus();
  };

  const handleTabKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    const current = tabOrder.indexOf(activeTab);
    const count = tabOrder.length;
    let nextIndex = current;
    if (event.key === "ArrowLeft") nextIndex = (current - 1 + count) % count;
    else if (event.key === "ArrowRight") nextIndex = (current + 1) % count;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = count - 1;
    const nextTab = tabOrder[nextIndex];
    if (!nextTab) return;
    setActiveTab(nextTab);
    focusTab(nextTab);
  };

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
              <div
                className="tab-bar"
                role="tablist"
                aria-label="Workbench views"
                ref={tablistRef}
                onKeyDown={handleTabKeyDown}
              >
                <button
                  type="button"
                  role="tab"
                  id={tabElId("workflow")}
                  data-tab-id={domId("workflow")}
                  aria-selected={activeTab === "workflow"}
                  aria-controls={panelElId("workflow")}
                  tabIndex={activeTab === "workflow" ? 0 : -1}
                  className={`tab ${activeTab === "workflow" ? "tab--active" : ""}`}
                  onClick={() => setActiveTab("workflow")}
                >
                  Workflow
                </button>
                <button
                  type="button"
                  role="tab"
                  id={tabElId("comparison")}
                  data-tab-id={domId("comparison")}
                  aria-selected={activeTab === "comparison"}
                  aria-controls={panelElId("comparison")}
                  tabIndex={activeTab === "comparison" ? 0 : -1}
                  className={`tab ${activeTab === "comparison" ? "tab--active" : ""}`}
                  onClick={() => setActiveTab("comparison")}
                >
                  Comparison
                </button>
                {visibleFileIds.map((fileId) => {
                  const node = nodes.find((n) => n.id === fileId);
                  if (!node) return null;
                  const tabId = `file:${fileId}` as const;
                  const isActive = activeTab === tabId;
                  return (
                    <button
                      key={fileId}
                      type="button"
                      role="tab"
                      id={tabElId(tabId)}
                      data-tab-id={domId(tabId)}
                      aria-selected={isActive}
                      aria-controls={panelElId(tabId)}
                      tabIndex={isActive ? 0 : -1}
                      className={`tab tab--file ${isActive ? "tab--active" : ""}`}
                      onClick={() => setActiveTab(tabId)}
                    >
                      <span className="tab__label" title={node.path}>
                        {node.name}
                      </span>
                      <span
                        className="tab__close"
                        role="button"
                        tabIndex={-1}
                        aria-label={`Close ${node.name}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          closeFile(fileId);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            e.stopPropagation();
                            closeFile(fileId);
                          }
                        }}
                      >
                        <X size={12} />
                      </span>
                    </button>
                  );
                })}
              </div>
              <main className="workbench">
                <div
                  role="tabpanel"
                  id={panelElId("workflow")}
                  aria-labelledby={tabElId("workflow")}
                  hidden={activeTab !== "workflow"}
                  className={`workbench__pane ${activeTab === "workflow" ? "" : "workbench__pane--hidden"}`}
                >
                  {activeRun ? <WorkflowView /> : <DropZone />}
                </div>
                <div
                  role="tabpanel"
                  id={panelElId("comparison")}
                  aria-labelledby={tabElId("comparison")}
                  hidden={activeTab !== "comparison"}
                  className={`workbench__pane ${activeTab === "comparison" ? "" : "workbench__pane--hidden"}`}
                >
                  <ComparisonView />
                </div>
                {visibleFileIds.map((fileId) => {
                  const tabId = `file:${fileId}` as const;
                  return (
                    <div
                      key={fileId}
                      role="tabpanel"
                      id={panelElId(tabId)}
                      aria-labelledby={tabElId(tabId)}
                      hidden={activeTab !== tabId}
                      className={`workbench__pane ${activeTab === tabId ? "" : "workbench__pane--hidden"}`}
                    >
                      <FileEditorView fileId={fileId} />
                    </div>
                  );
                })}
              </main>
            </div>
          </Panel>
        </Group>
      </div>
      <StatusBar />
    </div>
  );
}
