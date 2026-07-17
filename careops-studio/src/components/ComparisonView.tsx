import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronUp,
  Circle,
  Database,
  Grid3x3,
  LayoutGrid,
  Lightbulb,
  Loader2,
  Sparkles,
  Table2,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { comparisonClient } from "../lib/comparisonClient";
import { useFileStore } from "../store/fileStore";
import { useUiStore } from "../store/uiStore";
import { useWorkflowStore } from "../store/workflowStore";
import { HEATMAP_DIMENSIONS, type GenerationQualityReport, type WorkflowStage } from "../types";

// ── Stage definitions (workflow 3: generation_quality) ──────────────────────

const INITIAL_STAGES: WorkflowStage[] = [
  { id: "pattern_extraction", label: "Pattern Extraction", description: "Does this upload teach the generator something new?", status: "pending" },
  { id: "generation_batch", label: "Generation Batch", description: "Generate + SME-validate a fresh synthetic batch", status: "pending" },
  { id: "quality_scoring", label: "Quality Scoring", description: "Score the batch against the real summary", status: "pending" },
];

const DIMENSION_LABELS: Record<string, string> = {
  measure_alignment: "Measure",
  channel_alignment: "Channel",
  disposition_plausibility: "Disposition",
  confidence_calibration: "Confidence",
  structural_realism: "Realism",
};

/** Compact labels for the dense sortable table (full names shown on hover). */
const DIMENSION_TABLE_LABELS: Record<string, string> = {
  measure_alignment: "Measure",
  channel_alignment: "Channel",
  disposition_plausibility: "Dispo",
  confidence_calibration: "Conf",
  structural_realism: "Realism",
};

const SOURCE_TYPE_LABELS: Record<string, string> = {
  call_transcript: "Call Transcript",
  ivr_result_code: "IVR Result",
  csr_note: "CSR Note",
  web_form: "Web Form",
};

type RunStatus = "idle" | "running" | "complete" | "error";
type HeatmapView = "heatmap" | "table";
type SortKey = "record_id" | "source_type" | "overall" | string;

interface DatasetSummarySnapshot {
  batch_id?: string;
  total_records?: number;
  by_source_type?: Record<string, number>;
}

interface TrendPoint {
  runId: string;
  batchId: string;
  overallScore: number;
  at: string;
}

// ── Main view ────────────────────────────────────────────────────────────────

export function ComparisonView() {
  const activeRunId = useWorkflowStore((s) => s.activeRun?.id);
  const addGeneratedBatch = useFileStore((s) => s.addGeneratedBatch);
  const openFileInBackground = useUiStore((s) => s.openFileInBackground);
  const [status, setStatus] = useState<RunStatus>("idle");
  const [stages, setStages] = useState<WorkflowStage[]>(INITIAL_STAGES);
  const [logs, setLogs] = useState<string[]>([]);
  const [logsOpen, setLogsOpen] = useState(false);
  const [report, setReport] = useState<GenerationQualityReport | null>(null);
  const [datasetSummary, setDatasetSummary] = useState<DatasetSummarySnapshot | null>(null);
  const [patternLearned, setPatternLearned] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const unsubRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    unsubRef.current?.();
    unsubRef.current = null;

    if (!activeRunId) {
      setStatus("idle");
      return;
    }

    setStatus("running");
    setStages(INITIAL_STAGES.map((s) => ({ ...s, status: "pending" })));
    setLogs([]);
    setLogsOpen(true);
    setReport(null);
    setDatasetSummary(null);
    setPatternLearned(null);
    setErrorMsg(null);

    const addLog = (msg: string) => {
      const ts = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      setLogs((prev) => [...prev, `[${ts}] ${msg}`]);
    };
    const setStageStatus = (id: string, s: WorkflowStage["status"], message?: string) => {
      setStages((prev) => prev.map((st) => (st.id === id ? { ...st, status: s, message } : st)));
    };

    addLog("Watching this upload for generator-quality scoring…");

    unsubRef.current = comparisonClient.subscribe(
      activeRunId,
      (event) => {
        if (event.type === "stage_start") {
          setStageStatus(event.stageId, "active", event.message);
          addLog(event.message ?? `${event.stageId} started`);
        } else if (event.type === "stage_progress") {
          addLog(event.message ?? `${event.stageId} in progress`);
        } else if (event.type === "stage_complete") {
          setStageStatus(event.stageId, "completed", event.message);
          addLog(event.message ?? `${event.stageId} complete`);
          if (event.stageId === "pattern_extraction") {
            setPatternLearned(event.message ?? null);
          }
          if (event.stageId === "generation_batch" && event.result) {
            const summary = event.result as DatasetSummarySnapshot;
            setDatasetSummary(summary);
            if (summary.batch_id) {
              const node = addGeneratedBatch(summary.batch_id, summary.total_records ?? 0);
              openFileInBackground(node.id);
            }
          }
        } else if (event.type === "run_error") {
          setStatus("error");
          setErrorMsg(event.error);
          setLogsOpen(true);
          addLog(`Error: ${event.error}`);
        } else if (event.type === "run_complete") {
          setStatus("complete");
          setStages((prev) => prev.map((s) => ({ ...s, status: "completed" })));
          setLogsOpen(false);
          addLog("Scoring complete.");
        }
      },
      (r) => {
        setReport(r);
        setTrend((prev) =>
          [...prev, { runId: activeRunId, batchId: r.batch_id, overallScore: r.overall_score, at: new Date().toISOString() }].slice(-12),
        );
      },
    );

    return () => {
      unsubRef.current?.();
      unsubRef.current = null;
    };
  }, [activeRunId]);

  if (status === "idle") {
    return (
      <div className="comparison comparison--idle">
        <div className="comparison__idle-icon">
          <Grid3x3 size={36} />
        </div>
        <h2 className="comparison__idle-title">Generator Quality Dashboard</h2>
        <p className="comparison__idle-hint">
          Upload a file to see it in action: the data generator produces a fresh synthetic
          batch informed by your upload, and this dashboard scores every record in that batch
          against the real summary extracted from your file — a live analytical read on how
          well the generator's output resembles production data.
        </p>
      </div>
    );
  }

  return (
    <div className="comparison comparison--dashboard">
      <header className="dashboard-header">
        <div className="workflow__headline">
          <p className="workflow__eyebrow">Workflow 3 · Generator Quality</p>
          <h2 className="workflow__title">Generator Quality Dashboard</h2>
          <p className="workflow__meta">
            {report && (
              <>
                <span className="mono-chip">{report.batch_id}</span>
                <span className="workflow__meta-sep" aria-hidden>
                  ·
                </span>
              </>
            )}
            Synthetic batch scored against the reference summary
          </p>
        </div>
        <div className="dashboard-header__aside">
          <span className={`status-pill status-pill--${status}`}>
            <span className="status-pill__dot" aria-hidden />
            {status.charAt(0).toUpperCase() + status.slice(1)}
          </span>
          <ProgressStepper stages={stages} />
        </div>
      </header>

      {status === "running" && (
        <div className="active-agent-banner">
          <Loader2 size={13} className="spin" />
          <span className="active-agent-banner__name">
            {stages.find((s) => s.status === "active")?.label ?? "Working"}
          </span>
          <span className="active-agent-banner__suffix">is processing…</span>
        </div>
      )}

      {status === "error" && errorMsg && (
        <section className="result-panel">
          <div className="result-panel__header">
            <span className="result-panel__eyebrow">Error</span>
            <span className="result-panel__badge result-panel__badge--warn">failed</span>
          </div>
          <p className="result-panel__retry-note">{errorMsg}</p>
        </section>
      )}

      {report && (
        <div className="dashboard-primary">
          <HeatmapSection report={report} />
          <StatGrid report={report} datasetSummary={datasetSummary} patternLearned={patternLearned} />
        </div>
      )}

      {report && (
        <div className="analytics-grid">
          <section className="result-panel analytics-panel">
            <div className="result-panel__header">
              <span className="result-panel__eyebrow">Alignment by Dimension</span>
            </div>
            <DimensionBarChart report={report} />
          </section>

          <section className="result-panel analytics-panel">
            <div className="result-panel__header">
              <span className="result-panel__eyebrow">Batch Composition</span>
            </div>
            {datasetSummary?.by_source_type ? (
              <SourceBreakdown bySourceType={datasetSummary.by_source_type} />
            ) : (
              <p className="analytics-panel__empty">No batch composition data for this run.</p>
            )}
          </section>

          <section className="result-panel analytics-panel">
            <div className="result-panel__header">
              <span className="result-panel__eyebrow">Quality Trend This Session</span>
            </div>
            <TrendSparkline history={trend} />
          </section>
        </div>
      )}

      {report && (
        <section className="result-panel insight-panel">
          <div className="result-panel__header">
            <span className="result-panel__eyebrow">Analyst Insight</span>
          </div>
          <div className="insight-panel__body">
            <span className="insight-panel__mark" aria-hidden>
              <Lightbulb size={16} />
            </span>
            <p className="insight-panel__text">{report.narrative}</p>
          </div>
        </section>
      )}

      <ActivityLog logs={logs} open={logsOpen} onToggle={() => setLogsOpen((o) => !o)} />
    </div>
  );
}

// ── Progress stepper ─────────────────────────────────────────────────────────

function ProgressStepper({ stages }: { stages: WorkflowStage[] }) {
  return (
    <ol className="stage-rail stage-rail--compact" aria-label="Generation quality stages">
      {stages.map((stage, index) => (
        <li key={stage.id} className={`stage-rail__item stage-rail__item--${stage.status}`}>
          {index > 0 && <span className="stage-rail__connector" aria-hidden />}
          <span className="stage-rail__dot" aria-hidden>
            {stage.status === "completed" && <Check size={12} strokeWidth={3} />}
            {stage.status === "active" && <Loader2 size={12} className="spin" />}
            {stage.status === "error" && <AlertCircle size={12} />}
            {stage.status === "pending" && <Circle size={10} />}
          </span>
          <span className="stage-rail__label">{stage.label}</span>
        </li>
      ))}
    </ol>
  );
}

// ── Stat tiles ───────────────────────────────────────────────────────────────

function StatGrid({
  report,
  datasetSummary,
  patternLearned,
}: {
  report: GenerationQualityReport;
  datasetSummary: DatasetSummarySnapshot | null;
  patternLearned: string | null;
}) {
  const scoreTone = report.overall_score >= 75 ? "good" : report.overall_score >= 50 ? "warn" : "bad";
  const learnedNew = !!patternLearned && !patternLearned.toLowerCase().includes("no novel");

  return (
    <div className="kpi-grid">
      <ScoreCard score={report.overall_score} tone={scoreTone} />
      <div className="kpi-grid__tiles">
        <StatTile
          icon={<Database size={15} />}
          label="Records Scored"
          value={`${report.cells.length}`}
          sublabel={datasetSummary?.batch_id ? `batch ${datasetSummary.batch_id}` : "this batch"}
        />
        <StatTile
          icon={<TrendingUp size={15} />}
          label="Strongest Dimension"
          value={DIMENSION_LABELS[report.strongest_dimension] ?? report.strongest_dimension}
          tone="good"
        />
        <StatTile
          icon={<TrendingDown size={15} />}
          label="Weakest Dimension"
          value={DIMENSION_LABELS[report.weakest_dimension] ?? report.weakest_dimension}
          tone="warn"
        />
        <StatTile
          icon={<Sparkles size={15} />}
          label="Corpus Growth"
          value={learnedNew ? "New pattern" : "No change"}
          sublabel={learnedNew ? "learned_patterns.json grew" : "nothing novel this upload"}
          tone={learnedNew ? "good" : "default"}
        />
      </div>
    </div>
  );
}

function ScoreCard({ score, tone }: { score: number; tone: "good" | "warn" | "bad" }) {
  const pct = Math.max(0, Math.min(100, score));
  const r = 46;
  const circumference = 2 * Math.PI * r;
  const dash = (pct / 100) * circumference;
  const grade = pct >= 75 ? "Strong resemblance" : pct >= 50 ? "Partial resemblance" : "Weak resemblance";

  return (
    <div className={`score-card score-card--${tone}`}>
      <div className="score-card__gauge">
        <svg viewBox="0 0 120 120" role="img" aria-label={`Overall quality ${Math.round(pct)} out of 100`}>
          <circle className="score-card__track" cx="60" cy="60" r={r} />
          <circle
            className="score-card__arc"
            cx="60"
            cy="60"
            r={r}
            transform="rotate(-90 60 60)"
            style={{ strokeDasharray: `${dash} ${circumference}` }}
          />
        </svg>
        <div className="score-card__center">
          <span className="score-card__value">{Math.round(pct)}</span>
          <span className="score-card__scale">/ 100</span>
        </div>
      </div>
      <div className="score-card__meta">
        <span className="score-card__label">Overall Quality</span>
        <span className="score-card__grade">{grade}</span>
        <span className="score-card__hint">avg. alignment across every scored record</span>
      </div>
    </div>
  );
}

function StatTile({
  icon,
  label,
  value,
  sublabel,
  tone = "default",
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sublabel?: string;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  return (
    <div className={`stat-tile stat-tile--${tone}`}>
      <div className="stat-tile__icon">{icon}</div>
      <div className="stat-tile__body">
        <span className="stat-tile__label">{label}</span>
        <span className="stat-tile__value">{value}</span>
        {sublabel && <span className="stat-tile__sublabel">{sublabel}</span>}
      </div>
    </div>
  );
}

// ── Dimension bar chart ──────────────────────────────────────────────────────

function DimensionBarChart({ report }: { report: GenerationQualityReport }) {
  const dims = report.dimensions.length ? report.dimensions : [...HEATMAP_DIMENSIONS];
  const rows = dims.map((dim) => {
    const values = report.cells.map((c) => (c as unknown as Record<string, number>)[dim] ?? 0);
    const avg = values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
    return { dim, avg };
  });

  return (
    <div className="dim-bars" role="img" aria-label="Average alignment score per dimension">
      {rows.map(({ dim, avg }) => (
        <div className="dim-bar-row" key={dim}>
          <span className="dim-bar-row__label">{DIMENSION_LABELS[dim] ?? dim}</span>
          <div className="dim-bar-row__track">
            <div
              className="dim-bar-row__fill"
              style={{ width: `${Math.max(avg, 2)}%`, background: scoreToColor(avg) }}
            />
          </div>
          <span className="dim-bar-row__value">{avg.toFixed(0)}</span>
        </div>
      ))}
    </div>
  );
}

// ── Source-type composition ──────────────────────────────────────────────────

function SourceBreakdown({ bySourceType }: { bySourceType: Record<string, number> }) {
  const entries = Object.entries(bySourceType);
  const total = entries.reduce((sum, [, count]) => sum + count, 0) || 1;

  return (
    <div className="source-breakdown" role="img" aria-label="Synthetic batch composition by source type">
      {entries.map(([type, count]) => (
        <div className="source-breakdown__row" key={type}>
          <span className="source-breakdown__label">{SOURCE_TYPE_LABELS[type] ?? type}</span>
          <div className="source-breakdown__track">
            <div className="source-breakdown__fill" style={{ width: `${(count / total) * 100}%` }} />
          </div>
          <span className="source-breakdown__value">{count}</span>
        </div>
      ))}
    </div>
  );
}

// ── Session quality trend ────────────────────────────────────────────────────

function TrendSparkline({ history }: { history: TrendPoint[] }) {
  if (history.length < 2) {
    return (
      <p className="analytics-panel__empty">
        Upload more files this session to see the quality trend build up
        {history.length === 1 ? ` — ${Math.round(history[0].overallScore)} so far.` : "."}
      </p>
    );
  }

  const width = 260;
  const height = 64;
  const padX = 8;
  const padY = 10;

  const points = history.map((entry, i) => ({
    x: padX + (i / (history.length - 1)) * (width - padX * 2),
    y: padY + (1 - entry.overallScore / 100) * (height - padY * 2),
    score: entry.overallScore,
  }));

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const last = points[points.length - 1];

  return (
    <svg
      className="trend-sparkline"
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      role="img"
      aria-label={`Quality score trend across ${history.length} uploads this session, currently ${Math.round(last.score)}`}
    >
      <path d={path} fill="none" stroke="var(--humana-green)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle
          key={i}
          cx={p.x}
          cy={p.y}
          r={i === points.length - 1 ? 4 : 2.5}
          fill={i === points.length - 1 ? "var(--humana-green-deep)" : "var(--humana-green)"}
          stroke="#fff"
          strokeWidth={1.5}
        />
      ))}
      <text x={last.x} y={Math.max(last.y - 10, 10)} textAnchor="end" className="trend-sparkline__label">
        {last.score.toFixed(0)}
      </text>
    </svg>
  );
}

// ── Activity log (collapsible) ───────────────────────────────────────────────

function ActivityLog({ logs, open, onToggle }: { logs: string[]; open: boolean; onToggle: () => void }) {
  return (
    <section className="workflow__logs" aria-label="Generation quality output">
      <button type="button" className="workflow__logs-header workflow__logs-header--button" onClick={onToggle}>
        Activity Log ({logs.length})
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {open && (
        <pre className="workflow__logs-body">
          {logs.map((line, i) => (
            <div key={i}>{line}</div>
          ))}
        </pre>
      )}
    </section>
  );
}

// ── Heatmap / table section ─────────────────────────────────────────────────

/** Sequential single-hue ramp (light → dark), light=low score, dark=high score. */
function scoreToColor(score: number): string {
  const clamped = Math.max(0, Math.min(100, score));
  const stops: [number, [number, number, number]][] = [
    [0, [238, 246, 227]],
    [50, [122, 184, 67]],
    [100, [42, 74, 12]],
  ];
  let lo = stops[0];
  let hi = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++) {
    if (clamped >= stops[i][0] && clamped <= stops[i + 1][0]) {
      lo = stops[i];
      hi = stops[i + 1];
      break;
    }
  }
  const range = hi[0] - lo[0] || 1;
  const t = (clamped - lo[0]) / range;
  const r = Math.round(lo[1][0] + (hi[1][0] - lo[1][0]) * t);
  const g = Math.round(lo[1][1] + (hi[1][1] - lo[1][1]) * t);
  const b = Math.round(lo[1][2] + (hi[1][2] - lo[1][2]) * t);
  return `rgb(${r}, ${g}, ${b})`;
}

function scoreTextColor(score: number): string {
  return score >= 55 ? "#ffffff" : "#1c2f10";
}

function HeatmapSection({ report }: { report: GenerationQualityReport }) {
  const [view, setView] = useState<HeatmapView>("heatmap");
  const dims = report.dimensions.length ? report.dimensions : [...HEATMAP_DIMENSIONS];

  return (
    <section className="result-panel heatmap-panel">
      <div className="result-panel__header heatmap-panel__header">
        <div className="heatmap-panel__heading">
          <span className="result-panel__eyebrow heatmap-panel__eyebrow">
            <LayoutGrid size={14} />
            Alignment Heatmap
          </span>
          <p className="heatmap-panel__subtitle">
            {report.cells.length} generated records &times; {dims.length} realism dimensions —
            every cell scored 0–100 against the reference summary
          </p>
        </div>

        <div className="heatmap-panel__controls">
          <div className="heatmap-legend" aria-label="Score color scale from low to high">
            <span className="heatmap-legend__cap">0</span>
            <span className="heatmap-legend__scale" aria-hidden />
            <span className="heatmap-legend__cap">100</span>
          </div>
          <div className="view-toggle" role="tablist" aria-label="Alignment detail view">
            <button
              type="button"
              role="tab"
              aria-selected={view === "heatmap"}
              className={`view-toggle__btn ${view === "heatmap" ? "view-toggle__btn--active" : ""}`}
              onClick={() => setView("heatmap")}
            >
              <LayoutGrid size={13} /> Heatmap
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "table"}
              className={`view-toggle__btn ${view === "table" ? "view-toggle__btn--active" : ""}`}
              onClick={() => setView("table")}
            >
              <Table2 size={13} /> Table
            </button>
          </div>
        </div>
      </div>
      {view === "heatmap" ? <QualityHeatmap report={report} /> : <QualityTable report={report} />}
    </section>
  );
}

function QualityHeatmap({ report }: { report: GenerationQualityReport }) {
  const dims = report.dimensions.length ? report.dimensions : [...HEATMAP_DIMENSIONS];

  return (
    <div className="heatmap-scroll">
      <table className="heatmap">
        <thead>
          <tr>
            <th className="heatmap__corner" />
            {report.cells.map((cell) => (
              <th key={cell.record_id} className="heatmap__col-header">
                <span className="heatmap__record-id">{cell.record_id}</span>
                <span className="heatmap__source-type">{cell.source_type.replace(/_/g, " ")}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dims.map((dim) => (
            <tr key={dim}>
              <th className="heatmap__row-header">{DIMENSION_LABELS[dim] ?? dim}</th>
              {report.cells.map((cell) => {
                const value = (cell as unknown as Record<string, number>)[dim] ?? 0;
                return (
                  <td key={cell.record_id} className="heatmap__cell-wrap">
                    <div
                      className="heatmap__cell"
                      style={{ background: scoreToColor(value), color: scoreTextColor(value) }}
                    >
                      {Math.round(value)}
                      <span className="heatmap__tooltip">
                        <strong>{cell.record_id}</strong> · {DIMENSION_LABELS[dim] ?? dim}: {Math.round(value)}
                        {cell.notes && (
                          <>
                            <br />
                            {cell.notes}
                          </>
                        )}
                      </span>
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
          <tr className="heatmap__overall-row">
            <th className="heatmap__row-header">Overall</th>
            {report.cells.map((cell) => (
              <td key={cell.record_id} className="heatmap__cell-wrap">
                <div
                  className="heatmap__cell heatmap__cell--overall"
                  style={{ background: scoreToColor(cell.overall), color: scoreTextColor(cell.overall) }}
                >
                  {Math.round(cell.overall)}
                </div>
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function QualityTable({ report }: { report: GenerationQualityReport }) {
  const dims = report.dimensions.length ? report.dimensions : [...HEATMAP_DIMENSIONS];
  const [sortKey, setSortKey] = useState<SortKey>("overall");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(() => {
    const copy = [...report.cells];
    copy.sort((a, b) => {
      const av = (a as unknown as Record<string, string | number>)[sortKey];
      const bv = (b as unknown as Record<string, string | number>)[sortKey];
      if (typeof av === "string" || typeof bv === "string") {
        const cmp = String(av).localeCompare(String(bv));
        return sortDir === "asc" ? cmp : -cmp;
      }
      const cmp = (av as number) - (bv as number);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [report.cells, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  function SortHeader({ label, k, title }: { label: string; k: SortKey; title?: string }) {
    const active = sortKey === k;
    return (
      <th
        className={`quality-table__sortable ${active ? "quality-table__sortable--active" : ""}`}
        aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
      >
        <button
          type="button"
          className="quality-table__sort-btn"
          onClick={() => toggleSort(k)}
          title={title ?? label}
        >
          <span>{label}</span>
          <span className="quality-table__sort-caret" aria-hidden>
            {active && (sortDir === "asc" ? <ChevronUp size={11} /> : <ChevronDown size={11} />)}
          </span>
        </button>
      </th>
    );
  }

  return (
    <div className="heatmap-scroll">
      <table className="quality-table">
        <thead>
          <tr>
            <SortHeader label="Record" k="record_id" />
            <SortHeader label="Source" k="source_type" />
            {dims.map((dim) => (
              <SortHeader
                key={dim}
                label={DIMENSION_TABLE_LABELS[dim] ?? DIMENSION_LABELS[dim] ?? dim}
                title={DIMENSION_LABELS[dim] ?? dim}
                k={dim}
              />
            ))}
            <SortHeader label="Overall" k="overall" />
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((cell) => (
            <tr key={cell.record_id}>
              <td className="quality-table__record-id">{cell.record_id}</td>
              <td className="quality-table__source">{(cell.source_type || "").replace(/_/g, " ")}</td>
              {dims.map((dim) => {
                const value = (cell as unknown as Record<string, number>)[dim] ?? 0;
                return (
                  <td key={dim}>
                    <span className="quality-table__score-chip" style={{ background: scoreToColor(value), color: scoreTextColor(value) }}>
                      {Math.round(value)}
                    </span>
                  </td>
                );
              })}
              <td>
                <span
                  className="quality-table__score-chip quality-table__score-chip--overall"
                  style={{ background: scoreToColor(cell.overall), color: scoreTextColor(cell.overall) }}
                >
                  {Math.round(cell.overall)}
                </span>
              </td>
              <td className="quality-table__notes">{cell.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
