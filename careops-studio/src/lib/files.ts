export function extToFileKind(name: string): "csv" | "txt" | "md" | "json" | "zip" | "other" {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "csv") return "csv";
  if (ext === "txt") return "txt";
  if (ext === "md" || ext === "markdown") return "md";
  if (ext === "json") return "json";
  if (ext === "zip") return "zip";
  return "other";
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function createId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export const ACCEPTED_UPLOAD_TYPES: Record<string, string[]> = {
  "text/csv": [".csv"],
  "text/plain": [".txt"],
  "text/markdown": [".md"],
  "application/zip": [".zip"],
  "application/x-zip-compressed": [".zip"],
};

export function isAcceptedFile(file: File): boolean {
  const kind = extToFileKind(file.name);
  return kind !== "other";
}
