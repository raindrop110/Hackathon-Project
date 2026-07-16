import { FileUp, Upload } from "lucide-react";
import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { ACCEPTED_UPLOAD_TYPES, isAcceptedFile } from "../lib/files";
import { useFileStore } from "../store/fileStore";
import { useWorkflowStore } from "../store/workflowStore";

export function DropZone() {
  const addUploadedFiles = useFileStore((s) => s.addUploadedFiles);
  const startForFiles = useWorkflowStore((s) => s.startForFiles);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback(
    async (accepted: File[], rejected: { file: File }[]) => {
      setError(null);
      const valid = accepted.filter(isAcceptedFile);
      if (rejected.length || accepted.length !== valid.length) {
        setError("Only CSV, TXT, MD, and ZIP files are accepted.");
      }
      if (!valid.length) return;

      const nodes = addUploadedFiles(valid);
      await startForFiles(nodes);
    },
    [addUploadedFiles, startForFiles],
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    noClick: true,
    multiple: true,
    accept: ACCEPTED_UPLOAD_TYPES,
  });

  return (
    <div className="drop-zone-wrap">
      <div
        {...getRootProps()}
        className={`drop-zone ${isDragActive ? "drop-zone--active" : ""}`}
      >
        <input {...getInputProps()} />
        <div className="drop-zone__icon" aria-hidden>
          {isDragActive ? <Upload size={36} /> : <FileUp size={36} />}
        </div>
        <h2 className="drop-zone__title">
          {isDragActive ? "Release to upload" : "Drop datasets here"}
        </h2>
        <p className="drop-zone__hint">
          CSV, TXT, MD, ZIP · files appear in the left explorer and start the agent workflow
        </p>
        <button type="button" className="btn-primary" onClick={open}>
          Browse files
        </button>
        {error && <p className="drop-zone__error">{error}</p>}
      </div>

      <p className="drop-zone__formats">
        Accepted formats: <code>.csv</code> <code>.txt</code> <code>.md</code>{" "}
        <code>.zip</code>
      </p>
    </div>
  );
}
