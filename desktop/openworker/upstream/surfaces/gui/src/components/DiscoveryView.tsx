import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  convertDiscoveryPreparation,
  createDiscoveryIdempotencyKey,
  deleteDiscoverySource,
  getDiscovery,
  getDiscoveryConversionPrompt,
  getDiscoveryLaunchEvents,
  getDiscoveryLaunchStatus,
  intakeDiscoveryPreparation,
  resetDiscoveryPreparation,
  resumeDiscoveryLaunch,
  saveDiscoveryPreparation,
  saveDiscoveryConversionPrompt,
  saveDiscoveryRevision,
  startDiscoveryLaunch,
  stopDiscoveryLaunch,
  streamDiscoveryLaunchLog,
  type DiscoveryContext,
  type DiscoveryContextId,
  type DiscoveryActivityStream,
  type DiscoveryConversionPrompt,
  type DiscoveryConversionState,
  type DiscoveryExecutionInput,
  type DiscoveryLaunchEvent,
  type DiscoveryLaunch,
  type DiscoveryLaunchStatus,
  type DiscoveryPreparation,
  type DiscoveryPreparationContent,
  type DiscoveryProgressTimeline,
  type DiscoverySnapshot,
  type DiscoveryTimelineMilestone,
  type DiscoverySourceEntry,
} from "../api";
import { Icon } from "./Icon";
import { DiscoveryArtifactPanel } from "./DiscoveryArtifacts";

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

type Busy =
  | "intake"
  | "save"
  | "delete"
  | "reset"
  | "convert"
  | "prompt"
  | "revision"
  | "launch"
  | "stop"
  | "resume"
  | null;

const EMPTY_CONVERSION: DiscoveryConversionState = {
  status: "pending",
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
      execution_input: normalizeExecutionInput(conversion?.execution_input),
    },
  };
}

function normalizeExecutionInput(raw: unknown): DiscoveryExecutionInput | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const candidate = raw as Partial<DiscoveryExecutionInput>;
  const constraints = Array.isArray(candidate.constraints)
    ? candidate.constraints.map((item) => String(item ?? "").trim()).filter(Boolean)
    : [];
  return {
    task_description: String(candidate.task_description ?? ""),
    domain: String(candidate.domain ?? ""),
    background: String(candidate.background ?? ""),
    constraints,
  };
}

function executionInputEqual(left: DiscoveryExecutionInput | undefined, right: DiscoveryExecutionInput | undefined): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function emptyProgressTimeline(): DiscoveryProgressTimeline {
  return {
    revision: 0,
    percent: 0,
    current_milestone_id: null,
    milestones: [],
  };
}

function emptyActivityStream(): DiscoveryActivityStream {
  return {
    oldest_sequence: null,
    newest_sequence: null,
    truncated_before_sequence: 0,
    items: [],
  };
}

function normalizeTimeline(raw: Partial<DiscoveryProgressTimeline> | undefined): DiscoveryProgressTimeline {
  if (!raw || !Array.isArray(raw.milestones)) return emptyProgressTimeline();
  const milestones: DiscoveryTimelineMilestone[] = raw.milestones.map((milestone, index) => ({
    id: milestone.id ?? `milestone-${index + 1}`,
    key: milestone.key ?? milestone.id ?? `milestone-${index + 1}`,
    label: milestone.label ?? milestone.key ?? `Milestone ${index + 1}`,
    position: milestone.position ?? index + 1,
    state: milestone.state ?? "pending",
    summary: milestone.summary ?? null,
    started_at: milestone.started_at ?? null,
    ended_at: milestone.ended_at ?? null,
    attempts: Array.isArray(milestone.attempts) ? milestone.attempts : [],
  }));
  return {
    revision: raw.revision ?? 0,
    percent: raw.percent ?? 0,
    current_milestone_id: raw.current_milestone_id ?? null,
    milestones,
  };
}

function normalizeActivity(raw: Partial<DiscoveryActivityStream> | undefined): DiscoveryActivityStream {
  if (!raw || !Array.isArray(raw.items)) return emptyActivityStream();
  return {
    oldest_sequence: raw.oldest_sequence ?? null,
    newest_sequence: raw.newest_sequence ?? null,
    truncated_before_sequence: raw.truncated_before_sequence ?? 0,
    items: raw.items,
  };
}

function normalizeLaunchStatus(raw: DiscoveryLaunchStatus | DiscoverySnapshot): DiscoveryLaunchStatus | null {
  const candidate = raw as Partial<DiscoveryLaunchStatus> & Partial<DiscoverySnapshot>;
  const launch = candidate.launch ?? candidate.current_launch;
  if (!launch) return null;
  return {
    launch,
    state: candidate.state ?? launch.state,
    stage: candidate.stage ?? launch.stage,
    round: candidate.round ?? launch.round,
    checkpoint: candidate.checkpoint ?? launch.checkpoint ?? null,
    timeline: normalizeTimeline(candidate.timeline),
    activity: normalizeActivity(candidate.activity),
    allowed_actions: Array.isArray(candidate.allowed_actions) ? candidate.allowed_actions : [],
    produced_outputs: Array.isArray(candidate.produced_outputs) ? candidate.produced_outputs : [],
    latest_event_sequence: candidate.latest_event_sequence ?? 0,
  };
}

function applyLaunchEvents(
  status: DiscoveryLaunchStatus,
  events: DiscoveryLaunchEvent[],
): DiscoveryLaunchStatus {
  return events.reduce((current, event) => {
    const data = event.data;
    if (event.type === "work.state.updated") {
      const state = typeof data.state === "string" ? data.state : current.state;
      const stage = typeof data.stage === "string" ? data.stage : current.stage;
      const round = typeof data.round === "number" ? data.round : current.round;
      return {
        ...current,
        state: state as DiscoveryLaunchStatus["state"],
        stage,
        round,
        launch: { ...current.launch, state: state as DiscoveryLaunch["state"], stage, round },
      };
    }
    if (event.type === "progress.milestone.updated" && data.timeline) {
      return {
        ...current,
        timeline: normalizeTimeline(data.timeline as Partial<DiscoveryProgressTimeline>),
      };
    }
    return current;
  }, status);
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
    savedRevision.execution_input &&
    executionInputEqual(
      conversion.execution_input,
      savedRevision.execution_input,
    )
  ) {
    conversion = { ...conversion, status: "saved", error: null };
  } else if (
    conversion.status === "dirty" &&
    !conversion.execution_input
  ) {
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

function prototypeLaunchShortId(launch: DiscoveryLaunch): string {
  return launch.launch_id.slice(0, 12);
}

function prototypeLaunchTitle(launch: DiscoveryLaunch): string {
  const researchText = launch.input_snapshot?.research_text;
  if (typeof researchText === "string" && researchText.trim()) {
    const firstLine = researchText.trim().split("\n")[0];
    return firstLine.length <= 54 ? firstLine : `${firstLine.slice(0, 51)}...`;
  }
  return `Discovery Launch ${prototypeLaunchShortId(launch)}`;
}

function prototypeLaunchIsActive(launch: DiscoveryLaunch): boolean {
  return launch.state === "starting" || launch.state === "running" || launch.state === "stopping";
}

function PrototypeStatusPill({ state }: { state: DiscoveryLaunch["state"] }) {
  const live = state === "starting" || state === "running" || state === "stopping";
  const stateClass =
    state === "completed"
      ? "is-ready"
      : state === "failed"
        ? "is-danger"
        : live ? "is-live" : "is-warn";
  return (
    <span className="discovery-status-pill">
      <span className={`discovery-status-dot ${stateClass}`} />
      {state.charAt(0).toUpperCase() + state.slice(1)}
    </span>
  );
}

function PrototypeLaunchAction({
  launch,
  busy,
  onStop,
  onResume,
}: {
  launch: DiscoveryLaunch;
  busy: Busy;
  onStop?: () => void;
  onResume?: () => void;
}) {
  const resumable = (launch.state === "stopped" || launch.state === "interrupted") && launch.resumable;
  if (prototypeLaunchIsActive(launch) && onStop) {
    return (
      <button
        type="button"
        className="discovery-button discovery-button-small"
        disabled={busy === "stop" || launch.state === "stopping"}
        onClick={onStop}
      >
        {launch.state === "stopping" || busy === "stop" ? "Stopping..." : "Stop"}
      </button>
    );
  }
  if (resumable && onResume) {
    return (
      <button
        type="button"
        className="discovery-button discovery-button-small discovery-button-primary"
        disabled={busy === "resume"}
        onClick={onResume}
      >
        {busy === "resume" ? "Resuming..." : "Resume"}
      </button>
    );
  }
  return null;
}

function PrototypeHistoryRunItem({
  launch,
  selected,
  onSelect,
}: {
  launch: DiscoveryLaunch;
  selected: boolean;
  onSelect: () => void;
}) {
  const title = prototypeLaunchTitle(launch);
  const indexTitle = title.startsWith("Discovery Launch ")
    ? title.slice("Discovery Launch ".length)
    : title;
  const meta = prototypeLaunchIsActive(launch)
    ? `${prototypeLaunchShortId(launch)} · ${launch.stage}`
    : `${prototypeLaunchShortId(launch)} · ${launch.state === "failed" ? "stopped" : launch.state}`;
  return (
    <button
      type="button"
      className={`discovery-history-item ${selected ? "is-selected" : ""}`}
      aria-label={`Select ${prototypeLaunchTitle(launch)}`}
      aria-current={selected ? "true" : undefined}
      onClick={onSelect}
    >
      <span className="discovery-history-item-top">
        <span className="discovery-history-item-title">{indexTitle}</span>
        <span className={`discovery-history-status discovery-history-status-${launch.state}`}>
          <span className="discovery-history-status-dot" />
          {launch.state.charAt(0).toUpperCase() + launch.state.slice(1)}
        </span>
      </span>
      <span className="discovery-history-item-meta">{meta}</span>
    </button>
  );
}

function PrototypeLaunchDetailHeader({
  launch,
  selectedIsActive,
  busy,
  onStop,
  onResume,
}: {
  launch: DiscoveryLaunch;
  selectedIsActive: boolean;
  busy: Busy;
  onStop?: () => void;
  onResume?: () => void;
}) {
  return (
    <section className="discovery-prototype-panel discovery-detail-header" aria-label="Selected Discovery Launch">
      <div>
        <h2 className="discovery-launch-title">{prototypeLaunchTitle(launch)}</h2>
        <div className="discovery-launch-meta">
          {prototypeLaunchShortId(launch)} · <span>{launch.state}</span>
          {selectedIsActive ? ` · ${launch.stage}` : ""}
        </div>
      </div>
      <div className="discovery-detail-header-actions">
        <PrototypeStatusPill state={launch.state} />
        <PrototypeLaunchAction launch={launch} busy={busy} onStop={onStop} onResume={onResume} />
      </div>
    </section>
  );
}

function prototypeActivityTime(value: string | undefined, sequence: number): string {
  const match = value?.match(/T(\d{2}:\d{2})/);
  return match?.[1] ?? String(sequence).padStart(2, "0");
}

function PrototypeRuntimeDesk({
  status,
  busy,
  historyMode = false,
  rawOpen,
  rawLines,
  rawError,
  onToggleRaw,
  onStop,
  onResume,
}: {
  status: DiscoveryLaunchStatus | null;
  busy: Busy;
  historyMode?: boolean;
  rawOpen: boolean;
  rawLines: string[];
  rawError: string | null;
  onToggleRaw: () => void;
  onStop?: () => void;
  onResume?: () => void;
}) {
  if (!status) {
    return (
      <section className="discovery-prototype-panel p-5" aria-label="Runtime Desk" aria-busy="true">
        <h2 className="text-[15px] font-semibold text-ink">Runtime Desk</h2>
        <p className="mt-1.5 text-[12px] text-muted">Loading the server-authoritative Launch status.</p>
      </section>
    );
  }
  const canStop = status.allowed_actions.includes("stop") && Boolean(onStop);
  const canResume = status.allowed_actions.includes("resume") && Boolean(onResume);
  return (
    <div className="discovery-runtime-desk" aria-label="Runtime Desk" data-testid="runtime-desk">
      <section className="discovery-prototype-panel" aria-label={historyMode ? "Lifecycle" : "Launch timeline"}>
        <div className="discovery-prototype-panel-head">
          <h3>{historyMode ? "Lifecycle" : "Launch timeline"}</h3>
          <span>
            {historyMode
              ? status.state === "completed" || status.state === "failed" || status.state === "stopped"
                ? "Archived observation"
                : "Live observation"
              : "Start-time snapshot · immutable for this Launch"}
          </span>
        </div>
        <div className="discovery-timeline" aria-label="Research Progress Timeline">
          {status.timeline.milestones.map((milestone) => {
            const done = milestone.state === "completed";
            const active = !done && (milestone.id === status.timeline.current_milestone_id || milestone.state === "active" || milestone.state === "running");
            return (
              <div key={milestone.id} className={`discovery-timeline-row ${done ? "done" : active ? "active" : "pending"}`}>
                <span className="discovery-timeline-node" />
                <span className="discovery-timeline-step">{String(milestone.position).padStart(2, "0")}</span>
                <div className="discovery-timeline-detail">
                  <strong>{milestone.label}</strong>
                  <span>{milestone.summary ?? (done ? "Completed" : active ? "In progress" : "Awaiting start")}</span>
                </div>
                <span className="discovery-timeline-state">{done ? "Done" : active ? "Live" : "Next"}</span>
              </div>
            );
          })}
        </div>
      </section>

      <section className="discovery-prototype-panel" aria-label="Runtime output">
        <div className="discovery-prototype-panel-head">
          <div>
            <h3>Runtime output</h3>
            <span>
              {historyMode
                ? status.state === "completed" || status.state === "failed" || status.state === "stopped"
                  ? "Read-only"
                  : "Structured events"
                : "Structured events"}
              {!historyMode && (
                <span className="discovery-runtime-compat-label">Structured Launch observation</span>
              )}
            </span>
          </div>
          <button type="button" className="discovery-button discovery-button-quiet" aria-expanded={rawOpen} onClick={onToggleRaw}>
            {rawOpen ? "Hide Raw Console" : "View Raw Console"}
          </button>
        </div>
        <div className="discovery-runtime-events">
          {status.activity.items.length ? status.activity.items.map((item) => {
            const tone = item.level === "error" ? "danger" : item.level === "warning" ? "warn" : "normal";
            const milestone = item.milestone_id
              ? status.timeline.milestones.find((candidate) => candidate.id === item.milestone_id)
              : null;
            const stateLabel =
              item.level === "error"
                ? "Error"
                : milestone?.state === "completed" || status.state === "completed" || status.state === "failed" || status.state === "stopped"
                  ? "Done"
                  : "Live";
            return (
              <div key={item.sequence} className={`discovery-runtime-event ${tone}`}>
                <span className="discovery-runtime-event-time">{prototypeActivityTime(item.occurred_at, item.sequence)}</span>
                <div className="discovery-runtime-event-copy">
                  <strong>{item.text}</strong>
                  <span>{milestone?.summary ?? (item.milestone_id ? `Milestone: ${item.milestone_id}` : "Launch event")}</span>
                </div>
                <span className="discovery-runtime-event-state">{stateLabel}</span>
              </div>
            );
          }) : (
            <div className="discovery-runtime-empty">No curated activity yet.</div>
          )}
        </div>
        {rawOpen && (
          <div className="discovery-raw-console" aria-label="Raw Discovery Console">
            <div className="discovery-raw-console-head"><span>Raw Discovery Console</span><span>stdout + stderr</span></div>
            <pre>{rawLines.length ? rawLines.join("") : "Waiting for durable runner.log output..."}</pre>
            {rawError && <p role="alert">{rawError}</p>}
          </div>
        )}
      </section>

      <div className="discovery-runtime-footer">
        <div>
          {status.checkpoint ? `Checkpoint: ${status.checkpoint.stage}, round ${status.checkpoint.round}` : "No checkpoint recorded yet."}
          {status.produced_outputs.length > 0 && <span className="ml-2 text-faint">{status.produced_outputs.length} output reference(s)</span>}
        </div>
        {!historyMode && (
          <div className="flex flex-wrap items-center gap-2">
            {canStop && <button type="button" className="discovery-button discovery-button-small" disabled={busy === "stop"} onClick={onStop}>{busy === "stop" ? "Stopping..." : "Stop"}</button>}
            {canResume && <button type="button" className="discovery-button discovery-button-small discovery-button-primary" disabled={busy === "resume"} onClick={onResume}>{busy === "resume" ? "Resuming..." : "Resume"}</button>}
          </div>
        )}
      </div>
    </div>
  );
}

function PrototypeProgressPanel({ status }: { status: DiscoveryLaunchStatus | null }) {
  if (!status) return null;
  const completed = status.timeline.milestones.filter((milestone) => milestone.state === "completed").length;
  return (
    <section className="discovery-prototype-panel discovery-progress-panel" aria-label="Discovery Progress">
      <div className="discovery-rail-toggle"><strong>Progress</strong><span>{status.timeline.percent}% · {status.stage}</span></div>
      <div className="discovery-rail-body">
        <div className="discovery-progress-bar"><span style={{ width: `${status.timeline.percent}%` }} /></div>
        <div className="discovery-progress-caption"><span>{status.stage}</span><strong>{status.timeline.percent}%</strong></div>
        <div className="discovery-rail-stat"><span>Completed stages</span><strong>{completed} / {status.timeline.milestones.length}</strong></div>
        <div className="discovery-rail-stat"><span>Runtime updates</span><strong>{status.activity.items.length}</strong></div>
      </div>
    </section>
  );
}

function PrototypeLaunchHero({
  launch,
  status,
  busy,
  onStop,
}: {
  launch: DiscoveryLaunch;
  status: DiscoveryLaunchStatus | null;
  busy: Busy;
  onStop: () => void;
}) {
  return (
    <section className="discovery-prototype-panel discovery-hero-panel" aria-label="Current Discovery Launch">
      <div className="discovery-hero-row">
        <div>
          <h2 className="discovery-launch-title">{prototypeLaunchTitle(launch)}</h2>
          <div className="discovery-launch-meta">
            {prototypeLaunchShortId(launch)} · <span>{launch.state}</span> · {launch.stage} · round {launch.round}
          </div>
        </div>
        <div className="discovery-hero-actions"><PrototypeStatusPill state={launch.state} /><PrototypeLaunchAction launch={launch} busy={busy} onStop={onStop} /></div>
      </div>
      <div className="discovery-hero-facts">
        <div><span>Stage</span><strong>{launch.stage}</strong></div>
        <div><span>Round</span><strong>{launch.round}</strong></div>
        <div><span>Progress</span><strong>{status?.timeline.percent ?? 0}%</strong></div>
        <div><span>Revision</span><strong>{launch.revision_id.slice(0, 12)}</strong></div>
      </div>
    </section>
  );
}

function LaunchContext({
  launch,
  busy,
  onStop,
  error,
  runtimeStatus,
  rawOpen,
  rawLines,
  rawError,
  onToggleRaw,
}: {
  launch: DiscoveryLaunch | null;
  busy: Busy;
  onStop: () => void;
  error: string | null;
  runtimeStatus: DiscoveryLaunchStatus | null;
  rawOpen: boolean;
  rawLines: string[];
  rawError: string | null;
  onToggleRaw: () => void;
}) {
  return (
    <>
      {launch ? (
        <div className="discovery-runtime-layout">
          <div className="discovery-runtime-main">
            <PrototypeLaunchHero launch={launch} status={runtimeStatus} busy={busy} onStop={onStop} />
            <PrototypeRuntimeDesk
              status={runtimeStatus}
              busy={busy}
              rawOpen={rawOpen}
              rawLines={rawLines}
              rawError={rawError}
              onToggleRaw={onToggleRaw}
              onStop={onStop}
            />
          </div>
          <aside className="discovery-runtime-rail">
            <PrototypeProgressPanel status={runtimeStatus} />
            <div className="discovery-artifact-rail"><DiscoveryArtifactPanel launchId={launch.launch_id} /></div>
          </aside>
        </div>
      ) : (
        <EmptyContext context="launch" />
      )}
      {error && (
        <p className="mt-3 rounded-lg border border-danger/30 bg-dangerSoft px-3 py-2.5 text-[12px] text-danger" role="alert">
          {error}
        </p>
      )}
    </>
  );
}

function HistoryContext({
  currentLaunch,
  history,
  selectedId,
  busy,
  onSelect,
  onResume,
  onStop,
  error,
  runtimeStatus,
  rawOpen,
  rawLines,
  rawError,
  onToggleRaw,
}: {
  currentLaunch: DiscoveryLaunch | null;
  history: DiscoveryLaunch[];
  selectedId: string | null;
  busy: Busy;
  onSelect: (launchId: string) => void;
  onResume: (launch: DiscoveryLaunch) => void;
  onStop: () => void;
  error: string | null;
  runtimeStatus: DiscoveryLaunchStatus | null;
  rawOpen: boolean;
  rawLines: string[];
  rawError: string | null;
  onToggleRaw: () => void;
}) {
  if (!history.length && !currentLaunch) {
    return (
      <>
        <EmptyContext context="history" />
        {error && (
          <p className="mt-3 rounded-lg border border-danger/30 bg-dangerSoft px-3 py-2.5 text-[12px] text-danger" role="alert">
            {error}
          </p>
        )}
      </>
    );
  }
  const launches = currentLaunch
    ? [currentLaunch, ...history.filter((launch) => launch.launch_id !== currentLaunch.launch_id)]
    : history;
  const selected = launches.find((launch) => launch.launch_id === selectedId) ?? launches[0];
  const selectedIsActive = currentLaunch?.launch_id === selected.launch_id;
  return (
    <>
      <div className="discovery-history-layout" aria-label="Discovery Launch history">
        <aside className="discovery-history-index discovery-prototype-panel">
          <div className="discovery-history-index-head"><strong>Launches</strong><span>{launches.length} total</span></div>
          <div className="discovery-history-list">
            {launches.map((launch) => (
              <PrototypeHistoryRunItem
                key={launch.launch_id}
                launch={launch}
                selected={launch.launch_id === selected.launch_id}
                onSelect={() => onSelect(launch.launch_id)}
              />
            ))}
          </div>
        </aside>
        <main className="discovery-history-detail" aria-label={!selectedIsActive ? "Read-only history" : undefined}>
          {!selectedIsActive && (
            <p className="discovery-history-note">Completed and failed Launches are retained as read-only history. Select the active Launch to use Stop or Resume.</p>
          )}
          <PrototypeLaunchDetailHeader
            launch={selected}
            selectedIsActive={selectedIsActive}
            busy={busy}
            onStop={selectedIsActive ? onStop : undefined}
            onResume={!selectedIsActive ? () => onResume(selected) : undefined}
          />
          <PrototypeRuntimeDesk
            status={runtimeStatus}
            busy={busy}
            historyMode
            rawOpen={rawOpen}
            rawLines={rawLines}
            rawError={rawError}
            onToggleRaw={onToggleRaw}
            onStop={selectedIsActive ? onStop : undefined}
            onResume={!selectedIsActive ? () => onResume(selected) : undefined}
          />
        </main>
        <aside className="discovery-runtime-rail">
          <PrototypeProgressPanel status={runtimeStatus} />
          <div className="discovery-artifact-rail"><DiscoveryArtifactPanel launchId={selected.launch_id} /></div>
        </aside>
      </div>
      {error && (
        <p className="mt-3 rounded-lg border border-danger/30 bg-dangerSoft px-3 py-2.5 text-[12px] text-danger" role="alert">
          {error}
        </p>
      )}
    </>
  );
}

function StageCanvas({ preparation }: { preparation: DiscoveryPreparation }) {
  const preparationSaved = isCommittedPreparation(preparation);
  const conversionReady =
    Boolean(preparation.conversion.execution_input) && preparation.conversion.status !== "failed";
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
          <textarea
            className="discovery-text-input min-h-[172px]"
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
  onOpenInput,
  onOpenPrompt,
}: {
  preparation: DiscoveryPreparation;
  busy: Busy;
  error: string | null;
  onConvert: () => void;
  onOpenInput: () => void;
  onOpenPrompt: () => void;
}) {
  const preparationSaved = isCommittedPreparation(preparation);
  const conversion = preparation.conversion;
  const executionInput = conversion.execution_input;
  const convertLabel =
    busy === "convert"
      ? "Converting..."
      : conversion.status === "failed"
        ? "Try again"
        : executionInput
          ? "Re-convert"
          : "Convert";

  return (
    <section className={CARD + " overflow-hidden"} aria-labelledby="discovery-review-heading">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
        <div>
          <h3 id="discovery-review-heading" className="text-[13px] font-semibold text-ink">
            Reviewable Input
          </h3>
          <p className="mt-0.5 text-[11px] text-faint">
            {preparationSaved
              ? "Review the single backend-shaped Execution Input in the shared editor."
              : "Save the Preparation first to create the structured input."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="discovery-button discovery-button-small"
            onClick={onOpenPrompt}
            data-testid="conversion-prompt-entry"
          >
            Conversion Prompt
          </button>
          <button
            type="button"
            className="discovery-button discovery-button-small discovery-button-primary"
            disabled={!preparationSaved || busy !== null}
            onClick={onConvert}
          >
            {convertLabel}
          </button>
        </div>
      </div>
      <div className="p-3 sm:p-4" data-testid="execution-input-list">
        {conversion.status === "failed" && (
          <p className="mb-3 rounded-lg border border-danger/30 bg-dangerSoft px-3 py-2.5 text-[12px] text-danger" role="alert">
            {conversion.error ?? "The model did not produce a structured Discovery Execution Input."}
          </p>
        )}
        {!executionInput ? (
          <div className="rounded-lg border border-dashed border-lineStrong bg-paper px-4 py-6 text-center text-[12px] text-muted" aria-live="polite">
            {preparationSaved ? "Convert the saved Preparation to create the Execution Input." : "No structured Execution Input yet."}
          </div>
        ) : (
          <button
            type="button"
            className="group flex w-full items-center justify-between gap-3 rounded-lg border border-line bg-panel px-3 py-3 text-left transition-colors hover:bg-paper sm:px-4"
            onClick={onOpenInput}
            data-testid="execution-input-row"
          >
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[12px] font-semibold text-ink group-hover:text-accent">
                {executionInput.task_description}
              </span>
              <span className="mt-1 block truncate text-[10px] text-faint">
                {executionInput.domain} · {executionInput.constraints.length} constraint{executionInput.constraints.length === 1 ? "" : "s"}
              </span>
            </span>
            <span aria-hidden="true" className="shrink-0 text-[16px] text-accent">↗</span>
          </button>
        )}
        {error && conversion.status !== "failed" && (
          <p className="mt-3 rounded-lg border border-danger/30 bg-dangerSoft px-3 py-2.5 text-[12px] text-danger" role="alert">
            {error}
          </p>
        )}
      </div>
    </section>
  );
}

type ExecutionInputField =
  | "task_description"
  | "domain"
  | "background"
  | "constraints"
;

const EXECUTION_INPUT_EDITOR_FIELDS: Array<{ key: ExecutionInputField; label: string }> = [
  { key: "task_description", label: "Task description" },
  { key: "domain", label: "Domain" },
  { key: "background", label: "Background" },
  { key: "constraints", label: "Constraints" },
];

function DiscoveryEditorSurface({
  testId,
  title,
  backLabel,
  saveLabel,
  saveDisabled,
  onBack,
  onSave,
  children,
}: {
  testId: string;
  title: string;
  backLabel: string;
  saveLabel: string;
  saveDisabled: boolean;
  onBack: () => void;
  onSave: () => void;
  children: ReactNode;
}) {
  return (
    <main className="discovery-editor-route" data-testid={testId}>
      <div className="mb-4 flex items-center gap-3">
        <button type="button" className="discovery-button discovery-button-small" onClick={onBack}>
          {backLabel}
        </button>
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-faint">
            Shared editor surface
          </div>
          <h2 className="mt-1 truncate text-[22px] font-semibold tracking-[-0.04em] text-ink">
            {title}
          </h2>
        </div>
        <button
          type="button"
          className="discovery-button discovery-button-small discovery-button-primary"
          disabled={saveDisabled}
          onClick={onSave}
        >
          {saveLabel}
        </button>
      </div>
      <div className="grid gap-3 lg:grid-cols-[220px_minmax(0,1fr)_250px]">
        {children}
      </div>
    </main>
  );
}

function ExecutionInputEditor({
  input,
  busy,
  error,
  onBack,
  onSave,
  onOpenPrompt,
}: {
  input: DiscoveryExecutionInput;
  busy: Busy;
  error: string | null;
  onBack: () => void;
  onSave: (input: DiscoveryExecutionInput) => void;
  onOpenPrompt: () => void;
}) {
  const [draft, setDraft] = useState<DiscoveryExecutionInput>(input);
  const [field, setField] = useState<ExecutionInputField>("task_description");
  const fieldDefinition = EXECUTION_INPUT_EDITOR_FIELDS.find((item) => item.key === field)!;
  const isListField = field === "constraints";
  const value = draft[field];
  const textValue = Array.isArray(value) ? value.join("\n") : value;
  const updateValue = (next: string) => {
    setDraft((current) => ({
      ...current,
      [field]: isListField
        ? next.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
        : next,
    }));
  };

  return (
    <DiscoveryEditorSurface
      testId="discovery-execution-input-editor"
      title="Structured Execution Input"
      backLabel="← Reviewable Input"
      saveLabel={busy === "revision" ? "Saving..." : "Save"}
      saveDisabled={busy !== null}
      onBack={onBack}
      onSave={() => onSave(draft)}
    >
        <section className={CARD + " overflow-hidden"} aria-label="Execution schema">
          <div className="border-b border-line px-4 py-3">
            <h3 className="text-[12px] font-semibold text-ink">Execution schema</h3>
            <p className="mt-0.5 text-[10px] text-faint">4 backend fields</p>
          </div>
          <div className="space-y-1 p-2">
            {EXECUTION_INPUT_EDITOR_FIELDS.map((definition, index) => (
              <button
                key={definition.key}
                type="button"
                className={
                  "flex min-h-8 w-full items-center gap-2 rounded-lg px-2 text-left text-[10px] " +
                  (field === definition.key
                    ? "border border-accent/20 bg-accentSoft text-accent"
                    : "text-muted hover:bg-paper")
                }
                onClick={() => setField(definition.key)}
              >
                <span className="w-5 font-mono text-[9px] text-faint">{String(index + 1).padStart(2, "0")}</span>
                <span className="min-w-0 flex-1 truncate">{definition.label}</span>
                <span className="text-ok">✓</span>
              </button>
            ))}
          </div>
        </section>
        <section className={CARD + " min-w-0 overflow-hidden"} aria-label="Execution input field editor">
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-faint">Field editor</div>
              <h3 className="mt-1 text-[14px] font-semibold text-ink">{fieldDefinition.label}</h3>
            </div>
            <span className="font-mono text-[9px] text-faint">structured.execution_input</span>
          </div>
          <div className="p-4">
            <label className="block text-[11px] font-semibold text-muted" htmlFor="execution-input-field-editor">
              {fieldDefinition.label}
              <span className="float-right text-[9px] font-normal text-faint">{isListField ? "one item per line" : "multiline"}</span>
            </label>
            <textarea
              id="execution-input-field-editor"
              aria-label={fieldDefinition.label}
              className="discovery-text-input mt-2 min-h-[290px]"
              value={textValue}
              onChange={(event) => updateValue(event.target.value)}
              disabled={busy !== null}
            />
            <p className="mt-2 text-[10px] text-faint">Changes stay in the review draft until Save.</p>
          </div>
          <div className="flex items-center justify-between border-t border-line px-4 py-3">
            <button
              type="button"
              className="discovery-button discovery-button-small"
              disabled={field === EXECUTION_INPUT_EDITOR_FIELDS[0].key}
              onClick={() => {
                const index = EXECUTION_INPUT_EDITOR_FIELDS.findIndex((item) => item.key === field);
                setField(EXECUTION_INPUT_EDITOR_FIELDS[Math.max(0, index - 1)].key);
              }}
            >
              ← Previous field
            </button>
            <button
              type="button"
              className="discovery-button discovery-button-small"
              disabled={field === EXECUTION_INPUT_EDITOR_FIELDS[EXECUTION_INPUT_EDITOR_FIELDS.length - 1].key}
              onClick={() => {
                const index = EXECUTION_INPUT_EDITOR_FIELDS.findIndex((item) => item.key === field);
                setField(EXECUTION_INPUT_EDITOR_FIELDS[Math.min(EXECUTION_INPUT_EDITOR_FIELDS.length - 1, index + 1)].key);
              }}
            >
              Next field →
            </button>
          </div>
          {error && <p className="mx-4 mb-4 rounded-lg border border-danger/30 bg-dangerSoft px-3 py-2.5 text-[12px] text-danger" role="alert">{error}</p>}
        </section>
        <section className={CARD + " overflow-hidden"} aria-label="Conversion prompt">
          <div className="border-b border-line px-4 py-3">
            <h3 className="text-[12px] font-semibold text-ink">Conversion prompt</h3>
            <p className="mt-0.5 text-[10px] text-faint">Controls the structured conversion.</p>
          </div>
          <div className="p-4">
            <p className="text-[11px] leading-relaxed text-muted">The prompt is editable in the shared editor surface.</p>
            <button type="button" className="discovery-button discovery-button-small mt-3" onClick={onOpenPrompt}>
              View or edit prompt ↗
            </button>
          </div>
        </section>
    </DiscoveryEditorSurface>
  );
}

function ConversionPromptEditor({
  prompt,
  busy,
  error,
  backLabel,
  onBack,
  onSave,
}: {
  prompt: DiscoveryConversionPrompt | null;
  busy: Busy;
  error: string | null;
  backLabel: string;
  onBack: () => void;
  onSave: (instruction: string) => void;
}) {
  const [draft, setDraft] = useState(prompt?.instruction ?? "");
  const original = prompt?.instruction ?? "";
  const dirty = draft !== original;

  useEffect(() => {
    setDraft(original);
  }, [original]);

  return (
    <DiscoveryEditorSurface
      testId="discovery-conversion-prompt-editor"
      title="Discovery Input Conversion Prompt"
      backLabel={backLabel}
      saveLabel={busy === "prompt" ? "Saving..." : "Save"}
      saveDisabled={busy !== null || !dirty || !draft.trim()}
      onBack={onBack}
      onSave={() => onSave(draft)}
    >
        <section className={CARD + " overflow-hidden"} aria-label="Prompt contract">
          <div className="border-b border-line px-4 py-3">
            <h3 className="text-[12px] font-semibold text-ink">Prompt contract</h3>
            <p className="mt-0.5 text-[10px] text-faint">Active for the next Conversion.</p>
          </div>
          <div className="space-y-1 p-2">
            {["Evidence boundaries", "Structured JSON output", "Research text language"].map((label, index) => (
              <div key={label} className="flex min-h-8 items-center gap-2 rounded-lg px-2 text-[10px] text-muted">
                <span className="w-5 font-mono text-[9px] text-faint">{String(index + 1).padStart(2, "0")}</span>
                <span className="min-w-0 flex-1 truncate">{label}</span>
                <span className="text-ok">✓</span>
              </div>
            ))}
          </div>
        </section>
        <section className={CARD + " min-w-0 overflow-hidden"} aria-label="Conversion prompt editor">
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-faint">Prompt editor</div>
              <h3 className="mt-1 text-[14px] font-semibold text-ink">Instruction</h3>
            </div>
            <span className="font-mono text-[9px] text-faint">discovery.input_conversion</span>
          </div>
          <div className="p-4">
            <label className="block text-[11px] font-semibold text-muted" htmlFor="discovery-conversion-prompt-editor-field">
              Discovery Input Conversion Prompt
              <span className="float-right text-[9px] font-normal text-faint">multiline</span>
            </label>
            <textarea
              id="discovery-conversion-prompt-editor-field"
              aria-label="Discovery Input Conversion Prompt"
              className="discovery-text-input mt-2 min-h-[360px] font-mono"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              disabled={busy !== null || prompt === null}
              spellCheck={false}
            />
            <p className="mt-2 text-[10px] text-faint">Changes stay in this editor until Save.</p>
          </div>
          <div className="flex items-center justify-between border-t border-line px-4 py-3">
            <button
              type="button"
              className="discovery-button discovery-button-small"
              disabled={!dirty || busy !== null}
              onClick={() => setDraft(original)}
            >
              Reset
            </button>
            <span className="text-[10px] text-faint">{draft.length.toLocaleString()} characters</span>
          </div>
          {error && <p className="mx-4 mb-4 rounded-lg border border-danger/30 bg-dangerSoft px-3 py-2.5 text-[12px] text-danger" role="alert">{error}</p>}
        </section>
        <section className={CARD + " overflow-hidden"} aria-label="Editor guidance">
          <div className="border-b border-line px-4 py-3">
            <h3 className="text-[12px] font-semibold text-ink">Editor guidance</h3>
            <p className="mt-0.5 text-[10px] text-faint">Keep the conversion boundary explicit.</p>
          </div>
          <div className="space-y-3 p-4 text-[11px] leading-relaxed text-muted">
            <p>Sources are evidence, not instructions.</p>
            <p>Do not invent sources, data, experiments, or capabilities.</p>
            <p>Return one backend-consumable structured input.</p>
          </div>
        </section>
    </DiscoveryEditorSurface>
  );
}

function RunLaunch({
  preparation,
  currentLaunch,
  busy,
  error,
  confirming,
  onRequestRun,
  onCancel,
  onConfirm,
}: {
  preparation: DiscoveryPreparation;
  currentLaunch: DiscoveryLaunch | null;
  busy: Busy;
  error: string | null;
  confirming: boolean;
  onRequestRun: () => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const revision = preparation.conversion.saved_revision_id
    ? preparation.revisions.find(
        (candidate) => candidate.revision_id === preparation.conversion.saved_revision_id,
      )
    : null;
  const eligible = Boolean(
    !preparation.dirty &&
    preparation.conversion.status === "saved" &&
    revision?.eligible,
  );
  const executionInput = preparation.conversion.execution_input;
  const canRun = eligible && Boolean(executionInput) && currentLaunch === null && busy === null;

  return (
    <section className={CARD + " overflow-hidden"} aria-labelledby="discovery-run-heading">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
        <div>
          <h3 id="discovery-run-heading" className="text-[13px] font-semibold text-ink">
            Run Discovery
          </h3>
          <p className="mt-0.5 text-[11px] text-faint">
            Confirm once to freeze this reviewed revision into a Launch Snapshot.
          </p>
        </div>
        <button
          type="button"
          className="discovery-button discovery-button-small discovery-button-primary"
          disabled={!canRun}
          onClick={onRequestRun}
        >
          {busy === "launch" ? "Starting..." : "Run"}
        </button>
      </div>
      <div className="space-y-3 p-4 sm:p-5">
        <div className="discovery-notice" role="status" aria-live="polite">
          <span aria-hidden="true">{currentLaunch ? "•" : "→"}</span>
          <span>
            <strong>
              {currentLaunch
                ? `Launch ${currentLaunch.state}`
                : eligible
                  ? executionInput
                    ? "Ready to run"
                    : "Execution Input is missing"
                  : "Run is gated"}
            </strong>{" "}
            {currentLaunch
                ? "Preparation remains editable while this immutable Launch runs."
                : eligible
                ? executionInput
                  ? "The single backend-shaped Execution Input will be frozen into this Launch Snapshot."
                  : "Convert and save the Execution Input before Run."
                : "Save the Preparation, convert it, and save a non-empty revision first."}
          </span>
        </div>
        {error && (
          <p className="rounded-lg border border-danger/30 bg-dangerSoft px-3 py-2.5 text-[12px] text-danger" role="alert">
            {error}
          </p>
        )}
      </div>
      {confirming && (
        <div
          className="border-t border-line bg-paper px-4 py-4 sm:px-5"
          role="dialog"
          aria-modal="false"
          aria-labelledby="discovery-run-confirm-heading"
        >
          <h4 id="discovery-run-confirm-heading" className="text-[13px] font-semibold text-ink">
            Start a long-running Discovery Launch?
          </h4>
          <p className="mt-1 text-[12px] leading-relaxed text-muted">
            This action freezes the selected input and effective configuration. The Preparation can
            still be edited for a later Launch.
          </p>
          <div className="mt-3 flex justify-end gap-2">
            <button type="button" className="discovery-button discovery-button-small" onClick={onCancel}>
              Cancel
            </button>
            <button
              type="button"
              className="discovery-button discovery-button-small discovery-button-primary"
              onClick={onConfirm}
            >
              Start Launch
            </button>
          </div>
        </div>
      )}
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
  onOpenInput,
  onOpenPrompt,
  currentLaunch,
  launchError,
  confirmingRun,
  onRequestRun,
  onCancelRun,
  onConfirmRun,
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
  onOpenInput: () => void;
  onOpenPrompt: () => void;
  currentLaunch: DiscoveryLaunch | null;
  launchError: string | null;
  confirmingRun: boolean;
  onRequestRun: () => void;
  onCancelRun: () => void;
  onConfirmRun: () => void;
}) {
  return (
    <>
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
          onOpenInput={onOpenInput}
          onOpenPrompt={onOpenPrompt}
        />
        <RunLaunch
          preparation={preparation}
          currentLaunch={currentLaunch}
          busy={busy}
          error={launchError}
          confirming={confirmingRun}
          onRequestRun={onRequestRun}
          onCancel={onCancelRun}
          onConfirm={onConfirmRun}
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

function ResetPreparationDialog({
  busy,
  onCancel,
  onConfirm,
}: {
  busy: Busy;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="discovery-reset-overlay">
      <div
        className="discovery-reset-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="discovery-reset-heading"
        aria-describedby="discovery-reset-description"
      >
        <h2 id="discovery-reset-heading" className="text-[16px] font-semibold text-ink">
          Reset Preparation?
        </h2>
        <p id="discovery-reset-description" className="mt-2 text-[12px] leading-relaxed text-muted">
          This clears text, source files, Conversion drafts, and saved revisions. Current and past
          Launches remain unchanged.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            className="discovery-button discovery-button-small"
            onClick={onCancel}
            disabled={busy !== null}
          >
            Cancel
          </button>
          <button
            type="button"
            className="discovery-button discovery-button-small discovery-button-primary"
            onClick={onConfirm}
            disabled={busy !== null}
          >
            {busy === "reset" ? "Resetting..." : "Reset Preparation"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function DiscoveryView() {
  const [snapshot, setSnapshot] = useState<DiscoverySnapshot | null>(null);
  const [context, setContext] = useState<DiscoveryContextId>("preparation");
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(null);
  const [editingExecutionInput, setEditingExecutionInput] = useState(false);
  const [editingConversionPrompt, setEditingConversionPrompt] = useState(false);
  const [conversionPromptReturn, setConversionPromptReturn] = useState<"preparation" | "input">("preparation");
  const [conversionPrompt, setConversionPrompt] = useState<DiscoveryConversionPrompt | null>(null);
  const [conversionPromptLoaded, setConversionPromptLoaded] = useState(false);
  const [conversionPromptError, setConversionPromptError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [resetNotice, setResetNotice] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [confirmingReset, setConfirmingReset] = useState(false);
  const [confirmingRun, setConfirmingRun] = useState(false);
  const [busy, setBusy] = useState<Busy>(null);
  const [runtimeStatus, setRuntimeStatus] = useState<DiscoveryLaunchStatus | null>(null);
  const [rawOpen, setRawOpen] = useState(false);
  const [rawLines, setRawLines] = useState<string[]>([]);
  const [rawError, setRawError] = useState<string | null>(null);
  const idempotencyKeys = useRef(new Map<string, string>());
  const eventCursors = useRef(new Map<string, number>());
  const stopGrace = useRef<{ launch: DiscoveryLaunch; until: number } | null>(null);

  const observedLaunchId =
    context === "launch"
      ? snapshot?.current_launch?.launch_id ?? null
      : context === "history"
        ? snapshot?.current_launch?.launch_id === selectedHistoryId
          ? snapshot.current_launch.launch_id
          : snapshot?.history.find((launch) => launch.launch_id === selectedHistoryId)?.launch_id ??
            snapshot?.current_launch?.launch_id ??
            snapshot?.history[0]?.launch_id ??
            null
        : null;

  useEffect(() => {
    let alive = true;
    getDiscovery()
      .then((next) => {
        if (!alive) return;
        setSnapshot(next);
        setText(normalizePreparation(next.preparation).draft.text);
        setEditingExecutionInput(false);
        setEditingConversionPrompt(false);
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

  useEffect(() => {
    if (!snapshot?.current_launch) return undefined;
    let alive = true;
    const observedCurrentLaunchId = snapshot.current_launch.launch_id;
    const refresh = () => {
      getDiscovery()
        .then((next) => {
          if (!alive) return;
          if (context === "launch" && !next.current_launch) {
            const pendingStop = stopGrace.current;
            if (
              pendingStop?.launch.launch_id === observedCurrentLaunchId &&
              Date.now() < pendingStop.until
            ) {
              setSnapshot((current) => {
                if (!current || current.current_launch?.launch_id === observedCurrentLaunchId) {
                  return current;
                }
                return { ...next, current_launch: pendingStop.launch };
              });
              return;
            }
            stopGrace.current = null;
            setSnapshot(next);
            setSelectedHistoryId(observedCurrentLaunchId);
            setContext("history");
            return;
          }
          setSnapshot(next);
        })
        .catch(() => {
          // Keep the last server-authoritative Launch while a transient poll fails.
        });
    };
    const timer = window.setInterval(refresh, 100);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [context, snapshot?.current_launch?.launch_id]);

  useEffect(() => {
    if (!observedLaunchId) {
      setRuntimeStatus(null);
      setRawLines([]);
      setRawError(null);
      return undefined;
    }

    let alive = true;
    const controller = new AbortController();
    const refreshStatus = async () => {
      try {
        const status = normalizeLaunchStatus(await getDiscoveryLaunchStatus(observedLaunchId));
        if (!alive) return;
        setRuntimeStatus(status);
        if (status) {
          setSnapshot((current) => {
            if (!current) return current;
            return {
              ...current,
              current_launch:
                current.current_launch?.launch_id === status.launch.launch_id
                  ? status.launch
                  : current.current_launch,
              history: current.history.map((launch) =>
                launch.launch_id === status.launch.launch_id ? status.launch : launch,
              ),
            };
          });
        }
        const eventCursor = eventCursors.current.get(observedLaunchId) ?? 0;
        const events = await getDiscoveryLaunchEvents(observedLaunchId, eventCursor);
        if (alive) {
          eventCursors.current.set(observedLaunchId, events.latest_sequence);
          const restored = status ? applyLaunchEvents(status, events.events) : null;
          setRuntimeStatus(restored);
          if (restored) {
            setSnapshot((current) => {
              if (!current) return current;
              return {
                ...current,
                current_launch:
                  current.current_launch?.launch_id === restored.launch.launch_id
                    ? restored.launch
                    : current.current_launch,
                history: current.history.map((launch) =>
                  launch.launch_id === restored.launch.launch_id ? restored.launch : launch,
                ),
              };
            });
          }
        }
      } catch {
        // The full Discovery snapshot remains the fallback while a status poll retries.
      }
    };
    const streamRawLog = async () => {
      await refreshStatus();
      if (!alive || !rawOpen) return;
      setRawLines([]);
      setRawError(null);
      try {
        await streamDiscoveryLaunchLog(
          observedLaunchId,
          (line) => {
            if (alive) setRawLines((current) => [...current, line]);
          },
          controller.signal,
        );
      } catch (caught) {
        if (alive && !(caught instanceof DOMException && caught.name === "AbortError")) {
          setRawError(errorMessage(caught));
        }
      }
    };
    void (rawOpen ? streamRawLog() : refreshStatus());
    const timer = window.setInterval(() => void refreshStatus(), 200);

    return () => {
      alive = false;
      controller.abort();
      window.clearInterval(timer);
    };
  }, [observedLaunchId, rawOpen]);

  const contexts = snapshot?.contexts?.length ? snapshot.contexts : FALLBACK_CONTEXTS;
  const activeContext = contexts.find((item) => item.id === context) ?? contexts[0];
  const pageContextLabel = activeContext.id === "history" ? "Launch history" : activeContext.label;
  const preparation = snapshot ? normalizePreparation(snapshot.preparation) : null;
  const editingInput = editingExecutionInput ? preparation?.conversion.execution_input ?? null : null;
  const loading = snapshot === null && error === null;

  function setDraftText(value: string) {
    setText(value);
    setResetNotice(false);
    setMutationError(null);
    setReviewError(null);
    setSnapshot((current) => (current ? withDraftText(current, value) : current));
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

  async function resetPreparation() {
    setConfirmingReset(false);
    setMutationError(null);
    setReviewError(null);
    setBusy("reset");
    try {
      const next = await resetDiscoveryPreparation();
      setSnapshot(next);
      setText("");
      setEditingExecutionInput(false);
      setEditingConversionPrompt(false);
      setResetNotice(true);
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
      setEditingExecutionInput(false);
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

  function openExecutionInput() {
    setEditingExecutionInput(true);
    setReviewError(null);
  }

  function openConversionPrompt() {
    setConversionPromptReturn(editingExecutionInput ? "input" : "preparation");
    setEditingConversionPrompt(true);
    setConversionPromptError(null);
    if (conversionPromptLoaded) return;
    setBusy("prompt");
    void getDiscoveryConversionPrompt()
      .then((next) => {
        setConversionPrompt(next);
        setConversionPromptLoaded(true);
      })
      .catch((caught) => {
        setConversionPromptError(errorMessage(caught));
      })
      .finally(() => setBusy(null));
  }

  async function saveConversionPrompt(instruction: string) {
    setConversionPromptError(null);
    setBusy("prompt");
    try {
      const next = await saveDiscoveryConversionPrompt(instruction);
      setConversionPrompt(next);
      setConversionPromptLoaded(true);
      setEditingConversionPrompt(false);
    } catch (caught) {
      setConversionPromptError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  async function saveRevision(input: DiscoveryExecutionInput) {
    if (!preparation) return;
    setMutationError(null);
    setReviewError(null);
    setBusy("revision");
    try {
      const next = await saveDiscoveryRevision(input);
      setSnapshot(next);
      setEditingExecutionInput(false);
    } catch (caught) {
      setReviewError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  function requestRun() {
    setLaunchError(null);
    setConfirmingRun(true);
    if (preparation?.conversion.saved_revision_id) {
      const key = `start:${preparation.conversion.saved_revision_id}`;
      if (!idempotencyKeys.current.has(key)) {
        idempotencyKeys.current.set(key, createDiscoveryIdempotencyKey("discovery-start"));
      }
    }
  }

  function cancelRun() {
    if (busy === null) setConfirmingRun(false);
  }

  async function confirmRun() {
    if (!preparation) return;
    const revisionId = preparation.conversion.saved_revision_id;
    if (!revisionId) return;
    setConfirmingRun(false);
    setLaunchError(null);
    setBusy("launch");
    try {
      const key = `start:${revisionId}`;
      const requestKey =
        idempotencyKeys.current.get(key) ?? createDiscoveryIdempotencyKey("discovery-start");
      idempotencyKeys.current.set(key, requestKey);
      const result = await startDiscoveryLaunch(revisionId, requestKey);
      idempotencyKeys.current.delete(key);
      stopGrace.current = null;
      setSnapshot(result.snapshot);
      setContext("launch");
    } catch (caught) {
      setLaunchError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  async function stopLaunch() {
    const launch = snapshot?.current_launch;
    if (!launch) return;
    setLaunchError(null);
    setBusy("stop");
    const stoppingLaunch: DiscoveryLaunch = {
      ...launch,
      state: "stopping",
      stage: "stopping",
      stop_requested_at: launch.stop_requested_at ?? new Date().toISOString(),
      stop_reason: launch.stop_reason ?? "researcher requested graceful stop",
    };
    stopGrace.current = { launch: stoppingLaunch, until: Date.now() + 400 };
    setSelectedHistoryId(launch.launch_id);
    setSnapshot((current) =>
      current?.current_launch?.launch_id === launch.launch_id
        ? { ...current, current_launch: stoppingLaunch }
        : current,
    );
    setRuntimeStatus((current) =>
      current?.launch.launch_id === launch.launch_id
        ? {
            ...current,
            state: "stopping",
            stage: "stopping",
            launch: { ...current.launch, state: "stopping", stage: "stopping" },
          }
        : current,
    );
    try {
      const next = await stopDiscoveryLaunch(launch.launch_id);
      setSnapshot(
        next.current_launch
          ? next
          : { ...next, current_launch: stoppingLaunch },
      );
    } catch (caught) {
      stopGrace.current = null;
      setSnapshot((current) =>
        current?.current_launch?.launch_id === launch.launch_id
          ? { ...current, current_launch: launch }
          : current,
      );
      setLaunchError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  async function resumeLaunch(launch: DiscoveryLaunch) {
    const key = `resume:${launch.launch_id}`;
    const requestKey =
      idempotencyKeys.current.get(key) ?? createDiscoveryIdempotencyKey("discovery-resume");
    idempotencyKeys.current.set(key, requestKey);
    setLaunchError(null);
    setBusy("resume");
    try {
      const result = await resumeDiscoveryLaunch(launch.launch_id, requestKey);
      idempotencyKeys.current.delete(key);
      stopGrace.current = null;
      setSnapshot(result.snapshot);
      setContext("launch");
    } catch (caught) {
      setLaunchError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-paper" data-testid="discovery-view">
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto hairline-scroll">
        <div className="discovery-page-frame mx-auto w-full max-w-[1420px] px-5 py-6 sm:px-7 sm:py-8">
          <header className="discovery-page-header">
            <div className="min-w-0">
              <h1 className="discovery-page-title" aria-label="Discovery">
                Discovery <span aria-hidden="true" className="discovery-page-title-separator">/</span>{" "}
                <span>{pageContextLabel}</span>
              </h1>
              <p className="discovery-page-subtitle">
                One current Preparation · one active Launch · native sidecar transport
              </p>
            </div>
            <div className="discovery-page-actions">
              {activeContext.id === "preparation" && preparation ? (
                <button
                  type="button"
                  className="discovery-button discovery-page-refresh"
                  aria-label="Refresh Preparation"
                  title="Reset Preparation"
                  disabled={busy !== null}
                  onClick={() => setConfirmingReset(true)}
                >
                  <Icon name="refresh" size={14} />
                  <span>Refresh</span>
                </button>
              ) : (
                <span className={`discovery-connection ${error ? "is-error" : ""}`}>
                  {error ? "Sidecar reconnect needed" : loading ? "Connecting" : "Sidecar connected"}
                </span>
              )}
              {snapshot?.current_launch && (
                <PrototypeLaunchAction
                  launch={snapshot.current_launch}
                  busy={busy}
                  onStop={stopLaunch}
                  onResume={() => resumeLaunch(snapshot.current_launch!)}
                />
              )}
              <span className="sr-only" aria-label="Discovery status">
                {error ? "Sidecar reconnect needed" : loading ? "Loading" : preparation?.status === "draft" ? "Draft" : "Ready"}
              </span>
            </div>
          </header>

          {activeContext.id === "preparation" && confirmingReset && (
            <ResetPreparationDialog
              busy={busy}
              onCancel={() => setConfirmingReset(false)}
              onConfirm={resetPreparation}
            />
          )}

          <div className="discovery-context-nav-row">
            <nav className="discovery-context-nav" aria-label="Discovery sections" role="tablist">
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
                      onClick={() => {
                        setContext(item.id);
                        setConfirmingReset(false);
                      }}
                    >
                      {item.label}
                    </button>
                  );
                })}
              </div>
            </nav>
            {preparation && (
              <span className="discovery-status-pill discovery-context-status">
                <span
                  className={`discovery-status-dot ${isCommittedPreparation(preparation) ? "is-ready" : "is-warn"}`}
                />
                {isCommittedPreparation(preparation) ? "Preparation committed" : "Preparation in progress"}
              </span>
            )}
          </div>

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
              editingConversionPrompt ? (
                <ConversionPromptEditor
                  prompt={conversionPrompt}
                  busy={busy}
                  error={conversionPromptError}
                  backLabel={conversionPromptReturn === "input" ? "← Reviewable Input" : "← Preparation"}
                  onBack={() => {
                    setEditingConversionPrompt(false);
                    setConversionPromptError(null);
                  }}
                  onSave={saveConversionPrompt}
                />
              ) : editingInput ? (
                <ExecutionInputEditor
                  input={editingInput}
                  busy={busy}
                  error={reviewError}
                  onBack={() => setEditingExecutionInput(false)}
                  onSave={saveRevision}
                  onOpenPrompt={openConversionPrompt}
                />
              ) : (
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
                  onOpenInput={openExecutionInput}
                  onOpenPrompt={openConversionPrompt}
                  currentLaunch={snapshot?.current_launch ?? null}
                  launchError={launchError}
                  confirmingRun={confirmingRun}
                  onRequestRun={requestRun}
                  onCancelRun={cancelRun}
                  onConfirmRun={confirmRun}
                />
              )
            ) : activeContext.id === "launch" ? (
              <LaunchContext
                launch={snapshot?.current_launch ?? null}
                busy={busy}
                onStop={stopLaunch}
                error={launchError}
                runtimeStatus={runtimeStatus}
                rawOpen={rawOpen}
                rawLines={rawLines}
                rawError={rawError}
                onToggleRaw={() => setRawOpen((open) => !open)}
              />
            ) : activeContext.id === "history" ? (
              <HistoryContext
                currentLaunch={snapshot?.current_launch ?? null}
                history={snapshot?.history ?? []}
                selectedId={selectedHistoryId}
                busy={busy}
                onSelect={setSelectedHistoryId}
                onResume={resumeLaunch}
                onStop={stopLaunch}
                error={launchError}
                runtimeStatus={runtimeStatus}
                rawOpen={rawOpen}
                rawLines={rawLines}
                rawError={rawError}
                onToggleRaw={() => setRawOpen((open) => !open)}
              />
            ) : (
              <EmptyContext context={activeContext.id} />
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
