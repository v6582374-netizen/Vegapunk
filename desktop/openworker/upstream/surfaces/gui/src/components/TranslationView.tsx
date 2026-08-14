// The BabelDOC document-translation surface: prototype variant A ("Run desk") raised to
// production. Three resident columns — queue · live run · artifacts — so a translation is
// started, watched, and collected without ever navigating away.
//
// Everything on screen comes from the real endpoints in ../api. Progress is driven by the
// server's own append-only event log (getTranslationRunEvents, cursor-polled); the run's own
// `stages` array is authoritative for the stage table, with TRANSLATE_STAGES as a fallback only.
// The one semantic this integration adds on top of upstream BabelDOC is the bundle directory:
// source + translations land in ONE folder beside the original document, so that absolute path
// is given first-class treatment in the artifacts column.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  cancelTranslationRun,
  fetchTranslationArtifactBlobUrl,
  getTranslationRun,
  getTranslationRunEvents,
  getTranslationSettings,
  listTranslationDocuments,
  listTranslationRuns,
  registerTranslationDocuments,
  startTranslationRuns,
  streamTranslationRunLog,
  translationArtifactUrl,
  type TranslationArtifact,
  type TranslationDocument,
  type TranslationRun,
  type TranslationRunEvent,
  type TranslationStage,
  type TranslationUploadFile,
} from "../api";
import { Icon, type IconName } from "./Icon";
import {
  ARTIFACT_ROLE_LABEL,
  TRANSLATE_STAGES,
  bundleDirFor,
  dirOf,
  formatBytes,
  formatDuration,
  shortStage,
} from "./translationOptions";

const CARD = "rounded-xl2 border border-line bg-panel";
const EVENT_POLL_MS = 450;
const RUNS_POLL_MS = 1200;
const FEED_LIMIT = 120;
const LOG_LIMIT = 400;

/** Progress projected from the event log — the live truth while a run is in flight. */
type Progress = {
  stage: string | null;
  stage_index: number;
  stage_current: number;
  stage_total: number;
  stage_progress: number;
  overall_progress: number;
};

type FeedLine = { seq: number; at: number; type: string; text: string };

const isActive = (run: TranslationRun | null): boolean =>
  run != null && (run.state === "queued" || run.state === "running");

const errText = (caught: unknown, fallback: string): string =>
  caught instanceof Error && caught.message ? caught.message : fallback;

/* ------------------------------------------------------------------ motion */

function usePrefersReducedMotion(): boolean {
  const query = "(prefers-reduced-motion: reduce)";
  const [reduced, setReduced] = useState(() => {
    try {
      return window.matchMedia?.(query).matches ?? false;
    } catch {
      return false;
    }
  });
  useEffect(() => {
    let mq: MediaQueryList | null = null;
    try {
      mq = window.matchMedia?.(query) ?? null;
    } catch {
      return;
    }
    if (!mq?.addEventListener) return;
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    mq.addEventListener("change", onChange);
    return () => mq?.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

/**
 * Exponential approach to `target`, ~200ms to settle. Progress arrives as discrete event jumps;
 * interpolating keeps the bar continuous. A new target simply retargets the same motion, so it is
 * interruptible by construction, and reduced-motion / non-visual environments jump straight there.
 */
function useSmoothed(target: number, reduced: boolean): number {
  const [value, setValue] = useState(target);
  const current = useRef(target);

  useEffect(() => {
    if (reduced || typeof requestAnimationFrame !== "function") {
      current.current = target;
      setValue(target);
      return;
    }
    let frame = 0;
    let last = typeof performance !== "undefined" ? performance.now() : Date.now();
    const tick = (now: number) => {
      const dt = Math.min(64, Math.max(1, now - last));
      last = now;
      const delta = target - current.current;
      if (Math.abs(delta) < 0.05) {
        current.current = target;
        setValue(target);
        return;
      }
      current.current += delta * (1 - Math.exp(-dt / 80));
      setValue(current.current);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, reduced]);

  return value;
}

/* ------------------------------------------------------------------ progress primitives */

function ProgressBar({
  pct,
  label,
  valueText,
  tone = "accent",
}: {
  pct: number;
  label: string;
  valueText: string;
  tone?: "accent" | "ok" | "danger";
}) {
  const reduced = usePrefersReducedMotion();
  const clamped = Math.max(0, Math.min(100, pct));
  const shown = useSmoothed(clamped, reduced);
  const fill = tone === "ok" ? "bg-ok" : tone === "danger" ? "bg-danger" : "bg-accent";
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
      aria-valuetext={valueText}
      className="h-1.5 w-full overflow-hidden rounded-full bg-paper"
    >
      <div
        className={`h-full w-full origin-left rounded-full ${fill}`}
        style={{ transform: `scaleX(${(shown / 100).toFixed(4)})` }}
      />
    </div>
  );
}

/** One weight-proportional segment. Its own component so the spring hook never runs in a loop. */
function StageSegment({ stage, weight, frac }: { stage: TranslationStage; weight: number; frac: number }) {
  const reduced = usePrefersReducedMotion();
  const shown = useSmoothed(Math.max(0, Math.min(1, frac)), reduced);
  return (
    <span
      className="relative block h-full overflow-hidden rounded-[2px] bg-paper"
      style={{ flex: weight }}
      title={`${shortStage(stage.name)} · ${weight.toFixed(1)}% of the work`}
    >
      <i
        className={`absolute inset-0 origin-left rounded-[2px] ${shown >= 0.999 ? "bg-ok" : "bg-accent"}`}
        style={{ transform: `scaleX(${shown.toFixed(4)})` }}
      />
    </span>
  );
}

/** Segment widths are BabelDOC's stage weights: the bar itself teaches where the time goes. */
function WeightedTrack({ stages, fracs }: { stages: TranslationStage[]; fracs: number[] }) {
  return (
    <div className="flex h-2 gap-[2px]" aria-hidden="true">
      {stages.map((stage, index) => (
        <StageSegment key={`${stage.name}-${index}`} stage={stage} weight={stage.weight} frac={fracs[index] ?? 0} />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ small shells */

function Pill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "ok" | "warn" | "danger" | "accent" }) {
  const map = {
    neutral: "border-line bg-paper text-muted",
    ok: "border-okLine bg-okSoft text-ok",
    warn: "border-line bg-warnSoft text-warnInk",
    danger: "border-line bg-dangerSoft text-danger",
    accent: "border-line bg-accentSoft text-accent",
  } as const;
  return (
    <span className={`inline-flex min-h-[22px] shrink-0 items-center gap-1 rounded-full border px-2 text-[10.5px] font-medium ${map[tone]}`}>
      {children}
    </span>
  );
}

function stateTone(state: TranslationRun["state"]): "neutral" | "ok" | "warn" | "danger" | "accent" {
  if (state === "done") return "ok";
  if (state === "error") return "danger";
  if (state === "cancelled") return "warn";
  if (state === "running") return "accent";
  return "neutral";
}

const STATE_LABEL: Record<TranslationRun["state"], string> = {
  queued: "Queued",
  running: "Running",
  done: "Bundled",
  error: "Failed",
  cancelled: "Cancelled",
};

function ColumnHead({ title, icon, right }: { title: string; icon: IconName; right?: React.ReactNode }) {
  return (
    <div className="mb-3 flex min-h-7 items-center gap-2">
      <Icon name={icon} size={15} />
      <h2 className="text-[13px] font-semibold tracking-[-0.01em] text-ink">{title}</h2>
      <span className="ml-auto flex items-center gap-1.5">{right}</span>
    </div>
  );
}

/** The absolute path of the folder holding source + translations. The added semantic, made loud. */
function BundlePath({ path, pending, onCopy }: { path: string; pending?: boolean; onCopy: (path: string) => void }) {
  return (
    <div className={`${CARD} p-3`}>
      <div className="text-[10px] font-semibold uppercase tracking-[0.09em] text-muted">
        {pending ? "Will be written to" : "Bundled beside the original"}
      </div>
      <div className="mt-1.5 flex items-start gap-2">
        <Icon name="folder" size={13} className={pending ? "mt-0.5 shrink-0 text-muted" : "mt-0.5 shrink-0 text-ok"} />
        <code
          className={`min-w-0 flex-1 break-all font-mono text-[11.5px] leading-[1.45] ${pending ? "text-muted" : "text-ink"}`}
          data-testid="translation-bundle-dir"
        >
          {path}/
        </code>
      </div>
      <button
        type="button"
        className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-line px-2 py-1 text-[11px] text-muted transition-colors hover:bg-paper hover:text-ink"
        onClick={() => onCopy(path)}
      >
        <Icon name="copy" size={12} /> Copy path
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ the view */

export function TranslationView({ onOpenSettings }: { onOpenSettings?: () => void } = {}) {
  const [documents, setDocuments] = useState<TranslationDocument[]>([]);
  const [runs, setRuns] = useState<TranslationRun[]>([]);
  const [progress, setProgress] = useState<Record<string, Progress>>({});
  const [feed, setFeed] = useState<Record<string, FeedLine[]>>({});
  const [focusedDocId, setFocusedDocId] = useState<string | null>(null);
  const [checked, setChecked] = useState<string[]>([]);
  const [langPair, setLangPair] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");

  const [pathDraft, setPathDraft] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileInput = useRef<HTMLInputElement | null>(null);

  const [logOpen, setLogOpen] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [preview, setPreview] = useState<{ name: string; url: string } | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const cursors = useRef(new Map<string, number>());

  /* ---- load ---- */

  const reload = useCallback(async () => {
    try {
      const [docs, runList] = await Promise.all([listTranslationDocuments(), listTranslationRuns()]);
      setDocuments(docs.documents);
      setRuns(runList.runs);
      setError(null);
    } catch (caught) {
      setError(errText(caught, "The translation service is unavailable."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
    getTranslationSettings()
      .then((doc) => setLangPair(`${doc.values.lang_in || "auto"} → ${doc.values.lang_out || "zh"}`))
      .catch(() => setLangPair(null));
  }, [reload]);

  /* ---- selection ---- */

  const runsByDoc = useMemo(() => {
    const map = new Map<string, TranslationRun>();
    for (const run of [...runs].sort((a, b) => a.created_at - b.created_at)) map.set(run.document_id, run);
    return map;
  }, [runs]);

  const focusedDoc = useMemo(
    () => documents.find((doc) => doc.document_id === focusedDocId) ?? documents[0] ?? null,
    [documents, focusedDocId],
  );
  const serverRun = focusedDoc ? runsByDoc.get(focusedDoc.document_id) ?? null : null;
  const runId = serverRun?.run_id ?? null;
  const runActive = isActive(serverRun);

  /* ---- authoritative snapshots while anything is in flight ---- */

  const activeKey = runs.filter((run) => isActive(run)).map((run) => run.run_id).join(",");
  useEffect(() => {
    if (!activeKey) return;
    let alive = true;
    const timer = setInterval(() => {
      listTranslationRuns()
        .then((next) => {
          if (alive) setRuns(next.runs);
        })
        .catch(() => {});
    }, RUNS_POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [activeKey]);

  /* ---- cursor-polled event log: the progress driver ---- */

  useEffect(() => {
    if (!runId) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const absorb = (events: TranslationRunEvent[]) => {
      if (!events.length) return;
      setProgress((prev) => {
        const base: Progress = prev[runId] ?? {
          stage: null,
          stage_index: -1,
          stage_current: 0,
          stage_total: 0,
          stage_progress: 0,
          overall_progress: 0,
        };
        const next = { ...base };
        for (const event of events) {
          if (typeof event.stage === "string" && event.stage) next.stage = event.stage;
          if (typeof event.stage_current === "number") next.stage_current = event.stage_current;
          if (typeof event.stage_total === "number") next.stage_total = event.stage_total;
          if (typeof event.stage_progress === "number") next.stage_progress = event.stage_progress;
          if (typeof event.overall_progress === "number") next.overall_progress = event.overall_progress;
        }
        return { ...prev, [runId]: next };
      });
      setFeed((prev) => {
        const lines = [...(prev[runId] ?? [])];
        for (const event of events) {
          lines.push({ seq: event.sequence, at: event.at, type: event.type, text: describeEvent(event) });
        }
        return { ...prev, [runId]: lines.slice(-FEED_LIMIT) };
      });
      const terminal = events.some((event) => ["finish", "error", "cancelled", "cancel"].includes(event.type));
      if (terminal) {
        getTranslationRun(runId)
          .then((fresh) => {
            if (!alive) return;
            setRuns((prev) => prev.map((run) => (run.run_id === fresh.run_id ? fresh : run)));
          })
          .catch(() => {});
      }
    };

    const poll = async () => {
      try {
        const page = await getTranslationRunEvents(runId, cursors.current.get(runId) ?? 0);
        if (!alive) return;
        cursors.current.set(runId, Math.max(cursors.current.get(runId) ?? 0, page.latest_sequence));
        absorb(page.events);
      } catch (caught) {
        if (alive) setError(errText(caught, "Run events could not be read."));
      }
      if (alive && runActive) timer = setTimeout(() => void poll(), EVENT_POLL_MS);
    };

    void poll();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [runId, runActive]);

  /* ---- raw log tail ---- */

  useEffect(() => {
    if (!logOpen || !runId) return;
    const controller = new AbortController();
    setLog([]);
    streamTranslationRunLog(
      runId,
      (line) => setLog((prev) => [...prev, line].slice(-LOG_LIMIT)),
      controller.signal,
    ).catch(() => {});
    return () => controller.abort();
  }, [logOpen, runId]);

  /* ---- inline PDF preview ---- */

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview.url);
  }, [preview]);

  useEffect(() => {
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev.url);
      return null;
    });
    setPreviewError(null);
  }, [runId]);

  /* ---- actions ---- */

  const announce = (message: string) => setStatus(message);

  /** Newly registered documents join the queue, pre-checked, and take focus. */
  function mergeDocuments(added: TranslationDocument[]) {
    if (!added.length) return;
    setDocuments((prev) => {
      const seen = new Set(prev.map((doc) => doc.document_id));
      return [...prev, ...added.filter((doc) => !seen.has(doc.document_id))];
    });
    setChecked((prev) => [...new Set([...prev, ...added.map((doc) => doc.document_id)])]);
    setFocusedDocId(added[0].document_id);
  }

  const registerFiles = async (files: File[]) => {
    const pdfs = files.filter((file) => /\.pdf$/i.test(file.name));
    if (!pdfs.length) {
      setError("Only PDF documents can be translated.");
      return;
    }
    setBusy("register");
    setError(null);
    try {
      const payload: TranslationUploadFile[] = await Promise.all(
        pdfs.map(async (file) => ({
          filename: file.name,
          content_base64: await readBase64(file),
          size: file.size,
        })),
      );
      const { documents: added } = await registerTranslationDocuments({ files: payload });
      mergeDocuments(added);
      announce(`${added.length} document${added.length === 1 ? "" : "s"} added to the queue.`);
    } catch (caught) {
      setError(errText(caught, "Those documents could not be registered."));
    } finally {
      setBusy(null);
    }
  };

  const registerPaths = async () => {
    const paths = pathDraft
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (!paths.length) return;
    setBusy("register");
    setError(null);
    try {
      const { documents: added } = await registerTranslationDocuments({ paths });
      mergeDocuments(added);
      setPathDraft("");
      announce(`${added.length} local document${added.length === 1 ? "" : "s"} registered.`);
    } catch (caught) {
      setError(errText(caught, "That path could not be registered."));
    } finally {
      setBusy(null);
    }
  };

  const start = async (ids: string[]) => {
    if (!ids.length) return;
    setBusy("start");
    setError(null);
    try {
      const { runs: started } = await startTranslationRuns(ids);
      setRuns((prev) => {
        const byId = new Map(prev.map((run) => [run.run_id, run] as const));
        for (const run of started) byId.set(run.run_id, run);
        return [...byId.values()];
      });
      // A restarted run re-reads its event log from sequence 0, so its projection starts clean.
      for (const run of started) cursors.current.delete(run.run_id);
      setProgress((prev) => {
        const next = { ...prev };
        for (const run of started) delete next[run.run_id];
        return next;
      });
      setFeed((prev) => {
        const next = { ...prev };
        for (const run of started) next[run.run_id] = [];
        return next;
      });
      if (started[0]) setFocusedDocId(started[0].document_id);
      setChecked([]);
      announce(`Started ${started.length} translation run${started.length === 1 ? "" : "s"}.`);
    } catch (caught) {
      setError(errText(caught, "The run could not be started."));
    } finally {
      setBusy(null);
    }
  };

  const cancel = async (id: string) => {
    setBusy("cancel");
    try {
      const fresh = await cancelTranslationRun(id);
      setRuns((prev) => prev.map((run) => (run.run_id === fresh.run_id ? fresh : run)));
      announce(`Run cancelled: ${fresh.filename}.`);
    } catch (caught) {
      setError(errText(caught, "The run could not be cancelled."));
    } finally {
      setBusy(null);
    }
  };

  const copyPath = (path: string) => {
    navigator.clipboard?.writeText?.(path).catch(() => {});
    announce(`Copied ${path}`);
  };

  const openPreview = async (artifact: TranslationArtifact) => {
    if (!runId) return;
    setPreviewError(null);
    try {
      const url = await fetchTranslationArtifactBlobUrl(runId, artifact.name);
      setPreview((prev) => {
        if (prev) URL.revokeObjectURL(prev.url);
        return { name: artifact.name, url };
      });
    } catch (caught) {
      setPreviewError(errText(caught, "That artifact could not be previewed."));
    }
  };

  /* ---- derived view model ---- */

  const stages: TranslationStage[] = serverRun?.stages?.length ? serverRun.stages : TRANSLATE_STAGES;
  const live = runId ? progress[runId] : undefined;
  const terminal = serverRun != null && !isActive(serverRun);

  const stageIndex = (() => {
    if (!serverRun) return -1;
    if (serverRun.state === "done") return stages.length;
    if (live?.stage) {
      const found = stages.findIndex((stage) => stage.name === live.stage);
      if (found >= 0) return found;
    }
    return serverRun.stage_index;
  })();

  const stageCurrent = live?.stage_current ?? serverRun?.stage_current ?? 0;
  const stageTotal = live?.stage_total ?? serverRun?.stage_total ?? 0;
  const stageFrac = (() => {
    if (serverRun?.state === "done") return 1;
    const explicit = live?.stage_progress ?? serverRun?.stage_progress;
    if (typeof explicit === "number" && explicit > 0) return Math.min(1, explicit / 100);
    if (stageTotal > 0) return Math.min(1, stageCurrent / stageTotal);
    return 0;
  })();

  const overall = (() => {
    if (serverRun?.state === "done") return 100;
    if (!serverRun) return 0;
    const fromEvents = live?.overall_progress;
    return Math.max(0, Math.min(100, fromEvents ?? serverRun.overall_progress ?? 0));
  })();

  const fracs = stages.map((_, index) => (index < stageIndex ? 1 : index === stageIndex ? stageFrac : 0));
  const currentStageName = stageIndex >= 0 && stageIndex < stages.length ? stages[stageIndex].name : null;
  const runFeed = runId ? feed[runId] ?? [] : [];
  const artifacts = serverRun?.artifacts ?? [];
  const bundleDir = serverRun?.bundle_dir || focusedDoc?.bundle_dir || (focusedDoc ? bundleDirFor(focusedDoc.source_path) : "");

  const runLabel = serverRun
    ? `${STATE_LABEL[serverRun.state]} · ${overall.toFixed(0)}% overall${currentStageName ? ` · ${shortStage(currentStageName)}` : ""}`
    : "No run yet";

  /* ---- render ---- */

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-paper" data-testid="translation-view">
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto hairline-scroll">
        <div className="mx-auto w-full max-w-[1480px] px-5 py-6 sm:px-7 sm:py-8">
          <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-0">
              <h1 className="editorial-heading text-[26px] font-medium leading-[1.1] tracking-[-0.04em]">
                Document translation
              </h1>
              <p className="mt-1.5 text-[13px] leading-[1.5] text-muted">
                BabelDOC runs locally · source and translations are bundled beside the original file
              </p>
            </div>
            <div className="flex items-center gap-2">
              {langPair && <Pill tone="neutral">{langPair}</Pill>}
              {onOpenSettings && (
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-muted transition-colors hover:bg-panel hover:text-ink"
                  onClick={onOpenSettings}
                >
                  <Icon name="gear" size={13} /> Options
                </button>
              )}
            </div>
          </header>

          <p className="sr-only" role="status" aria-live="polite">
            {error ? error : status || runLabel}
          </p>

          {error && (
            <div
              className="mb-4 flex items-start gap-2 rounded-xl2 border border-line bg-dangerSoft px-3 py-2.5 text-[12px] text-danger"
              role="alert"
            >
              <Icon name="shield" size={14} className="mt-0.5 shrink-0" />
              <span className="min-w-0 flex-1">{error}</span>
              <button type="button" className="shrink-0 text-[11px] underline" onClick={() => setError(null)}>
                Dismiss
              </button>
            </div>
          )}

          <div className="grid min-h-0 grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(260px,300px)_minmax(0,1fr)_minmax(280px,340px)]">
            {/* ---------------------------------------------------------- queue */}
            <section className="flex min-w-0 flex-col" aria-label="Document queue">
              <ColumnHead
                title="Queue"
                icon="library"
                right={<Pill tone="neutral">{documents.length}</Pill>}
              />

              <div
                className={
                  "flex flex-col items-center gap-1.5 rounded-xl2 border border-dashed px-3 py-5 text-center transition-colors duration-200 " +
                  (dragOver ? "border-accent bg-accentSoft" : "border-lineStrong bg-panel/40")
                }
                role="button"
                tabIndex={0}
                aria-label="Add PDF documents: drop files here, or activate to choose files"
                onClick={() => fileInput.current?.click()}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    fileInput.current?.click();
                  }
                }}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragOver(false);
                  void registerFiles(Array.from(event.dataTransfer?.files ?? []));
                }}
              >
                <Icon name="folderPlus" size={20} className="text-muted" />
                <strong className="text-[12.5px] font-medium text-ink">Drop PDFs, or click to choose</strong>
                <small className="text-[11px] leading-[1.45] text-muted">
                  Outputs stay next to each source file
                </small>
              </div>
              <input
                ref={fileInput}
                type="file"
                accept="application/pdf,.pdf"
                multiple
                className="sr-only"
                aria-label="Choose PDF documents"
                onChange={(event) => {
                  void registerFiles(Array.from(event.target.files ?? []));
                  event.target.value = "";
                }}
              />

              <div className="mt-2 flex items-center gap-1.5">
                <input
                  className="min-w-0 flex-1 rounded-lg border border-line bg-panel px-2 py-1.5 font-mono text-[11px] text-ink placeholder:text-faint focus:border-accent focus:outline-none"
                  placeholder="/absolute/path/paper.pdf"
                  aria-label="Register a local document by absolute path"
                  value={pathDraft}
                  onChange={(event) => setPathDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void registerPaths();
                  }}
                />
                <button
                  type="button"
                  className="shrink-0 rounded-lg border border-line px-2 py-1.5 text-[11px] text-muted transition-colors hover:bg-panel hover:text-ink disabled:opacity-40"
                  disabled={!pathDraft.trim() || busy === "register"}
                  onClick={() => void registerPaths()}
                >
                  Add path
                </button>
              </div>

              <div className="mt-3 flex flex-col gap-1.5">
                {loading ? (
                  <p className="px-1 text-[12px] text-muted">Loading the queue…</p>
                ) : documents.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-line px-3 py-4 text-center text-[11.5px] leading-[1.5] text-muted">
                    No documents yet. Drop a PDF above, or paste a path that already lives on this machine.
                  </p>
                ) : (
                  documents.map((doc) => {
                    const docRun = runsByDoc.get(doc.document_id) ?? null;
                    const focused = focusedDoc?.document_id === doc.document_id;
                    const pct = docRun
                      ? docRun.state === "done"
                        ? 100
                        : progress[docRun.run_id]?.overall_progress ?? docRun.overall_progress
                      : null;
                    return (
                      <div
                        key={doc.document_id}
                        className={
                          "flex items-center gap-2 rounded-lg border px-2 py-2 transition-colors " +
                          (focused ? "border-accent bg-accentSoft/40" : "border-line bg-panel hover:bg-paper")
                        }
                      >
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 shrink-0 accent-accent"
                          aria-label={`Include ${doc.filename} in the next run`}
                          checked={checked.includes(doc.document_id)}
                          onChange={(event) =>
                            setChecked((prev) =>
                              event.target.checked
                                ? [...new Set([...prev, doc.document_id])]
                                : prev.filter((id) => id !== doc.document_id),
                            )
                          }
                        />
                        <button
                          type="button"
                          className="flex min-w-0 flex-1 items-center gap-2 text-left"
                          aria-current={focused}
                          onClick={() => setFocusedDocId(doc.document_id)}
                        >
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[12.5px] font-medium text-ink" title={doc.filename}>
                              {doc.filename}
                            </span>
                            <span className="mt-0.5 block truncate font-mono text-[10.5px] text-muted" title={doc.source_path}>
                              {dirOf(doc.source_path)}
                            </span>
                          </span>
                          {docRun ? (
                            docRun.state === "running" || docRun.state === "queued" ? (
                              <span className="shrink-0 font-mono text-[11px] tabular-nums text-accent">
                                {(pct ?? 0).toFixed(0)}%
                              </span>
                            ) : (
                              <Pill tone={stateTone(docRun.state)}>{STATE_LABEL[docRun.state]}</Pill>
                            )
                          ) : (
                            <Pill tone="neutral">Ready</Pill>
                          )}
                        </button>
                      </div>
                    );
                  })
                )}
              </div>

              {/* The Run column already owns the primary call to action for the focused document, so this
                  one only claims accent weight when it does something that card cannot: start a batch. */}
              {documents.length > 0 && (
                <button
                  type="button"
                  className={
                    checked.length > 1
                      ? "mt-3 inline-flex items-center justify-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-[12.5px] font-medium text-onSolid transition-opacity duration-200 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                      : "mt-3 inline-flex items-center justify-center gap-1.5 rounded-lg border border-line px-3 py-2 text-[12.5px] font-medium text-ink transition-colors duration-200 hover:bg-panel disabled:cursor-not-allowed disabled:opacity-40"
                  }
                  disabled={busy === "start" || (checked.length === 0 && !focusedDoc)}
                  onClick={() => void start(checked.length ? checked : focusedDoc ? [focusedDoc.document_id] : [])}
                >
                  <Icon name="sparkle" size={14} />
                  {busy === "start"
                    ? "Starting…"
                    : checked.length > 1
                      ? `Translate ${checked.length} documents`
                      : "Translate"}
                </button>
              )}
            </section>

            {/* ---------------------------------------------------------- live run */}
            <section className="flex min-w-0 flex-col" aria-label="Current run">
              <ColumnHead
                title="Run"
                icon="sparkle"
                right={serverRun && <Pill tone={stateTone(serverRun.state)}>{STATE_LABEL[serverRun.state]}</Pill>}
              />

              {!focusedDoc ? (
                <div className={`${CARD} flex flex-col items-center gap-2 px-6 py-14 text-center`}>
                  <Icon name="file" size={24} className="text-faint" />
                  <p className="text-[12.5px] text-muted">Add a document to start a translation run.</p>
                </div>
              ) : (
                <>
                  <div className={`${CARD} p-4`}>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div
                          className="text-[10px] font-semibold uppercase tracking-[0.09em] text-muted"
                          data-testid="translation-run-phase"
                        >
                          {serverRun
                            ? serverRun.state === "done"
                              ? "Complete"
                              : serverRun.state === "error"
                                ? "Failed"
                                : serverRun.state === "cancelled"
                                  ? "Cancelled"
                                  : `Stage ${Math.max(0, stageIndex) + 1} of ${stages.length}`
                            : "Ready"}
                        </div>
                        <h3 className="mt-1 truncate text-[17px] font-medium tracking-[-0.02em] text-ink" title={focusedDoc.filename}>
                          {focusedDoc.filename}
                        </h3>
                        <p className="mt-1 text-[11.5px] text-muted">
                          {focusedDoc.pages != null && <span className="font-mono tabular-nums">{focusedDoc.pages} pages · </span>}
                          <span className="font-mono tabular-nums">{formatBytes(focusedDoc.size)}</span>
                          {serverRun && ` · ${serverRun.lang_in} → ${serverRun.lang_out}`}
                        </p>
                      </div>
                      <div className="text-right">
                        <div className="font-mono text-[28px] font-medium leading-none tabular-nums tracking-[-0.03em] text-ink">
                          {overall.toFixed(0)}
                          <span className="text-[15px] font-normal text-muted">%</span>
                        </div>
                        <div className="mt-1 text-[11px] text-muted">
                          {serverRun ? formatDuration(serverRun.elapsed_seconds) : "not started"}
                        </div>
                      </div>
                    </div>

                    <div className="mt-3.5">
                      <ProgressBar
                        pct={overall}
                        label={`Overall translation progress for ${focusedDoc.filename}`}
                        valueText={
                          currentStageName
                            ? `${overall.toFixed(0)} percent · ${shortStage(currentStageName)}`
                            : `${overall.toFixed(0)} percent`
                        }
                        tone={serverRun?.state === "error" ? "danger" : serverRun?.state === "done" ? "ok" : "accent"}
                      />
                      <div className="mt-2">
                        <WeightedTrack stages={stages} fracs={fracs} />
                      </div>
                      <p className="mt-2 text-[11px] text-muted">
                        Segment width is BabelDOC's own stage weight
                        {stageTotal > 0 && serverRun?.state === "running" && (
                          <>
                            {" · "}
                            <span className="font-mono tabular-nums text-ink">
                              {stageCurrent}/{stageTotal}
                            </span>{" "}
                            in {currentStageName ? shortStage(currentStageName) : "stage"}
                          </>
                        )}
                      </p>
                    </div>

                    <div className="mt-3.5 flex flex-wrap items-center gap-2">
                      {runActive ? (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-ink transition-colors hover:bg-paper disabled:opacity-40"
                          disabled={busy === "cancel"}
                          onClick={() => serverRun && void cancel(serverRun.run_id)}
                        >
                          <Icon name="x" size={13} /> Cancel run
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-2.5 py-1.5 text-[12px] font-medium text-onSolid transition-opacity duration-200 hover:opacity-90 disabled:opacity-40"
                          disabled={busy === "start"}
                          onClick={() => void start([focusedDoc.document_id])}
                        >
                          <Icon name="sparkle" size={13} /> {terminal ? "Run again" : "Run translation"}
                        </button>
                      )}
                      {serverRun?.state === "error" && serverRun.error && (
                        <span className="min-w-0 flex-1 truncate text-[11.5px] text-danger" title={serverRun.error}>
                          {serverRun.error}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className={`${CARD} mt-3 p-4`}>
                    <div className="mb-2.5 flex items-center gap-2">
                      <h4 className="text-[12.5px] font-semibold text-ink">Stages</h4>
                      <Pill tone="neutral">{stages.length}</Pill>
                    </div>
                    <ol className="flex flex-col">
                      {stages.map((stage, index) => {
                        const done = index < stageIndex;
                        const active = index === stageIndex && runActive;
                        return (
                          <li
                            key={`${stage.name}-${index}`}
                            className={
                              "flex items-start gap-2.5 rounded-lg px-1.5 py-1.5 " +
                              (active ? "bg-accentSoft/50" : "")
                            }
                          >
                            <span
                              className={
                                "mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border font-mono text-[9px] tabular-nums " +
                                (done
                                  ? "border-okLine bg-okSoft text-ok"
                                  : active
                                    ? "border-accent text-accent"
                                    : "border-line text-faint")
                              }
                            >
                              {done ? <Icon name="sparkle" size={8} /> : index + 1}
                            </span>
                            <span className="min-w-0 flex-1">
                              <span
                                className={
                                  "block truncate text-[12px] " +
                                  (done ? "text-muted" : active ? "font-medium text-ink" : "text-muted")
                                }
                                title={stage.name}
                              >
                                {shortStage(stage.name)}
                              </span>
                              {active && (
                                <span className="mt-1 block">
                                  <ProgressBar
                                    pct={stageFrac * 100}
                                    label={`${shortStage(stage.name)} progress`}
                                    valueText={
                                      stageTotal > 0
                                        ? `${stageCurrent} of ${stageTotal}`
                                        : `${(stageFrac * 100).toFixed(0)} percent`
                                    }
                                  />
                                  {stageTotal > 0 && (
                                    <span className="mt-1 block font-mono text-[10.5px] tabular-nums text-muted">
                                      {stageCurrent}/{stageTotal}
                                    </span>
                                  )}
                                </span>
                              )}
                            </span>
                            <span className="shrink-0 font-mono text-[10.5px] tabular-nums text-faint">
                              {stage.weight.toFixed(1)}
                            </span>
                          </li>
                        );
                      })}
                    </ol>
                  </div>

                  <div className={`${CARD} mt-3 p-4`}>
                    <div className="mb-2 flex items-center gap-2">
                      <h4 className="text-[12.5px] font-semibold text-ink">Events</h4>
                      <Pill tone="neutral">{runFeed.length}</Pill>
                      <button
                        type="button"
                        className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-line px-2 py-1 text-[11px] text-muted transition-colors hover:bg-paper hover:text-ink"
                        aria-expanded={logOpen}
                        onClick={() => setLogOpen((prev) => !prev)}
                      >
                        <Icon name={logOpen ? "chevronDown" : "chevronRight"} size={12} /> Raw log
                      </button>
                    </div>
                    {runFeed.length === 0 ? (
                      <p className="text-[11.5px] text-muted">
                        {serverRun ? "Waiting for the first event…" : "Events appear once a run starts."}
                      </p>
                    ) : (
                      <div className="flex max-h-[190px] flex-col gap-0.5 overflow-y-auto hairline-scroll">
                        {[...runFeed].reverse().map((line) => (
                          <div key={line.seq} className="flex items-baseline gap-2 font-mono text-[11px] leading-[1.5]">
                            <span className="shrink-0 tabular-nums text-faint">{clockOf(line.at)}</span>
                            <span
                              className={
                                "w-[68px] shrink-0 truncate " +
                                (line.type === "error" ? "text-danger" : line.type === "finish" ? "text-ok" : "text-muted")
                              }
                            >
                              {line.type}
                            </span>
                            <span className="min-w-0 flex-1 truncate text-ink" title={line.text}>
                              {line.text}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                    {logOpen && (
                      <pre
                        className="mt-2 max-h-[170px] overflow-auto rounded-lg border border-line bg-paper p-2 font-mono text-[10.5px] leading-[1.5] text-muted"
                        data-testid="translation-raw-log"
                      >
                        {log.length ? log.join("\n") : "No raw output yet."}
                      </pre>
                    )}
                  </div>
                </>
              )}
            </section>

            {/* ---------------------------------------------------------- artifacts */}
            <section className="flex min-w-0 flex-col" aria-label="Artifacts">
              <ColumnHead
                title="Artifacts"
                icon="folder"
                right={artifacts.length > 0 && <Pill tone="ok">{artifacts.length}</Pill>}
              />

              {!focusedDoc ? (
                <div className={`${CARD} px-4 py-10 text-center text-[12px] text-muted`}>
                  Nothing to collect yet.
                </div>
              ) : (
                <>
                  {bundleDir && (
                    <BundlePath path={bundleDir} pending={serverRun?.state !== "done"} onCopy={copyPath} />
                  )}

                  {artifacts.length === 0 ? (
                    <p className="mt-3 rounded-lg border border-dashed border-line px-3 py-4 text-[11.5px] leading-[1.5] text-muted">
                      {serverRun?.state === "error"
                        ? "The run failed before writing artifacts."
                        : serverRun?.state === "cancelled"
                          ? "Cancelled before any artifact was written."
                          : runActive
                            ? "Translated documents appear here as soon as the run finishes."
                            : "Run the translation to produce the bilingual, translated-only, and glossary files."}
                    </p>
                  ) : (
                    <div className="mt-3 flex flex-col gap-1.5">
                      {artifacts.map((artifact) => (
                        <div
                          key={artifact.name}
                          className={`${CARD} flex items-center gap-2 p-2`}
                          data-testid={`translation-artifact-${artifact.role}`}
                        >
                          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-paper text-muted">
                            <Icon name={artifact.role === "glossary" ? "table" : artifact.role === "log" ? "fileCode" : "file"} size={13} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[12px] font-medium text-ink" title={artifact.name}>
                              {artifact.name}
                            </span>
                            <span className="mt-0.5 block truncate text-[10.5px] text-muted">
                              {ARTIFACT_ROLE_LABEL[artifact.role] ?? artifact.role} ·{" "}
                              <span className="font-mono tabular-nums">{formatBytes(artifact.size)}</span>
                            </span>
                          </span>
                          {/\.pdf$/i.test(artifact.name) && (
                            <button
                              type="button"
                              className="shrink-0 rounded-lg border border-line px-2 py-1 text-[11px] text-muted transition-colors hover:bg-paper hover:text-ink"
                              onClick={() => void openPreview(artifact)}
                            >
                              Preview
                            </button>
                          )}
                          {runId && (
                            <a
                              className="shrink-0 rounded-lg border border-line px-2 py-1 text-[11px] text-muted transition-colors hover:bg-paper hover:text-ink"
                              href={translationArtifactUrl(runId, artifact.name)}
                              download={artifact.name}
                            >
                              Download
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {previewError && (
                    <p className="mt-2 text-[11px] text-danger" role="alert">
                      {previewError}
                    </p>
                  )}

                  {preview && (
                    <div className={`${CARD} mt-3 overflow-hidden`}>
                      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
                        <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink" title={preview.name}>
                          {preview.name}
                        </span>
                        <button
                          type="button"
                          className="shrink-0 rounded-lg border border-line px-1.5 py-0.5 text-[11px] text-muted transition-colors hover:bg-paper hover:text-ink"
                          aria-label="Close preview"
                          onClick={() =>
                            setPreview((prev) => {
                              if (prev) URL.revokeObjectURL(prev.url);
                              return null;
                            })
                          }
                        >
                          <Icon name="x" size={12} />
                        </button>
                      </div>
                      <object
                        data={preview.url}
                        type="application/pdf"
                        aria-label={`Preview of ${preview.name}`}
                        className="block h-[360px] w-full bg-paper"
                        data-testid="translation-artifact-preview"
                      >
                        <p className="p-3 text-[11.5px] text-muted">
                          This PDF cannot be shown inline. Use Download instead.
                        </p>
                      </object>
                    </div>
                  )}

                  {serverRun?.state === "done" && (
                    <p className="mt-3 text-[11px] leading-[1.5] text-faint">
                      The original document moved in beside its translations, so the pair never drifts apart on disk.
                    </p>
                  )}
                </>
              )}
            </section>
          </div>
        </div>
      </div>
    </main>
  );
}

/* ------------------------------------------------------------------ helpers */

function describeEvent(event: TranslationRunEvent): string {
  const stage = typeof event.stage === "string" && event.stage ? shortStage(event.stage) : null;
  if (typeof event.message === "string" && event.message) return stage ? `${stage} · ${event.message}` : event.message;
  if (event.type === "progress_end" && stage) {
    const overall = typeof event.overall_progress === "number" ? ` · ${event.overall_progress.toFixed(1)}% overall` : "";
    return `${stage} complete${overall}`;
  }
  if (stage) {
    const counts =
      typeof event.stage_current === "number" && typeof event.stage_total === "number"
        ? ` ${event.stage_current}/${event.stage_total}`
        : "";
    return `${stage}${counts}`;
  }
  return event.type;
}

function clockOf(at: number): string {
  const ms = at > 1e11 ? at : at * 1000;
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString([], { hour12: false });
}

/** base64 of a picked file, via FileReader's data URL (no new dependency, works in the webview). */
function readBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`${file.name} could not be read.`));
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}
