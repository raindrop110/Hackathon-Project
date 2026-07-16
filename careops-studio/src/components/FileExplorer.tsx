import {
  ChevronDown,
  ChevronRight,
  FileSpreadsheet,
  FileText,
  Folder,
  FolderOpen,
  Loader2,
  Search,
  FoldVertical,
  UnfoldVertical,
} from "lucide-react";
import { useMemo, type ReactNode } from "react";
import { useFileStore } from "../store/fileStore";
import type { FileNode, FolderNode, TreeNode } from "../types";

function FileIcon({ node }: { node: FileNode }) {
  if (node.status === "uploading" || node.status === "processing") {
    return <Loader2 size={14} className="spin" />;
  }
  if (node.fileKind === "csv") return <FileSpreadsheet size={14} />;
  return <FileText size={14} />;
}

function matchesQuery(node: TreeNode, query: string, nodes: TreeNode[]): boolean {
  if (!query.trim()) return true;
  const q = query.toLowerCase();
  if (node.name.toLowerCase().includes(q)) return true;
  if (node.kind === "folder") {
    return nodes.some(
      (child) => child.parentId === node.id && matchesQuery(child, query, nodes),
    );
  }
  return false;
}

export function FileExplorer() {
  const nodes = useFileStore((s) => s.nodes);
  const selectedId = useFileStore((s) => s.selectedId);
  const query = useFileStore((s) => s.query);
  const select = useFileStore((s) => s.select);
  const setQuery = useFileStore((s) => s.setQuery);
  const toggleFolder = useFileStore((s) => s.toggleFolder);
  const collapseAll = useFileStore((s) => s.collapseAll);
  const expandAll = useFileStore((s) => s.expandAll);

  const fileCount = nodes.filter((n) => n.kind === "file").length;

  const roots = useMemo(
    () => nodes.filter((n) => n.parentId === null),
    [nodes],
  );

  const childrenOf = (parentId: string) =>
    nodes.filter((n) => n.parentId === parentId);

  const renderNode = (node: TreeNode, depth: number) => {
    if (!matchesQuery(node, query, nodes)) return null;

    if (node.kind === "folder") {
      return (
        <FolderRow
          key={node.id}
          node={node}
          depth={depth}
          selected={selectedId === node.id}
          onSelect={() => select(node.id)}
          onToggle={() => toggleFolder(node.id)}
        >
          {!node.collapsed &&
            childrenOf(node.id).map((child) => renderNode(child, depth + 1))}
        </FolderRow>
      );
    }

    return (
      <FileRow
        key={node.id}
        node={node}
        depth={depth}
        selected={selectedId === node.id}
        onSelect={() => select(node.id)}
      />
    );
  };

  return (
    <aside className="explorer">
      <div className="explorer__header">
        <div className="explorer__title-row">
          <span className="explorer__title">Datasets</span>
          <span className="explorer__count">{fileCount}</span>
        </div>
        <div className="explorer__actions">
          <button type="button" className="icon-btn" onClick={collapseAll} title="Collapse all">
            <FoldVertical size={14} />
          </button>
          <button type="button" className="icon-btn" onClick={expandAll} title="Expand all">
            <UnfoldVertical size={14} />
          </button>
        </div>
      </div>

      <div className="explorer__search">
        <Search size={13} className="explorer__search-icon" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter files…"
          aria-label="Filter datasets"
        />
      </div>

      <div className="explorer__tree" role="tree">
        {roots.map((root) => renderNode(root, 0))}
      </div>

      <div className="explorer__footer">Drop files on the right to add</div>
    </aside>
  );
}

function FolderRow({
  node,
  depth,
  selected,
  onSelect,
  onToggle,
  children,
}: {
  node: FolderNode;
  depth: number;
  selected: boolean;
  onSelect: () => void;
  onToggle: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="tree-folder">
      <button
        type="button"
        role="treeitem"
        aria-expanded={!node.collapsed}
        className={`tree-row ${selected ? "tree-row--selected" : ""}`}
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={onSelect}
        onDoubleClick={onToggle}
      >
        <span
          className="tree-row__chevron"
          onClick={(e) => {
            e.stopPropagation();
            onToggle();
          }}
        >
          {node.collapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
        </span>
        <span className="tree-row__icon">
          {node.collapsed ? <Folder size={14} /> : <FolderOpen size={14} />}
        </span>
        <span className="tree-row__name">{node.name}</span>
      </button>
      {children}
    </div>
  );
}

function FileRow({
  node,
  depth,
  selected,
  onSelect,
}: {
  node: FileNode;
  depth: number;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="treeitem"
      className={`tree-row tree-row--file ${selected ? "tree-row--selected" : ""} status-${node.status}`}
      style={{ paddingLeft: 8 + depth * 14 + 16 }}
      onClick={onSelect}
    >
      <span className="tree-row__icon">
        <FileIcon node={node} />
      </span>
      <span className="tree-row__name" title={node.path}>
        {node.name}
      </span>
      {node.status === "new" && <span className="badge badge--new">new</span>}
      {node.status === "error" && <span className="badge badge--error">err</span>}
      {node.meta && node.status !== "new" && (
        <span className="tree-row__meta">{node.meta}</span>
      )}
    </button>
  );
}
