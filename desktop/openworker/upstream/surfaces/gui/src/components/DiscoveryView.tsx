import { useEffect, useRef, useState } from "react";
import {
  deleteDiscoverySource,
  getDiscovery,
  intakeDiscoveryPreparation,
  saveDiscoveryPreparation,
  type DiscoveryContext,
  type DiscoveryContextId,
  type DiscoveryPreparation,
  type DiscoveryPreparationContent,
  type DiscoverySnapshot,
  type DiscoverySourceEntry,
} from "../api";
import { Icon } from "./Icon";

const FALLBACK_CONTEXTS: DiscoveryContext[] = [
  {
    id: "preparation",
    label: "Preparation",
    description: "Gather and review research inputs before a launch.",
  },
  {
    id: "launch",
    label: "Current Launch",
    description: "Observe the active Discovery launch.",
  },
  {
    id: "history",
    label: "History",
    description: "Review completed and interrupted Discovery launches.",
  },
];

const CARD = "rounded-xl2 border border-line bg-panel";
const EMPTY_CONTENT: DiscoveryPreparationContent = { text: "", sources: [] };
const STAGES = [
  ["Gather", "Files and text"],
  ["Convert", "Explicit model action"],
  ["Review", "Edit and save"],
  ["Run", "Immutable Launch snapshot"],
] as const;

type Busy = "intake" | "save" | "delete" | null;

function normalizePreparation(raw: DiscoveryPreparation | { status?: string }): DiscoveryPreparation {
  const candidate = raw as Partial<DiscoveryPreparation>;
  return {
    status:
      candidate.status === "draft" || candidate.status === "saved" ? candidate.status : "empty",
    dirty: candidate.dirty ?? false,
    draft: candidate.draft ?? EMPTY_CONTENT,
    saved: candidate.saved ?? EMPTY_CONTENT,
  };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The Discovery sidecar rejected this change.";
}

function hasPreparationInput(content: DiscoveryPreparationContent): boolean {
  return Boolean(content.text.trim() || content.sources.length);
}

function withDraftText(snapshot: DiscoverySnapshot, text: string): DiscoverySnapshot {
  const preparation = normalizePreparation(snapshot.preparation);
  const draft = { ...preparation.draft, text };
  const dirty =
    draft.text !== preparation.saved.text ||
    JSON.stringify(draft.sources) !== JSON.stringify(preparation.saved.sources);
  const status = dirty
    ? "draft"
    : hasPreparationInput(draft)
      ? "saved"
      : "empty";
  return {
    ...snapshot,
    preparation: { ...preparation, status, dirty, draft },
  };
}

function formattedValue(text: string, sources: DiscoverySourceEntry[]): string {
  return [
    "# Discovery Input",
    "",
    "## Research question",
    text || "Add a research question in the source text area.",
    "",
    "## Source material",
    ...sources.map((source) => `- ${source.filename}`),
    "",
    "## Expected evidence",
    "Define the comparison, measurable outcome, and evidence required for a useful result.",
  ].join("\n");
}

function EmptyContext({ context }: { context: DiscoveryContextId }) {
  if (context === "preparation") return null;

  if (context === "launch") {
    return (
      <section className={CARD + " p-5 sm:p-6"} aria-labelledby="discovery-launch-heading">
        <div className="flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-paper text-muted">
            <Icon name="clock" size={17} />
          </span>
          <div>
            <h2 id="discovery-launch-heading" className="text-[15px] font-semibold text-ink">
              No current Launch
            </h2>
            <p className="mt-1.5 text-[13px] leading-relaxed text-muted">
              A confirmed Discovery run will appear here with its live state and controls.
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className={CARD + " p-5 sm:p-6"} aria-labelledby="discovery-history-heading">
      <div className="flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-paper text-muted">
          <Icon name="library" size={17} />
        </span>
        <div>
          <h2 id="discovery-history-heading" className="text-[15px] font-semibold text-ink">
            No Launch history yet
          </h2>
          <p className="mt-1.5 text-[13px] leading-relaxed text-muted">
            Completed, stopped, or interrupted Discovery launches will stay available here as
            read-only records.
          </p>
        </div>
      </div>
    </section>
  );
}

function StageCanvas({
  preparation,
  converted,
  revisionSaved,
  launched,
}: {
  preparation: DiscoveryPreparation;
  converted: boolean;
  revisionSaved: boolean;
  launched: boolean;
}) {
  const hasInput = hasPreparationInput(preparation.draft);
  const activeStage = launched ? 4 : revisionSaved ? 4 : converted ? 3 : hasInput ? 2 : 1;
  const completed = [hasInput, converted, revisionSaved, launched];

  return (
    <div className="discovery-stage-bar" aria-label="Preparation stages" role="list">
      {STAGES.map(([stage, description], index) => {
        const stageNumber = index + 1;
        return (
          <div
            key={stage}
            className={`discovery-stage ${activeStage >= stageNumber ? "is-active" : ""}`}
            role="listitem"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-extrabold tracking-[0.08em] text-faint">
                0{stageNumber}
              </span>
              {completed[index] && (
                <span className="discovery-stage-complete" aria-label="Completed">
                  ✓
                </span>
              )}
            </div>
            <strong className="mt-1 block text-[12px] font-semibold text-ink">{stage}</strong>
            <small className="mt-0.5 block text-[10.5px] text-muted">{description}</small>
          </div>
        );
      })}
    </div>
  );
}

function SourceStrip({
  sources,
  busy,
  onDelete,
}: {
  sources: DiscoverySourceEntry[];
  busy: boolean;
  onDelete: (source: DiscoverySourceEntry) => void;
}) {
  if (!sources.length) {
    return <span className="text-[11px] text-faint">No files yet.</span>;
  }

  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Accepted Source Entries">
      {sources.map((source) => (
        <li key={source.source_id}>
          <span className="inline-flex min-h-7 items-center gap-1.5 rounded-full border border-line bg-panel px-2.5 text-[11px] text-muted">
            <span className="font-semibold text-faint">{source.extension.replace(".", "").toUpperCase()}</span>
            <span className="max-w-[220px] truncate">{source.filename}</span>
            <button
              type="button"
              className="text-[16px] leading-none text-faint transition-colors hover:text-danger disabled:cursor-wait disabled:opacity-50"
              aria-label={`Remove ${source.filename}`}
              disabled={busy}
              onClick={() => onDelete(source)}
            >
              ×
            </button>
          </span>
        </li>
      ))}
    </ul>
  );
}

function GatherContext({
  preparation,
  text,
  resetNotice,
  busy,
  error,
  onTextChange,
  onFiles,
  onSave,
  onDelete,
}: {
  preparation: DiscoveryPreparation;
  text: string;
  resetNotice: boolean;
  busy: Busy;
  error: string | null;
  onTextChange: (value: string) => void;
  onFiles: (files: File[]) => void;
  onSave: () => void;
  onDelete: (source: DiscoverySourceEntry) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const isEmpty = !hasPreparationInput(preparation.draft);

  function handleFiles(files: File[]) {
    if (files.length) onFiles(files);
  }

  return (
    <section className={CARD + " overflow-hidden"} aria-labelledby="discovery-gather-heading">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
        <div>
          <h3 id="discovery-gather-heading" className="text-[13px] font-semibold text-ink">
            Gather context
          </h3>
          <p className="mt-0.5 text-[11px] text-faint">
            Drop files individually. Folders are intentionally absent.
          </p>
        </div>
        <button
          type="button"
          className="discovery-button discovery-button-small"
          onClick={() => inputRef.current?.click()}
          disabled={busy !== null}
        >
          + Add file
        </button>
      </div>

      <div className="grid gap-4 p-4 sm:p-5 lg:grid-cols-[minmax(0,1.12fr)_minmax(280px,0.88fr)]">
        <div>
          <div
            className="discovery-drop-zone"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              handleFiles(Array.from(event.dataTransfer.files));
            }}
          >
            <div>
              <div className="discovery-drop-icon">⇧</div>
              <strong className="block text-[13px] text-ink">Choose individual files</strong>
              <p className="mx-auto mt-1 max-w-[320px] text-[11px] text-muted">
                .txt, .md, .pdf, .docx, .csv, and .zip are accepted. Add as many as this
                Preparation needs.
              </p>
              <div className="mt-3 flex flex-wrap justify-center gap-2">
                <button
                  type="button"
                  className="discovery-button discovery-button-small"
                  onClick={() => inputRef.current?.click()}
                  disabled={busy !== null}
                >
                  Choose files
                </button>
                <span className="discovery-button discovery-button-small discovery-button-ghost">
                  Individual files only
                </span>
              </div>
            </div>
          </div>
          <input
            ref={inputRef}
            className="sr-only"
            type="file"
            multiple
            accept=".txt,.md,.pdf,.docx,.csv,.zip"
            aria-label="Source files"
            disabled={busy !== null}
            onChange={(event) => {
              handleFiles(Array.from(event.target.files ?? []));
              event.target.value = "";
            }}
          />
          <div className="mt-3">
            <SourceStrip sources={preparation.draft.sources} busy={busy !== null} onDelete={onDelete} />
          </div>
        </div>

        <label className="block">
          <span className="discovery-section-label">Free-form text</span>
          <textarea
            className="discovery-text-input mt-2 min-h-[142px]"
            aria-label="Research text"
            placeholder="Describe the research question, context, or constraints."
            value={text}
            onChange={(event) => onTextChange(event.target.value)}
          />
          <span className="mt-1.5 block text-[11px] text-faint">
            Free-form text stays separate from uploaded file entries.
          </span>
        </label>
      </div>

      {error && (
        <p className="mx-4 mb-4 rounded-lg border border-danger/30 bg-dangerSoft px-3 py-2.5 text-[12px] text-danger sm:mx-5" role="alert">
          {error}
        </p>
      )}
      {preparation.dirty && hasPreparationInput(preparation.saved) && (
        <p className="mx-4 mb-3 text-[11px] text-muted sm:mx-5">
          Saved Preparation remains unchanged until Save.
        </p>
      )}
      <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-2.5 text-[11px] sm:px-5">
        <span className="text-muted" aria-live="polite">
          {busy === "intake"
            ? "Adding Source Entries..."
            : busy === "delete"
              ? "Removing Source Entry..."
              : busy === "save"
                ? "Saving Preparation..."
                : resetNotice
                  ? "Preparation reset"
                  : preparation.dirty
                    ? "Draft changes not saved"
                    : isEmpty
                      ? "Empty Preparation - add text or one source to begin"
                      : "Preparation saved"}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-faint">{preparation.draft.sources.length} files</span>
          <button
            type="button"
            className="discovery-button discovery-button-small"
            disabled={!preparation.dirty || busy !== null}
            onClick={onSave}
          >
            Save Preparation
          </button>
        </div>
      </div>
    </section>
  );
}

function ReviewableInput({
  converted,
  formatted,
  canConvert,
  onConvert,
  onFormattedChange,
}: {
  converted: boolean;
  formatted: string;
  canConvert: boolean;
  onConvert: () => void;
  onFormattedChange: (value: string) => void;
}) {
  return (
    <section className={CARD + " overflow-hidden"} aria-labelledby="discovery-review-heading">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
        <div>
          <h3 id="discovery-review-heading" className="text-[13px] font-semibold text-ink">
            Reviewable input
          </h3>
          <p className="mt-0.5 text-[11px] text-faint">
            {converted ? "Edit the formatted revision before saving it." : "Convert to reveal the editable revision."}
          </p>
        </div>
        <button
          type="button"
          className="discovery-button discovery-button-small discovery-button-primary"
          disabled={!canConvert}
          onClick={onConvert}
        >
          {converted ? "Convert again" : "Convert"}
        </button>
      </div>
      <div className="p-4 sm:p-5">
        {converted ? (
          <textarea
            className="discovery-formatted-input"
            aria-label="Formatted Discovery Input"
            value={formatted}
            onChange={(event) => onFormattedChange(event.target.value)}
          />
        ) : (
          <div className="discovery-notice">
            <span aria-hidden="true">→</span>
            <span>
              <strong>Conversion is a boundary</strong>
              Source changes never start a Launch. The formatted draft appears after explicit
              conversion.
            </span>
          </div>
        )}
      </div>
    </section>
  );
}

function RunGate({
  converted,
  revisionSaved,
  canRun,
  launched,
  onSaveRevision,
  onRun,
}: {
  converted: boolean;
  revisionSaved: boolean;
  canRun: boolean;
  launched: boolean;
  onSaveRevision: () => void;
  onRun: () => void;
}) {
  return (
    <section className="discovery-footer-gate" aria-label="Run gate">
      <div>
        <strong className="block text-[12px] font-semibold text-ink">
          {launched ? "Launch started" : revisionSaved ? "Preparation is ready" : "Run remains gated"}
        </strong>
        <span className="mt-0.5 block text-[11px] text-muted">
          {launched
            ? "Launch started from the saved Preparation revision. Later edits do not change this snapshot."
            : revisionSaved
              ? "The next Launch will snapshot this saved revision."
              : "Convert, review, and save before the Launch action unlocks."}
        </span>
      </div>
      <div className="discovery-footer-gate-actions">
        <button
          type="button"
          className="discovery-button"
          disabled={!converted || launched}
          onClick={onSaveRevision}
        >
          {revisionSaved ? "Revision saved" : "Save revision"}
        </button>
        <button
          type="button"
          className="discovery-button discovery-button-primary"
          disabled={!canRun || launched}
          onClick={onRun}
        >
          {launched ? "Launch started" : "Run Discovery"}
        </button>
      </div>
    </section>
  );
}

function PreparationCanvas({
  preparation,
  text,
  resetNotice,
  busy,
  error,
  converted,
  formatted,
  revisionSaved,
  launched,
  onTextChange,
  onFiles,
  onSave,
  onDelete,
  onConvert,
  onFormattedChange,
  onSaveRevision,
  onRun,
}: {
  preparation: DiscoveryPreparation;
  text: string;
  resetNotice: boolean;
  busy: Busy;
  error: string | null;
  converted: boolean;
  formatted: string;
  revisionSaved: boolean;
  launched: boolean;
  onTextChange: (value: string) => void;
  onFiles: (files: File[]) => void;
  onSave: () => void;
  onDelete: (source: DiscoverySourceEntry) => void;
  onConvert: () => void;
  onFormattedChange: (value: string) => void;
  onSaveRevision: () => void;
  onRun: () => void;
}) {
  const hasInput = hasPreparationInput(preparation.draft);
  const sourceReady = hasInput && !error;
  const canRun = sourceReady && converted && revisionSaved;

  return (
    <>
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-faint">
            Preparation / stage canvas
          </div>
          <h2 className="mt-1 text-[24px] font-semibold tracking-[-0.04em] text-ink">
            Move one Preparation through four deliberate stages.
          </h2>
          <p className="mt-1 max-w-2xl text-[13px] text-muted">
            A persistent stage bar makes the conversion boundary and the final Run action
            impossible to mistake.
          </p>
        </div>
        <span className="discovery-status-pill shrink-0">
          <span className={`discovery-status-dot ${canRun ? "is-ready" : "is-warn"}`} />
          {canRun ? "Ready to run" : "Preparation in progress"}
        </span>
      </div>

      <div className="discovery-canvas-stack">
        <StageCanvas
          preparation={preparation}
          converted={converted}
          revisionSaved={revisionSaved}
          launched={launched}
        />
        <GatherContext
          preparation={preparation}
          text={text}
          resetNotice={resetNotice}
          busy={busy}
          error={error}
          onTextChange={onTextChange}
          onFiles={onFiles}
          onSave={onSave}
          onDelete={onDelete}
        />
        <ReviewableInput
          converted={converted}
          formatted={formatted}
          canConvert={sourceReady}
          onConvert={onConvert}
          onFormattedChange={onFormattedChange}
        />
        <RunGate
          converted={converted}
          revisionSaved={revisionSaved}
          canRun={canRun}
          launched={launched}
          onSaveRevision={onSaveRevision}
          onRun={onRun}
        />
      </div>
    </>
  );
}

function ErrorContext() {
  return (
    <section
      className={CARD + " p-5 sm:p-6"}
      aria-labelledby="discovery-error-heading"
      role="alert"
    >
      <div className="flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-paper text-muted">
          <Icon name="refresh" size={17} />
        </span>
        <div>
          <h2 id="discovery-error-heading" className="text-[15px] font-semibold text-ink">
            Discovery is unavailable
          </h2>
          <p className="mt-1.5 text-[13px] leading-relaxed text-muted">
            The sidecar did not return the Discovery state. Reconnect it and try again.
          </p>
        </div>
      </div>
    </section>
  );
}

function LoadingContext() {
  return (
    <section
      className={CARD + " p-5 sm:p-6"}
      aria-labelledby="discovery-loading-heading"
      aria-busy="true"
    >
      <h2 id="discovery-loading-heading" className="text-[15px] font-semibold text-ink">
        Loading Discovery
      </h2>
      <p className="mt-1.5 text-[13px] leading-relaxed text-muted">
        Checking the sidecar for the current Preparation and Launch state.
      </p>
    </section>
  );
}

export function DiscoveryView() {
  const [snapshot, setSnapshot] = useState<DiscoverySnapshot | null>(null);
  const [context, setContext] = useState<DiscoveryContextId>("preparation");
  const [text, setText] = useState("");
  const [converted, setConverted] = useState(false);
  const [formatted, setFormatted] = useState("");
  const [revisionSaved, setRevisionSaved] = useState(false);
  const [launched, setLaunched] = useState(false);
  const [lastAction, setLastAction] = useState("");
  const [resetNotice, setResetNotice] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Busy>(null);

  useEffect(() => {
    let alive = true;
    getDiscovery()
      .then((next) => {
        if (!alive) return;
        setSnapshot(next);
        setText(normalizePreparation(next.preparation).draft.text);
        setResetNotice(false);
        setContext(next.active_context);
      })
      .catch(() => {
        if (alive) setError("Discovery is unavailable. Try again when the sidecar is ready.");
      });
    return () => {
      alive = false;
    };
  }, []);

  const contexts = snapshot?.contexts?.length ? snapshot.contexts : FALLBACK_CONTEXTS;
  const activeContext = contexts.find((item) => item.id === context) ?? contexts[0];
  const preparation = snapshot ? normalizePreparation(snapshot.preparation) : null;
  const loading = snapshot === null && error === null;

  function resetReviewState() {
    setConverted(false);
    setFormatted("");
    setRevisionSaved(false);
    setLaunched(false);
    setLastAction("");
  }

  function setDraftText(value: string) {
    setText(value);
    setResetNotice(false);
    setMutationError(null);
    resetReviewState();
    setSnapshot((current) => (current ? withDraftText(current, value) : current));
  }

  async function addFiles(files: File[]) {
    if (!snapshot) return;
    setMutationError(null);
    setResetNotice(false);
    setLastAction("");
    setBusy("intake");
    try {
      const next = await intakeDiscoveryPreparation(text, files);
      setSnapshot(next);
      setText(normalizePreparation(next.preparation).draft.text);
      resetReviewState();
    } catch (caught) {
      setMutationError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  async function savePreparation() {
    setMutationError(null);
    setBusy("save");
    try {
      const previous = snapshot ? normalizePreparation(snapshot.preparation) : null;
      const next = await saveDiscoveryPreparation(text);
      setSnapshot(next);
      setText(normalizePreparation(next.preparation).draft.text);
      setResetNotice(
        next.preparation.status === "empty" &&
          Boolean(
            previous &&
              (hasPreparationInput(previous.saved) || hasPreparationInput(previous.draft)),
          ),
      );
    } catch (caught) {
      setMutationError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  async function removeSource(source: DiscoverySourceEntry) {
    setMutationError(null);
    setBusy("delete");
    setResetNotice(false);
    setLastAction("");
    try {
      const next = await deleteDiscoverySource(source.source_id);
      setSnapshot(withDraftText(next, text));
      setText(text);
      resetReviewState();
    } catch (caught) {
      setMutationError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  function convertInput() {
    if (!preparation || !hasPreparationInput(preparation.draft) || mutationError) return;
    setFormatted(formattedValue(text, preparation.draft.sources));
    setConverted(true);
    setRevisionSaved(false);
    setLaunched(false);
    setLastAction("Conversion completed. Review the formatted draft before saving.");
  }

  function saveRevision() {
    if (!converted) return;
    setRevisionSaved(true);
    setLastAction("Formatted input revision saved. Run is now eligible.");
  }

  function runDiscovery() {
    if (!preparation || !converted || !revisionSaved || mutationError) return;
    setLaunched(true);
    setLastAction(
      "Launch started from the saved Preparation revision. Later edits will not change this snapshot.",
    );
  }

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-paper" data-testid="discovery-view">
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto hairline-scroll">
        <div className="mx-auto w-full max-w-[1420px] px-5 py-6 sm:px-7 sm:py-8">
          <header className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-faint">
                <Icon name="library" size={14} /> Native module
              </div>
              <h1 className="mt-2 text-[26px] font-semibold tracking-[-0.02em] text-ink">Discovery</h1>
              <p className="mt-1.5 max-w-2xl text-[13.5px] leading-relaxed text-muted">
                One home for preparing, running, and reviewing long-running research.
              </p>
            </div>
            <div className="rounded-lg border border-line bg-panel px-3 py-2 text-right" aria-label="Discovery status">
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-faint">Status</div>
              <div className="mt-0.5 text-[12.5px] font-medium text-ink">
                {error ? "Sidecar reconnect needed" : loading ? "Loading" : launched ? "Launch started" : preparation?.status === "draft" ? "Draft" : "Ready"}
              </div>
            </div>
          </header>

          <nav className="mt-7 border-b border-line" aria-label="Discovery sections" role="tablist">
            <div className="flex min-w-0 gap-1 overflow-x-auto">
              {contexts.map((item) => {
                const selected = item.id === activeContext.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    id={`discovery-tab-${item.id}`}
                    aria-controls={`discovery-panel-${item.id}`}
                    className={
                      "shrink-0 border-b-2 px-3 py-2.5 text-[13px] font-medium transition-colors " +
                      (selected
                        ? "border-accent text-ink"
                        : "border-transparent text-muted hover:border-lineStrong hover:text-ink")
                    }
                    onClick={() => setContext(item.id)}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </nav>

          <div
            className="mt-5"
            role="tabpanel"
            id={`discovery-panel-${activeContext.id}`}
            aria-labelledby={`discovery-tab-${activeContext.id}`}
          >
            {loading ? (
              <LoadingContext />
            ) : error ? (
              <ErrorContext />
            ) : activeContext.id === "preparation" && preparation ? (
              <>
                <PreparationCanvas
                  preparation={preparation}
                  text={text}
                  resetNotice={resetNotice}
                  busy={busy}
                  error={mutationError}
                  converted={converted}
                  formatted={formatted}
                  revisionSaved={revisionSaved}
                  launched={launched}
                  onTextChange={setDraftText}
                  onFiles={addFiles}
                  onSave={savePreparation}
                  onDelete={removeSource}
                  onConvert={convertInput}
                  onFormattedChange={(value) => {
                    setFormatted(value);
                    setRevisionSaved(false);
                    setLaunched(false);
                  }}
                  onSaveRevision={saveRevision}
                  onRun={runDiscovery}
                />
                {lastAction && (
                  <div className="discovery-notice mt-3" role="status">
                    <span aria-hidden="true">i</span>
                    <span>{lastAction}</span>
                  </div>
                )}
              </>
            ) : (
              <EmptyContext context={activeContext.id} />
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
