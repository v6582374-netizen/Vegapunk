import { useEffect, useRef, useState } from "react";
import {
  convertDiscoveryPreparation,
  deleteDiscoverySource,
  getDiscovery,
  intakeDiscoveryPreparation,
  saveDiscoveryPreparation,
  saveDiscoveryRevision,
  type DiscoveryContext,
  type DiscoveryContextId,
  type DiscoveryConversionState,
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

type Busy = "intake" | "save" | "delete" | "convert" | "revision" | null;

const EMPTY_CONVERSION: DiscoveryConversionState = {
  status: "pending",
  draft: "",
  model_id: null,
  error: null,
  saved_revision_id: null,
  base_fingerprint: null,
  current_fingerprint: "",
};

const CONVERSION_STATUSES = ["pending", "editing", "saved", "dirty", "failed"] as const;

function normalizePreparation(raw: DiscoveryPreparation | { status?: string }): DiscoveryPreparation {
  const candidate = raw as Partial<DiscoveryPreparation>;
  const conversion = candidate.conversion as Partial<DiscoveryConversionState> | undefined;
  const status = CONVERSION_STATUSES.includes(conversion?.status as (typeof CONVERSION_STATUSES)[number])
    ? (conversion?.status as DiscoveryConversionState["status"])
    : EMPTY_CONVERSION.status;
  return {
    status:
      candidate.status === "draft" || candidate.status === "saved" ? candidate.status : "empty",
    dirty: candidate.dirty ?? false,
    draft: candidate.draft ?? EMPTY_CONTENT,
    saved: candidate.saved ?? EMPTY_CONTENT,
    revisions: Array.isArray(candidate.revisions) ? candidate.revisions : [],
    conversion: {
      ...EMPTY_CONVERSION,
      ...conversion,
      status,
    },
  };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The Discovery sidecar rejected this change.";
}

function hasPreparationInput(content: DiscoveryPreparationContent): boolean {
  return Boolean(content.text.trim() || content.sources.length);
}

function isCommittedPreparation(preparation: DiscoveryPreparation): boolean {
  return preparation.status === "saved" && !preparation.dirty && hasPreparationInput(preparation.draft);
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
  const savedRevision = preparation.conversion.saved_revision_id
    ? preparation.revisions.find(
        (revision) => revision.revision_id === preparation.conversion.saved_revision_id,
      )
    : null;
  let conversion = preparation.conversion;
  if (dirty) {
    conversion = { ...conversion, status: "dirty", error: null };
  } else if (
    conversion.status === "dirty" &&
    savedRevision?.eligible &&
    conversion.draft === savedRevision.formatted_input
  ) {
    conversion = { ...conversion, status: "saved", error: null };
  } else if (conversion.status === "dirty" && !conversion.draft) {
    conversion = { ...conversion, status: "pending", error: null };
  }
  return {
    ...snapshot,
    preparation: { ...preparation, status, dirty, draft, conversion },
  };
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

function StageCanvas({ preparation }: { preparation: DiscoveryPreparation }) {
  const preparationSaved = isCommittedPreparation(preparation);
  const conversionReady =
    Boolean(preparation.conversion.draft.trim()) && preparation.conversion.status !== "failed";
  const revisionSaved =
    preparationSaved &&
    preparation.conversion.status === "saved" &&
    preparation.revisions.some(
      (revision) =>
        revision.revision_id === preparation.conversion.saved_revision_id && revision.eligible,
    );
  const activeStage = revisionSaved ? 4 : conversionReady ? 3 : preparationSaved ? 2 : 1;
  const completed = [preparationSaved, conversionReady, revisionSaved, false];

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
  preparation,
  busy,
  error,
  onConvert,
  onDraftChange,
  onSaveRevision,
}: {
  preparation: DiscoveryPreparation;
  busy: Busy;
  error: string | null;
  onConvert: () => void;
  onDraftChange: (value: string) => void;
  onSaveRevision: () => void;
}) {
  const preparationSaved = isCommittedPreparation(preparation);
  const conversion = preparation.conversion;
  const hasDraft = Boolean(conversion.draft.trim());
  const latestRevision = conversion.saved_revision_id
    ? preparation.revisions.find((revision) => revision.revision_id === conversion.saved_revision_id)
    : null;
  const canSaveRevision =
    preparationSaved &&
    hasDraft &&
    conversion.status !== "saved" &&
    conversion.status !== "pending" &&
    busy === null;
  const convertLabel =
    busy === "convert"
      ? "Converting..."
      : conversion.status === "failed"
        ? "Try again"
        : hasDraft
          ? "Re-convert"
          : "Convert";
  const statusLabel = {
    pending: preparationSaved ? "Ready to convert" : "Waiting for Preparation",
    editing: "Draft ready for review",
    saved: "Revision saved",
    dirty: preparationSaved ? "Unsaved review changes" : "Preparation changed",
    failed: "Conversion failed",
  }[conversion.status];

  return (
    <section className={CARD + " overflow-hidden"} aria-labelledby="discovery-review-heading">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
        <div>
          <h3 id="discovery-review-heading" className="text-[13px] font-semibold text-ink">
            Reviewable input
          </h3>
          <p className="mt-0.5 text-[11px] text-faint">
            {preparationSaved
              ? "Convert once, review the Markdown, then save an immutable revision."
              : "Save the Preparation first to unlock later stages."}
          </p>
        </div>
        <button
          type="button"
          className="discovery-button discovery-button-small discovery-button-primary"
          disabled={!preparationSaved || busy !== null}
          onClick={onConvert}
        >
          {convertLabel}
        </button>
      </div>
      <div className="space-y-4 p-4 sm:p-5">
        <div
          className="discovery-notice"
          data-testid="conversion-status"
          aria-live="polite"
          role={conversion.status === "failed" ? "alert" : "status"}
        >
          <span aria-hidden="true">{conversion.status === "failed" ? "!" : "→"}</span>
          <span>
            <strong>{statusLabel}</strong>
            {conversion.status === "pending" &&
              (preparationSaved
                ? "The committed source bundle is ready for the global default model."
                : "Save the whole Preparation before later stages can use these inputs.")}
            {conversion.status === "editing" &&
              "This draft is local until you explicitly save a Formatted Discovery Input revision."}
            {conversion.status === "saved" &&
              `Revision ${latestRevision ? latestRevision.revision_id.slice(0, 8) : "current"} is immutable and eligible for the next Run frontier.`}
            {conversion.status === "dirty" &&
              (preparationSaved
                ? "Review edits are not saved yet. Save a new revision to make Run eligible."
                : "Save the changed Preparation, then convert it again before reviewing.")}
            {conversion.status === "failed" &&
              (conversion.error ?? "The default model did not produce a Formatted Discovery Input.")}
          </span>
        </div>

        {hasDraft && (
          <label className="block">
            <span className="discovery-section-label">Formatted Discovery Input</span>
            <textarea
              className="discovery-text-input mt-2 min-h-[210px] font-mono text-[12px]"
              aria-label="Formatted Discovery Input"
              value={conversion.draft}
              onChange={(event) => onDraftChange(event.target.value)}
              disabled={busy !== null}
            />
            <span className="mt-1.5 block text-[11px] text-faint">
              Markdown remains editable. Saving appends a new revision and never overwrites history.
            </span>
          </label>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-[11px] text-muted">
            {preparation.revisions.length
              ? `${preparation.revisions.length} saved revision${preparation.revisions.length === 1 ? "" : "s"}`
              : "No saved revisions yet"}
          </span>
          <button
            type="button"
            className="discovery-button discovery-button-small"
            disabled={!canSaveRevision}
            onClick={onSaveRevision}
          >
            {busy === "revision" ? "Saving revision..." : "Save revision"}
          </button>
        </div>

        {error && (
          <p className="rounded-lg border border-danger/30 bg-dangerSoft px-3 py-2.5 text-[12px] text-danger" role="alert">
            {error}
          </p>
        )}

        {preparation.revisions.length > 0 && (
          <div className="border-t border-line pt-3" aria-label="Saved Formatted Discovery Input revisions">
            <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-faint">
              Revision history
            </div>
            <ul className="mt-2 space-y-1.5">
              {preparation.revisions.map((revision) => (
                <li
                  key={revision.revision_id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-line bg-paper px-3 py-2 text-[11px]"
                >
                  <span className="min-w-0 truncate text-muted">
                    {revision.revision_id.slice(0, 8)} · {new Date(revision.created_at).toLocaleString()}
                  </span>
                  <span className={revision.eligible && !preparation.dirty ? "text-ok" : "text-faint"}>
                    {revision.eligible && !preparation.dirty ? "Eligible" : "Stale"}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
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
  reviewError,
  onTextChange,
  onFiles,
  onSave,
  onDelete,
  onConvert,
  onDraftChange,
  onSaveRevision,
}: {
  preparation: DiscoveryPreparation;
  text: string;
  resetNotice: boolean;
  busy: Busy;
  error: string | null;
  reviewError: string | null;
  onTextChange: (value: string) => void;
  onFiles: (files: File[]) => void;
  onSave: () => void;
  onDelete: (source: DiscoverySourceEntry) => void;
  onConvert: () => void;
  onDraftChange: (value: string) => void;
  onSaveRevision: () => void;
}) {
  const preparationSaved = isCommittedPreparation(preparation);

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
          <span className={`discovery-status-dot ${preparationSaved ? "is-ready" : "is-warn"}`} />
          {preparationSaved ? "Preparation committed" : "Preparation in progress"}
        </span>
      </div>

      <div className="discovery-canvas-stack">
        <StageCanvas
          preparation={preparation}
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
          preparation={preparation}
          busy={busy}
          error={reviewError}
          onConvert={onConvert}
          onDraftChange={onDraftChange}
          onSaveRevision={onSaveRevision}
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
  const [resetNotice, setResetNotice] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
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

  function setDraftText(value: string) {
    setText(value);
    setResetNotice(false);
    setMutationError(null);
    setReviewError(null);
    setSnapshot((current) => (current ? withDraftText(current, value) : current));
  }

  function setConversionDraft(value: string) {
    setMutationError(null);
    setReviewError(null);
    setSnapshot((current) => {
      if (!current) return current;
      const preparation = normalizePreparation(current.preparation);
      const conversion = preparation.conversion;
      const savedRevision = conversion.saved_revision_id
        ? preparation.revisions.find(
            (revision) => revision.revision_id === conversion.saved_revision_id,
          )
        : null;
      const status =
        !preparation.dirty && value.trim() && savedRevision?.formatted_input === value
          ? "saved"
          : "dirty";
      return {
        ...current,
        preparation: {
          ...preparation,
          conversion: {
            ...conversion,
            draft: value,
            status,
            error: null,
          },
        },
      };
    });
  }

  async function addFiles(files: File[]) {
    if (!snapshot) return;
    setMutationError(null);
    setReviewError(null);
    setResetNotice(false);
    setBusy("intake");
    try {
      const next = await intakeDiscoveryPreparation(text, files);
      setSnapshot(next);
      setText(normalizePreparation(next.preparation).draft.text);
    } catch (caught) {
      setMutationError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  async function savePreparation() {
    setMutationError(null);
    setReviewError(null);
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
    setReviewError(null);
    setBusy("delete");
    setResetNotice(false);
    try {
      const next = await deleteDiscoverySource(source.source_id);
      setSnapshot(withDraftText(next, text));
      setText(text);
    } catch (caught) {
      setMutationError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  async function convertPreparation() {
    setMutationError(null);
    setReviewError(null);
    setBusy("convert");
    try {
      const next = await convertDiscoveryPreparation();
      setSnapshot(next);
    } catch (caught) {
      setReviewError(null);
      setSnapshot((current) => {
        if (!current) return current;
        const preparation = normalizePreparation(current.preparation);
        return {
          ...current,
          preparation: {
            ...preparation,
            conversion: {
              ...preparation.conversion,
              status: "failed",
              error: errorMessage(caught),
            },
          },
        };
      });
    } finally {
      setBusy(null);
    }
  }

  async function saveRevision() {
    if (!preparation) return;
    const formattedInput = preparation.conversion.draft;
    if (!formattedInput.trim()) return;
    setMutationError(null);
    setReviewError(null);
    setBusy("revision");
    try {
      const next = await saveDiscoveryRevision(formattedInput);
      setSnapshot(next);
    } catch (caught) {
      setReviewError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
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
                {error ? "Sidecar reconnect needed" : loading ? "Loading" : preparation?.status === "draft" ? "Draft" : "Ready"}
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
                  reviewError={reviewError}
                  onTextChange={setDraftText}
                  onFiles={addFiles}
                  onSave={savePreparation}
                  onDelete={removeSource}
                  onConvert={convertPreparation}
                  onDraftChange={setConversionDraft}
                  onSaveRevision={saveRevision}
                />
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
