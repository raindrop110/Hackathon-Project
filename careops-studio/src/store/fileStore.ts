import { create } from "zustand";
import { SEED_TREE } from "../data/seed";
import { createId, extToFileKind, formatBytes } from "../lib/files";
import type { FileNode, FolderNode, TreeNode } from "../types";

interface FileStore {
  nodes: TreeNode[];
  selectedId: string | null;
  query: string;
  /** In-browser text content for uploaded files, keyed by node id (uploads have no disk path to read back). */
  uploadedContent: Record<string, string>;
  select: (id: string | null) => void;
  setQuery: (q: string) => void;
  toggleFolder: (id: string) => void;
  collapseAll: () => void;
  expandAll: () => void;
  addUploadedFiles: (files: File[]) => FileNode[];
  addGeneratedBatch: (batchId: string, recordCount: number) => FileNode;
  setFileStatus: (id: string, status: FileNode["status"]) => void;
  setUploadedContent: (id: string, content: string) => void;
  clearNewBadges: () => void;
  fileCount: () => number;
  folderCount: () => number;
}

export const useFileStore = create<FileStore>((set, get) => ({
  nodes: SEED_TREE,
  selectedId: null,
  query: "",
  uploadedContent: {},

  select: (id) => set({ selectedId: id }),

  setQuery: (query) => set({ query }),

  toggleFolder: (id) =>
    set((state) => ({
      nodes: state.nodes.map((n) =>
        n.kind === "folder" && n.id === id ? { ...n, collapsed: !n.collapsed } : n,
      ),
    })),

  collapseAll: () =>
    set((state) => ({
      nodes: state.nodes.map((n) =>
        n.kind === "folder" ? { ...n, collapsed: true } : n,
      ),
    })),

  expandAll: () =>
    set((state) => ({
      nodes: state.nodes.map((n) =>
        n.kind === "folder" ? { ...n, collapsed: false } : n,
      ),
    })),

  addUploadedFiles: (files) => {
    const uploadsFolder = get().nodes.find(
      (n) => n.kind === "folder" && n.id === "folder-uploads",
    ) as FolderNode | undefined;

    const created: FileNode[] = files.map((file) => {
      const id = createId("upload");
      return {
        id,
        name: file.name,
        path: `data/uploads/${file.name}`,
        kind: "file" as const,
        fileKind: extToFileKind(file.name),
        meta: formatBytes(file.size),
        status: "uploading" as const,
        parentId: uploadsFolder?.id ?? "folder-uploads",
        sizeBytes: file.size,
        uploadedAt: new Date().toISOString(),
      };
    });

    set((state) => ({
      nodes: [
        ...state.nodes.map((n) =>
          n.kind === "folder" && n.id === "folder-uploads"
            ? { ...n, collapsed: false }
            : n,
        ),
        ...created,
      ],
      selectedId: created[0]?.id ?? state.selectedId,
    }));

    created.forEach((node, i) => {
      const rawFile = files[i];
      if (node.fileKind !== "csv" && node.fileKind !== "txt" && node.fileKind !== "md") return;
      rawFile
        .text()
        .then((text) => get().setUploadedContent(node.id, text))
        .catch(() => {});
    });

    return created;
  },

  addGeneratedBatch: (batchId, recordCount) => {
    const id = `generated-${batchId}`;
    const existing = get().nodes.find((n) => n.id === id);
    if (existing) return existing as FileNode;

    const node: FileNode = {
      id,
      name: `${batchId}.json`,
      path: `generated/${batchId}.json`,
      kind: "file",
      fileKind: "json",
      meta: `${recordCount} record${recordCount === 1 ? "" : "s"}`,
      status: "new",
      parentId: "folder-generated",
    };

    set((state) => ({
      nodes: [
        ...state.nodes.map((n) =>
          n.kind === "folder" && n.id === "folder-generated" ? { ...n, collapsed: false } : n,
        ),
        node,
      ],
    }));

    return node;
  },

  setFileStatus: (id, status) =>
    set((state) => ({
      nodes: state.nodes.map((n) =>
        n.kind === "file" && n.id === id ? { ...n, status } : n,
      ),
    })),

  setUploadedContent: (id, content) =>
    set((state) => ({
      uploadedContent: { ...state.uploadedContent, [id]: content },
    })),

  clearNewBadges: () =>
    set((state) => ({
      nodes: state.nodes.map((n) =>
        n.kind === "file" && n.status === "new" ? { ...n, status: "ready" } : n,
      ),
    })),

  fileCount: () => get().nodes.filter((n) => n.kind === "file").length,
  folderCount: () => get().nodes.filter((n) => n.kind === "folder").length,
}));
