import { useEffect, useState } from "react";
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

function EmptyContext({ context }: { context: DiscoveryContextId }) {
  if (context === "preparation") {
    return null;
  }

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
  const gatherState = preparation.dirty
    ? "Draft"
    : preparation.status === "saved"
      ? "Saved"
      : "Not started";
  const stages = [
    ["Gather", gatherState],
    ["Convert", "Not started"],
    ["Review", "Not started"],
    ["Run", "Not started"],
  ];
  return (
    <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4" aria-label="Preparation stages">
      {stages.map(([stage, state]) => (
        <div key={stage} className="rounded-lg border border-line bg-paper px-3 py-2.5">
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-faint">Stage</div>
          <div className="mt-1 text-[13px] font-medium text-ink">{stage}</div>
          <div className="mt-0.5 text-[11.5px] text-faint">{state}</div>
        </div>
      ))}
    </div>
  );
}

function SourceEntryList({
  sources,
  busy,
  onDelete,
}: {
  sources: DiscoverySourceEntry[];
  busy: boolean;
  onDelete: (source: DiscoverySourceEntry) => void;
}) {
  if (!sources.length) {
    return <p className="text-[12.5px] text-muted">No Source Entries yet.</p>;
  }
  return (
    <ul className="space-y-2" aria-label="Accepted Source Entries">
      {sources.map((source) => (
        <li
          key={source.source_id}
          className="flex items-center justify-between gap-3 rounded-lg border border-line bg-paper px-3 py-2.5"
        >
          <div className="min-w-0">
            <div className="truncate text-[13px] font-medium text-ink">{source.filename}</div>
            <div className="mt-0.5 text-[11.5px] text-faint">
              {source.extension} - {source.size} bytes
            </div>
          </div>
          <button
            type="button"
            className="shrink-0 rounded-md px-2 py-1 text-[12px] font-medium text-muted hover:bg-panel hover:text-ink disabled:cursor-wait disabled:opacity-50"
            aria-label={`Remove ${source.filename}`}
            disabled={busy}
            onClick={() => onDelete(source)}
          >
            Remove
          </button>
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
  busy: "intake" | "save" | "delete" | null;
  error: string | null;
  onTextChange: (value: string) => void;
  onFiles: (files: File[]) => void;
  onSave: () => void;
  onDelete: (source: DiscoverySourceEntry) => void;
}) {
  const isEmpty = !hasPreparationInput(preparation.draft);
  const saveEnabled = preparation.dirty || text !== preparation.saved.text;
  const heading = preparation.dirty
    ? "Preparation draft"
    : resetNotice
      ? "Preparation reset"
      : isEmpty
        ? "Your first Preparation is empty"
        : "Preparation saved";
  const description = preparation.dirty
    ? "Review the accepted Source Entries and research text. Changes remain a Draft until you save them."
    : resetNotice
      ? "The committed Preparation is empty again. Add new research text or source files to begin another one."
    : "Add research text or individual source files here, then save the whole Preparation before conversion.";

  return (
    <section className={CARD + " p-5 sm:p-6"} aria-labelledby="discovery-preparation-heading">
      <div className="flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-paper text-muted">
          <Icon name="file" size={17} />
        </span>
        <div className="min-w-0">
          <h2 id="discovery-preparation-heading" className="text-[15px] font-semibold text-ink">
            {heading}
          </h2>
          <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-muted">{description}</p>
        </div>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)]">
        <label className="block">
          <span className="text-[12px] font-semibold uppercase tracking-[0.08em] text-faint">
            Research text
          </span>
          <textarea
            className="mt-2 min-h-36 w-full resize-y rounded-lg border border-line bg-paper px-3 py-2.5 text-[13px] leading-relaxed text-ink outline-none transition-colors placeholder:text-faint focus:border-lineStrong"
            aria-label="Research text"
            placeholder="Describe the research question, context, or constraints."
            value={text}
            onChange={(event) => onTextChange(event.target.value)}
          />
        </label>

        <div>
          <label className="block">
            <span className="text-[12px] font-semibold uppercase tracking-[0.08em] text-faint">
              Source files
            </span>
            <input
              className="mt-2 block w-full rounded-lg border border-dashed border-lineStrong bg-paper px-3 py-3 text-[12.5px] text-muted file:mr-3 file:rounded-md file:border-0 file:bg-panel file:px-2.5 file:py-1.5 file:text-[12px] file:font-medium file:text-ink"
              type="file"
              multiple
              accept=".txt,.md,.pdf,.docx,.csv,.zip"
              aria-label="Source files"
              disabled={busy !== null}
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                if (files.length) onFiles(files);
                event.target.value = "";
              }}
            />
          </label>
          <p className="mt-2 text-[11.5px] leading-relaxed text-faint">
            Individual .txt, .md, .pdf, .docx, .csv, or .zip files only. Folders are not accepted.
          </p>
        </div>
      </div>

      <div className="mt-5 border-t border-line pt-4">
        <div className="mb-2 flex items-center justify-between gap-3">
          <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-faint">
            Accepted Source Entries
          </h3>
          <span className="text-[11.5px] text-faint">{preparation.draft.sources.length} files</span>
        </div>
        <SourceEntryList sources={preparation.draft.sources} busy={busy !== null} onDelete={onDelete} />
      </div>

      {preparation.dirty && preparation.saved.sources.length > 0 && (
        <p className="mt-3 text-[12px] text-muted">
          Saved Preparation remains unchanged until Save.
        </p>
      )}
      {error && (
        <p className="mt-3 rounded-lg border border-line bg-paper px-3 py-2.5 text-[12.5px] text-ink" role="alert">
          {error}
        </p>
      )}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <span className="text-[12px] text-muted" aria-live="polite">
          {busy === "intake" ? "Adding Source Entries..." : busy === "delete" ? "Removing Source Entry..." : busy === "save" ? "Saving Preparation..." : preparation.dirty ? "Draft changes not saved" : "Preparation saved"}
        </span>
        <button
          type="button"
          className="rounded-lg bg-ink px-3.5 py-2 text-[12.5px] font-semibold text-panel transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          disabled={!saveEnabled || busy !== null}
          onClick={onSave}
        >
          Save Preparation
        </button>
      </div>
    </section>
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
  const [busy, setBusy] = useState<"intake" | "save" | "delete" | null>(null);

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
    setSnapshot((current) => (current ? withDraftText(current, value) : current));
  }

  async function addFiles(files: File[]) {
    if (!snapshot) return;
    setMutationError(null);
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

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-paper" data-testid="discovery-view">
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto hairline-scroll">
        <div className="mx-auto w-full max-w-5xl px-5 py-6 sm:px-7 sm:py-8">
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
            <div className="mb-3">
              <h2 className="text-[13px] font-semibold text-ink">{activeContext.label}</h2>
              <p className="mt-0.5 text-[12.5px] text-muted">{activeContext.description}</p>
            </div>
            {loading ? (
              <LoadingContext />
            ) : error ? (
              <ErrorContext />
            ) : activeContext.id === "preparation" && preparation ? (
              <>
                <GatherContext
                  preparation={preparation}
                  text={text}
                  resetNotice={resetNotice}
                  busy={busy}
                  error={mutationError}
                  onTextChange={setDraftText}
                  onFiles={addFiles}
                  onSave={savePreparation}
                  onDelete={removeSource}
                />
                <StageCanvas preparation={preparation} />
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
