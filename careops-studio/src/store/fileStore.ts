import { create } from "zustand";
import { SEED_TREE } from "../data/seed";
import { createId, extToFileKind, formatBytes } from "../lib/files";
import type { FileNode, FolderNode, TreeNode } from "../types";

interface FileStore {
  nodes: TreeNode[];
  selectedId: string | null;
  query: string;
  select: (id: string | null) => void;
  setQuery: (q: string) => void;
  toggleFolder: (id: string) => void;
  collapseAll: () => void;
  expandAll: () => void;
  addUploadedFiles: (files: File[]) => FileNode[];
  setFileStatus: (id: string, status: FileNode["status"]) => void;
  clearNewBadges: () => void;
  fileCount: () => number;
  folderCount: () => number;
}

export const useFileStore = create<FileStore>((set, get) => ({
  nodes: SEED_TREE,
  selectedId: null,
  query: "",

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

    return created;
  },

  setFileStatus: (id, status) =>
    set((state) => ({
      nodes: state.nodes.map((n) =>
        n.kind === "file" && n.id === id ? { ...n, status } : n,
      ),
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
