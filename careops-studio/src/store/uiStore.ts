import { create } from "zustand";

export type WorkbenchTabId = "workflow" | "comparison" | `file:${string}`;

interface UiStore {
  activeTab: WorkbenchTabId;
  openFileIds: string[];
  setActiveTab: (tab: WorkbenchTabId) => void;
  openFile: (fileId: string) => void;
  openFileInBackground: (fileId: string) => void;
  closeFile: (fileId: string) => void;
}

export const useUiStore = create<UiStore>((set) => ({
  activeTab: "workflow",
  openFileIds: [],

  setActiveTab: (tab) => set({ activeTab: tab }),

  openFile: (fileId) =>
    set((state) => ({
      openFileIds: state.openFileIds.includes(fileId)
        ? state.openFileIds
        : [...state.openFileIds, fileId],
      activeTab: `file:${fileId}`,
    })),

  /** Adds a tab without switching focus to it — e.g. workflow 2 finishing a
   * generated-data batch shouldn't yank the user away from whatever they're
   * currently looking at. */
  openFileInBackground: (fileId) =>
    set((state) => ({
      openFileIds: state.openFileIds.includes(fileId)
        ? state.openFileIds
        : [...state.openFileIds, fileId],
    })),

  closeFile: (fileId) =>
    set((state) => {
      const openFileIds = state.openFileIds.filter((id) => id !== fileId);
      if (state.activeTab !== `file:${fileId}`) return { openFileIds };
      const fallback: WorkbenchTabId = openFileIds.length
        ? `file:${openFileIds[openFileIds.length - 1]}`
        : "workflow";
      return { openFileIds, activeTab: fallback };
    }),
}));
