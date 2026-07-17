import { useState } from "react";
import { Pencil } from "lucide-react";
import { updateCareGapField } from "../lib/agentWorkflowClient";
import { useWorkflowStore } from "../store/workflowStore";
import type { WorkflowRun } from "../types";

function formatDuration(startedAt: string, completedAt?: string): string | undefined {
  if (!completedAt) return undefined;
  const seconds = Math.max(
    1,
    Math.round((new Date(completedAt).getTime() - new Date(startedAt).getTime()) / 1000),
  );
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function FinalResultCard({ run }: { run: WorkflowRun }) {
  const result = run.finalResult;
  if (!result) return null;

  const summary = result.summary ?? run.agentResults.summarization;
  const disposition = result.disposition ?? run.agentResults.schema_normalization;
  const careGap = result.careGap ?? run.agentResults.care_gap_connection;

  const success = careGap?.success ?? true;
  const gapId = (careGap?.gap_id ?? disposition?.gap_id) as string | undefined;
  const manualEdits = run.manualEdits ?? [];

  const chips: { label: string; value: string }[] = [
    { label: "Member", value: (summary?.member_id ?? disposition?.member_id) as string },
    { label: "Care Gap", value: (careGap?.gap_id ?? disposition?.gap_id) as string },
    { label: "Measure", value: (summary?.measure_name ?? disposition?.measure_name) as string },
    {
      label: "Disposition",
      value: (disposition?.raw_disposition_code ?? summary?.disposition_code) as string,
    },
    { label: "Action", value: disposition?.action_taken as string },
    { label: "Source", value: run.fileNames.join(", ") },
    { label: "Duration", value: formatDuration(run.startedAt, run.completedAt) as string },
  ].filter((item) => item.value !== undefined && item.value !== null && item.value !== "");

  const changeEntries = careGap?.changes ? Object.entries(careGap.changes) : [];

  return (
    <section className="result-panel result-panel--final">
      <div className="result-panel__header result-panel__header--final">
        <div className="result-final__heading">
          <span className="result-panel__eyebrow">Final Result</span>
          <h3 className="result-final__title">
            {success ? "Care gap journey resolved" : "Care gap needs a second pass"}
          </h3>
          <p className="result-final__run">
            Run <code>{run.id.slice(0, 12)}</code>
          </p>
        </div>
        <span
          className={`result-panel__badge result-panel__badge--${success ? "success" : "warn"}`}
        >
          {success ? "Verified" : "Needs review"}
        </span>
      </div>

      {chips.length > 0 && (
        <div className="result-chips">
          {chips.map((c) => (
            <span key={c.label} className="result-chip">
              <span className="result-chip__label">{c.label}</span>
              <span className="result-chip__value">{c.value}</span>
            </span>
          ))}
        </div>
      )}

      {changeEntries.length > 0 && (
        <div className="result-final__changes">
          <div className="result-final__changes-head">
            <p className="result-panel__section-title">Record changes</p>
            {gapId && <span className="result-final__changes-hint">Click a value to correct it</span>}
          </div>
          <table className="diff-table">
            <thead>
              <tr>
                <th>Field</th>
                <th>Before</th>
                <th>After</th>
              </tr>
            </thead>
            <tbody>
              {changeEntries.map(([field, change]) => (
                <tr key={field}>
                  <td className="diff-table__field">{field}</td>
                  <td className="diff-table__from">{change.from || "—"}</td>
                  <td className="diff-table__to">
                    <EditableAfterCell
                      gapId={gapId}
                      field={field}
                      value={change.to}
                      edited={manualEdits.includes(field)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!success && careGap?.reason && <p className="result-panel__retry-note">{careGap.reason}</p>}
    </section>
  );
}

function EditableAfterCell({
  gapId,
  field,
  value,
  edited,
}: {
  gapId?: string;
  field: string;
  value: string;
  edited: boolean;
}) {
  const applyCareGapEdit = useWorkflowStore((s) => s.applyCareGapEdit);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canEdit = Boolean(gapId);

  function cancel() {
    setEditing(false);
    setDraft(value);
    setError(null);
  }

  async function commit() {
    if (saving) return;
    const next = draft.trim();
    if (!next || next === value) {
      cancel();
      return;
    }
    if (!gapId) {
      setError("No gap id");
      return;
    }
    setSaving(true);
    setError(null);
    const res = await updateCareGapField(gapId, field, next);
    setSaving(false);
    if (!res.success) {
      setError(res.error ?? "Save failed");
      return;
    }
    applyCareGapEdit(field, next);
    setEditing(false);
  }

  if (editing) {
    return (
      <span className="diff-cell-edit">
        <input
          className="diff-cell-input"
          autoFocus
          value={draft}
          disabled={saving}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void commit();
            if (e.key === "Escape") cancel();
          }}
          onBlur={() => void commit()}
        />
        {saving && <span className="diff-cell-spinner" aria-hidden />}
        {error && <span className="diff-cell-error">{error}</span>}
      </span>
    );
  }

  return (
    <button
      type="button"
      className="diff-cell-to"
      disabled={!canEdit}
      onClick={() => {
        setDraft(value);
        setEditing(true);
      }}
      title={canEdit ? "Click to correct this value — writes to care_gaps.csv" : undefined}
    >
      <span className="diff-cell-to__value">{value}</span>
      {edited && <span className="diff-cell-tag">Edited</span>}
      {canEdit && <Pencil size={11} className="diff-cell-pencil" aria-hidden />}
    </button>
  );
}
