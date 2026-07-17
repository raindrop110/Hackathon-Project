import { AlertCircle, Loader2, Lock, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchFileContent, fetchGeneratedBatch, saveFileContent } from "../lib/filesClient";
import { useFileStore } from "../store/fileStore";

const EDITABLE_KINDS = new Set(["csv", "txt", "md", "json"]);

export function FileEditorView({ fileId }: { fileId: string }) {
  const node = useFileStore((s) => s.nodes.find((n) => n.id === fileId));
  const isUpload = fileId.startsWith("upload-");
  const isGenerated = fileId.startsWith("generated-");
  const uploadedContent = useFileStore((s) => s.uploadedContent[fileId]);
  const setUploadedContent = useFileStore((s) => s.setUploadedContent);

  const editable = node?.kind === "file" && EDITABLE_KINDS.has(node.fileKind);

  const [content, setContent] = useState<string | null>(null);
  const [savedContent, setSavedContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(!isUpload);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!node || node.kind !== "file" || !editable) {
      setLoading(false);
      return;
    }

    if (isUpload) {
      if (uploadedContent !== undefined) {
        setContent(uploadedContent);
        setSavedContent(uploadedContent);
        setLoading(false);
      }
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    const batchId = isGenerated ? node.id.slice("generated-".length) : null;
    const load = batchId ? fetchGeneratedBatch(batchId) : fetchFileContent(node.path);

    load
      .then((text) => {
        if (cancelled) return;
        setContent(text);
        setSavedContent(text);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load file");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId, isUpload, isGenerated, uploadedContent]);

  if (!node || node.kind !== "file") return null;

  const dirty = !isGenerated && content !== null && content !== savedContent;

  async function handleSave() {
    if (content === null || node?.kind !== "file" || isGenerated) return;
    setSaving(true);
    setError(null);
    try {
      if (isUpload) {
        setUploadedContent(node.id, content);
      } else {
        await saveFileContent(node.path, content);
      }
      setSavedContent(content);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save file");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="file-editor">
      <div className="file-editor__toolbar">
        <span className="file-editor__path" title={node.path}>
          {node.path}
          {dirty && <span className="file-editor__dirty-dot" aria-label="Unsaved changes" />}
        </span>
        {isGenerated && (
          <span className="file-editor__readonly-badge">
            <Lock size={12} /> Read-only — generated data
          </span>
        )}
        {editable && !isGenerated && (
          <button
            type="button"
            className="btn-ghost file-editor__save"
            onClick={handleSave}
            disabled={!dirty || saving || loading}
          >
            {saving ? <Loader2 size={13} className="spin" /> : <Save size={13} />}
            {isUpload ? "Save locally" : "Save"}
          </button>
        )}
      </div>

      {loading && (
        <div className="file-editor__status">
          <Loader2 size={16} className="spin" /> Loading…
        </div>
      )}

      {!loading && error && (
        <div className="file-editor__status file-editor__status--error">
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {!loading && !error && !editable && (
        <div className="file-editor__status">Preview not available for this file type.</div>
      )}

      {!loading && !error && editable && content !== null && (
        <textarea
          className="file-editor__textarea"
          value={content}
          onChange={(e) => !isGenerated && setContent(e.target.value)}
          readOnly={isGenerated}
          spellCheck={false}
        />
      )}
    </div>
  );
}
