const API_BASE = "/api";

async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    return body?.detail ?? fallback;
  } catch {
    return fallback;
  }
}

export async function fetchFileContent(path: string): Promise<string> {
  const res = await fetch(`${API_BASE}/files/content?path=${encodeURIComponent(path)}`);
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `Failed to load file: ${res.status}`));
  }
  const data = (await res.json()) as { content: string };
  return data.content;
}

export async function saveFileContent(path: string, content: string): Promise<void> {
  const res = await fetch(`${API_BASE}/files/content`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `Failed to save file: ${res.status}`));
  }
}

/** Read-only — workflow 2's generated batches live in memory on the server, not
 * on disk, so this is fetched and pretty-printed rather than saved back. */
export async function fetchGeneratedBatch(batchId: string): Promise<string> {
  const res = await fetch(`${API_BASE}/generated-batches/${encodeURIComponent(batchId)}`);
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `Failed to load batch: ${res.status}`));
  }
  const data = await res.json();
  return JSON.stringify(data, null, 2);
}
