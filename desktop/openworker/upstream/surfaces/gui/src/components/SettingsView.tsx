import { useCallback, useEffect, useState } from "react";
import {
  getDiscoveryLaunchPreferences,
  getPrompt,
  getPromptLibrary,
  getSettings,
  getTrustedWorkspaces,
  savePrompt,
  setOnboarded,
  setPdfSettings,
  setScratchBase,
  setSessionsPeek,
  setWorkspaceTrusted,
  setDiscoveryLaunchPreferences,
  type DiscoveryLaunchPreferenceDefinition,
  type DiscoveryLaunchPreferences,
  type DiscoveryLaunchPreferencesDocument,
  type ModelSettings,
  type PdfSettings,
  type PromptRecord,
  type WorkspaceCommandTrust,
} from "../api";
import {
  cancelDictationModelDownload,
  deleteDictationModel,
  downloadDictationModel,
  getAutostart,
  getDictationStatus,
  getKeepAwake,
  checkForUpdate,
  installUpdate,
  isTauri,
  isUpdaterEnabled,
  listenDictationDownloadProgress,
  markDictationTestPassed,
  pickFolder,
  setAutostart,
  setKeepAwake,
  startDictation,
  stopDictation,
  verifyDictationModel,
  type DictationDownloadProgress,
  type DictationStatus,
} from "../tauri";
import { useThemePref } from "../theme";
import { Icon } from "./Icon";
import { PanelHead } from "./IntegrationsView";
import { ModelsTab } from "./ManageTabs";
import { GalleryModal } from "./GalleryModal";
import { PersonasTab } from "./PersonasTab";
import { showPersonas } from "../flags";

// Settings, restructured (Option 2) into a full-page surface that mirrors IntegrationsView's shell:
// a left sub-nav (Appearance · Files · Models · Discovery Launch · Personas) + centered panel, replacing the old
// top-tab ManageModal. Local/app concerns live here; anything external (Connectors, Messaging, MCP,
// Activity) stays under Integrations. Appearance + Files are re-skinned to the mock's Tailwind idiom;
// Models + Personas host the existing tab components inside the page shell (field re-skin to follow).
// "appearance" is the General tab's stable key - callers deep-link with it, so the
// rename (UX-021) changed only the label. "files" folded into General as a card.
type SetTab = "appearance" | "models" | "voice" | "personas" | "prompts" | "discovery";

const CARD = "rounded-xl2 border border-line bg-panel";
const FIELD_LABEL = "text-[12.5px] font-medium text-ink";
const FIELD_HELP = "text-[12px] text-muted mt-1.5 leading-relaxed";
const INPUT =
  "flex-1 min-w-0 px-3 py-2 rounded-lg border border-line bg-paper text-[13px] text-ink outline-none focus:border-accent";
const BTN_ACCENT = "text-[12.5px] px-3 py-2 rounded-lg bg-accent text-white shrink-0 disabled:opacity-40";
const BTN_BORDERED =
  "text-[12.5px] px-3 py-2 rounded-lg border border-line bg-paper hover:border-lineStrong shrink-0";

const SET_TABS: { key: SetTab; label: string; icon: "sliders" | "code" | "mic" | "sparkle" | "library" }[] = [
  { key: "appearance", label: "General", icon: "sliders" },
  { key: "models", label: "Models", icon: "code" },
  { key: "discovery", label: "Discovery Launch", icon: "sliders" },
  { key: "voice", label: "Voice input", icon: "mic" },
  { key: "prompts", label: "Prompt Library", icon: "library" },
  { key: "personas", label: "Personas", icon: "sparkle" },
];

export function SettingsView({
  initialTab,
  onOpenPersona,
}: {
  initialTab?: SetTab;
  onOpenPersona?: (id: string) => void;
}) {
  // Personas is flag-gated (hidden for launch) - filter the tab AND coerce a stale
  // deep-link to it (openSettings("personas") callers) so the page never opens on a
  // section with no nav entry.
  const personas = showPersonas();
  const tabs = personas ? SET_TABS : SET_TABS.filter((t) => t.key !== "personas");
  const wanted = initialTab && (personas || initialTab !== "personas") ? initialTab : "appearance";
  const [tab, setTab] = useState<SetTab>(wanted);
  const [promptLibraryDirty, setPromptLibraryDirty] = useState(false);
  const stablePromptDirty = useCallback((dirty: boolean) => setPromptLibraryDirty(dirty), []);

  const changeTab = (next: SetTab) => {
    if (tab === "prompts" && next !== "prompts" && promptLibraryDirty) {
      if (!window.confirm("Discard unsaved Prompt changes?")) return;
      setPromptLibraryDirty(false);
    }
    setTab(next);
  };

  return (
    <main className="flex-1 min-w-0 min-h-0 flex overflow-hidden bg-paper">
      <nav className="page-subnav w-[208px] shrink-0 border-r border-line bg-panel/40 px-3 py-4">
        <div className="px-2 text-[13.5px] font-semibold mb-3 flex items-center gap-2">
          <Icon name="gear" size={16} /> Settings
        </div>
        {tabs.map((t) => {
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              className={
                "w-full text-left px-2.5 py-2 rounded-lg text-[13px] flex items-center gap-2 " +
                (active ? "bg-paper text-accent font-medium" : "text-muted hover:bg-paper hover:text-ink")
              }
              onClick={() => changeTab(t.key)}
            >
              <Icon name={t.icon} size={15} /> {t.label}
            </button>
          );
        })}
      </nav>

      <div
        className={
          "flex-1 min-w-0 min-h-0 hairline-scroll " +
          (tab === "prompts" ? "overflow-hidden" : "overflow-y-auto")
        }
      >
        <div
          className={
            "max-w-3xl mx-auto px-7 py-6 " +
            (tab === "prompts" ? "h-full min-h-0 flex flex-col" : "")
          }
        >
          {tab === "appearance" ? (
            <AppearanceSection />
          ) : tab === "models" ? (
            <section>
              <PanelHead
                title="Models"
                sub="Providers and the models offered in the composer's picker. Keys are stored only on this computer."
              />
              <ModelsTab />
              {/* Token savings is model-spend behavior, so it lives here (UX-021),
                  not under General. */}
              <div className="mt-6">
                <TokenSavingsCard />
              </div>
            </section>
          ) : tab === "discovery" ? (
            <DiscoveryLaunchPreferencesSection />
          ) : tab === "voice" ? (
            <VoiceInputSection />
          ) : tab === "prompts" ? (
            <PromptLibrarySection onDirtyChange={stablePromptDirty} />
          ) : (
            <PersonasSection onOpenPersona={onOpenPersona} />
          )}
        </div>
      </div>
    </main>
  );
}

type PreferenceGroup = { title: string; paths: string[] };

const DISCOVERY_PREFERENCE_GROUPS: PreferenceGroup[] = [
  {
    title: "Workflow",
    paths: [
      "skip_idea_generation",
      "workflow.loop_rounds",
      "workflow.loop_mode",
      "workflow.max_iterations",
      "workflow.top_ideas_count",
      "workflow.top_ideas_evo",
      "workflow.max_concurrent_tasks",
    ],
  },
  {
    title: "Agents",
    paths: [
      "agents.generation.generation_count",
      "agents.generation.creativity",
      "agents.generation.failed_similarity_threshold",
      "agents.reflection.count",
      "agents.reflection.detail_level",
      "agents.evolution.creativity_level",
      "agents.evolution.temperature",
      "agents.evolution.use_memory",
      "agents.ranking.strategy",
      "agents.scholar.search_depth",
      "agents.survey.max_papers",
      "agents.dr.enabled",
      "agents.dr.mode",
      "agents.exp_analyze.use_llm_for_metric_direction",
    ],
  },
  {
    title: "Experiments",
    paths: ["experiment.max_runs", "experiment.use_mcts"],
  },
];

const DISCOVERY_RANKING_WEIGHTS = ["novelty", "plausibility", "testability", "alignment"] as const;

function readPreferencePath(values: DiscoveryLaunchPreferences, path: string): unknown {
  let current: unknown = values;
  for (const part of path.split(".")) {
    if (!current || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

function writePreferencePath(
  values: DiscoveryLaunchPreferences,
  path: string,
  value: unknown,
): DiscoveryLaunchPreferences {
  const next = JSON.parse(JSON.stringify(values)) as DiscoveryLaunchPreferences;
  const parts = path.split(".");
  let current: Record<string, unknown> = next as unknown as Record<string, unknown>;
  for (const part of parts.slice(0, -1)) {
    current = current[part] as Record<string, unknown>;
  }
  current[parts[parts.length - 1]] = value;
  return next;
}

function displayPreferenceLabel(path: string): string {
  const parts = path.split(".");
  const leaf = parts[parts.length - 1] || path;
  return leaf
    .split("_")
    .map((word) => word.charAt(0).toLocaleUpperCase() + word.slice(1))
    .join(" ");
}

function DiscoveryPreferenceField({
  path,
  definition,
  values,
  disabled,
  onChange,
}: {
  path: string;
  definition: DiscoveryLaunchPreferenceDefinition;
  values: DiscoveryLaunchPreferences;
  disabled: boolean;
  onChange: (path: string, value: unknown) => void;
}) {
  const value = readPreferencePath(values, path);
  const label = displayPreferenceLabel(path);
  return (
    <div className="flex items-start gap-3 border-b border-line py-3 last:border-b-0">
      <div className="min-w-0 flex-1">
        <div className={FIELD_LABEL}>{label}</div>
        <div className={FIELD_HELP}>{definition.description}</div>
      </div>
      {definition.type === "boolean" ? (
        <input
          aria-label={label}
          type="checkbox"
          className="mt-1 h-4 w-4 accent-accent"
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(event) => onChange(path, event.target.checked)}
        />
      ) : definition.type === "enum" ? (
        <select
          aria-label={label}
          className={INPUT + " max-w-[180px]"}
          value={typeof value === "string" ? value : ""}
          disabled={disabled}
          onChange={(event) => onChange(path, event.target.value)}
        >
          {(definition.values || []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      ) : (
        <input
          aria-label={label}
          className={INPUT + " max-w-[180px]"}
          type="number"
          min={definition.minimum}
          max={definition.maximum}
          step={definition.type === "integer" ? 1 : 0.1}
          value={typeof value === "number" ? value : ""}
          disabled={disabled}
          onChange={(event) => onChange(path, Number(event.target.value))}
        />
      )}
    </div>
  );
}

function DiscoveryLaunchPreferencesSection() {
  const [document, setDocument] = useState<DiscoveryLaunchPreferencesDocument | null>(null);
  const [draft, setDraft] = useState<DiscoveryLaunchPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await getDiscoveryLaunchPreferences();
      setDocument(next);
      setDraft(next.values);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Discovery Launch preferences are unavailable.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const update = (path: string, value: unknown) => {
    setDraft((current) => (current ? writePreferencePath(current, path, value) : current));
    setNotice(null);
  };

  const save = async () => {
    if (!draft || saving) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const next = await setDiscoveryLaunchPreferences({ values: draft });
      setDocument(next);
      setDraft(next.values);
      setNotice("Saved. These defaults apply to newly started Discovery Launches; running or resumed Launches keep their snapshot.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Discovery Launch preferences could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <section><PanelHead title="Discovery Launch" sub="Validated defaults used by future Discovery Launches." /><div className={CARD + " p-4 text-[12px] text-muted"}>Loading preferences…</div></section>;
  }
  if (!document || !draft) {
    return <section><PanelHead title="Discovery Launch" sub="Validated defaults used by future Discovery Launches." /><div className={CARD + " p-4"}><div className="text-[13px] text-red-600">{error || "Discovery Launch preferences are unavailable."}</div><button className={BTN_BORDERED + " mt-3"} onClick={() => void load()}>Retry</button></div></section>;
  }

  return (
    <section>
      <PanelHead
        title="Discovery Launch"
        sub="Server-validated defaults for the Discovery workflow. Changes apply only when a new Launch starts."
      />
      {error && <div role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-[12px] text-red-700">{error}</div>}
      {notice && <div role="status" className="mb-4 rounded-lg border border-line bg-accentSoft px-3 py-2.5 text-[12px] text-accent">{notice}</div>}
      <div className="space-y-4">
        {DISCOVERY_PREFERENCE_GROUPS.map((group) => (
          <div className={CARD + " p-4"} key={group.title}>
            <div className="mb-1 text-[13.5px] font-medium text-ink">{group.title}</div>
            <div className="text-[12px] text-muted">Values and validation rules come from the sidecar.</div>
            <div className="mt-2">
              {group.paths.map((path) => (
                <DiscoveryPreferenceField
                  key={path}
                  path={path}
                  definition={document.parameters[path]}
                  values={draft}
                  disabled={saving}
                  onChange={update}
                />
              ))}
            </div>
          </div>
        ))}
        <div className={CARD + " p-4"}>
          <div className="text-[13.5px] font-medium text-ink">Ranking criteria</div>
          <div className={FIELD_HELP}>Keep the four related weights together; the server requires their sum to equal 1.</div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            {DISCOVERY_RANKING_WEIGHTS.map((key) => {
              const path = `agents.ranking.criteria.${key}`;
              const value = readPreferencePath(draft, path);
              return (
                <label key={key} className="text-[12px] text-muted">
                  <span className="mb-1 block text-ink">{key}</span>
                  <input
                    className={INPUT + " w-full"}
                    type="number"
                    min={0}
                    max={1}
                    step={0.1}
                    value={typeof value === "number" ? value : ""}
                    disabled={saving}
                    onChange={(event) => update(path, Number(event.target.value))}
                  />
                </label>
              );
            })}
          </div>
        </div>
      </div>
      <div className="mt-5 flex items-center gap-2">
        <span className="text-[11.5px] text-muted">Schema v{document.schema_version}</span>
        <button className={BTN_ACCENT + " ml-auto"} onClick={() => void save()} disabled={saving}>
          {saving ? "Saving…" : "Save Discovery Defaults"}
        </button>
      </div>
    </section>
  );
}

function PromptLibrarySection({ onDirtyChange }: { onDirtyChange: (dirty: boolean) => void }) {
  const [prompts, setPrompts] = useState<PromptRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [systemOriginal, setSystemOriginal] = useState("");
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [workflowFilter, setWorkflowFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selected = prompts.find((prompt) => prompt.id === selectedId) || null;
  const dirty = !!selected && draft !== selected.text;
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);
  const workflows = [...new Set(prompts.map((prompt) => prompt.workflow))];
  const filtered = prompts.filter((prompt) => {
    const matchesWorkflow = workflowFilter === "all" || prompt.workflow === workflowFilter;
    const matchesQuery = [prompt.id, prompt.name, prompt.description, prompt.workflow, prompt.stage, prompt.text]
      .join(" ")
      .toLocaleLowerCase()
      .includes(query.trim().toLocaleLowerCase());
    return matchesWorkflow && matchesQuery;
  });

  const fetchPrompt = (id: string) => getPrompt(id);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const body = await getPromptLibrary();
      setPrompts(body.prompts);
      const first = body.prompts[0];
      if (first) {
        const detail = await fetchPrompt(first.id);
        setSelectedId(first.id);
        setDraft(detail.prompt.text);
        setSystemOriginal(detail.prompt.system_original_text);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Prompt Library is unavailable.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const selectPrompt = async (prompt: PromptRecord) => {
    if (dirty && !window.confirm("Discard unsaved Prompt changes?")) return;
    setError(null);
    setNotice(null);
    try {
      const detail = await fetchPrompt(prompt.id);
      setSelectedId(prompt.id);
      setDraft(detail.prompt.text);
      setSystemOriginal(detail.prompt.system_original_text);
    } catch (selectError) {
      setError(selectError instanceof Error ? selectError.message : "Prompt could not be loaded.");
    }
  };

  const save = async () => {
    if (!selected || saving) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const body = await savePrompt(selected.id, draft);
      setPrompts((current) => current.map((prompt) => prompt.id === body.prompt.id ? body.prompt : prompt));
      setDraft(body.prompt.text);
      setNotice("Saved. This change applies to subsequently started work only; running work keeps its snapshot.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Prompt could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const resetDraft = () => {
    if (!selected) return;
    setDraft(systemOriginal);
    setNotice("System original loaded into the draft. Save to apply it.");
    setError(null);
  };

  if (loading) return <section><PanelHead title="Prompt Library" sub="Registered Prompts used by future Vegapunk work." /><div className={CARD + " p-4 text-[12px] text-muted"}>Loading Prompt Library…</div></section>;
  if (error && !selected) return <section><PanelHead title="Prompt Library" sub="Registered Prompts used by future Vegapunk work." /><div className={CARD + " p-4"}><div className="text-[13px] text-red-600">{error}</div><button className={BTN_BORDERED + " mt-3"} onClick={() => void load()}>Retry</button></div></section>;

  const grouped = new Map<string, Map<string, PromptRecord[]>>();
  for (const prompt of filtered) {
    const stages = grouped.get(prompt.workflow) || new Map<string, PromptRecord[]>();
    stages.set(prompt.stage, [...(stages.get(prompt.stage) || []), prompt]);
    grouped.set(prompt.workflow, stages);
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <PanelHead title="Prompt Library" sub="Inspect and revise Registered Prompts used by future Vegapunk work." />
      {error && <div role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-[12px] text-red-700">{error}</div>}
      {notice && <div role="status" className="mb-4 rounded-lg border border-line bg-accentSoft px-3 py-2.5 text-[12px] text-accent">{notice}</div>}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input
          className={INPUT + " min-w-[260px] flex-1"}
          placeholder="Search name, ID, metadata, or body"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="flex max-w-full items-center gap-1 overflow-x-auto">
          {["all", ...workflows].map((workflow) => {
            const active = workflowFilter === workflow;
            const words = workflow.split("_").join(" ");
            const label = workflow === "all" ? "All" : words.charAt(0).toLocaleUpperCase() + words.slice(1);
            return (
              <button
                key={workflow}
                type="button"
                className={
                  "shrink-0 rounded-lg px-3 py-2 text-[12px] " +
                  (active ? "bg-accentSoft text-accent font-medium" : "text-muted hover:bg-panel hover:text-ink")
                }
                onClick={() => setWorkflowFilter(workflow)}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(230px,0.8fr)_minmax(0,1.7fr)] gap-4">
        <div className={CARD + " min-h-0 overflow-y-auto p-3"}>
          <div className="px-1 pb-3 text-[11px] uppercase tracking-wider text-muted">
            {filtered.length} Registered Prompts
          </div>
          <div className="space-y-4">
            {[...grouped].map(([workflow, stages]) => (
              <div key={workflow}>
                <div className="text-[11px] uppercase tracking-wider text-muted mb-1.5">{workflow}</div>
                {[...stages].map(([stage, items]) => (
                  <div key={stage} className="space-y-1 mb-3">
                    <div className="text-[11px] text-muted">{stage}</div>
                    {items.map((prompt) => (
                      <button key={prompt.id} type="button" onClick={() => void selectPrompt(prompt)} className={"w-full text-left rounded-lg px-3 py-2 " + (selectedId === prompt.id ? "bg-paper text-accent" : "hover:bg-paper") }>
                        <span className="block text-[12.5px] font-medium text-ink">{prompt.name}</span>
                        <span className="block text-[11.5px] text-muted mt-0.5">{prompt.invocation_type}</span>
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
        <div className={CARD + " min-w-0 min-h-0 overflow-y-auto p-4 flex flex-col"}>
          {selected ? (
            <>
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1"><div className="text-[15px] font-medium text-ink">{selected.name}</div><div className="text-[11.5px] text-muted mt-1 font-mono break-all">{selected.id}</div></div>
                {dirty && <span className="text-[11px] text-accent">Unsaved</span>}
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 text-[11.5px] text-muted border-y border-line py-3">
                <div><span className="block text-ink font-medium">Workflow</span>{selected.workflow} · {selected.stage}</div>
                <div><span className="block text-ink font-medium">Invocation</span>{selected.invocation_type}</div>
                <div><span className="block text-ink font-medium">Template variables</span>{selected.template_variables.join(", ") || "None"}</div>
                <div><span className="block text-ink font-medium">Required</span>{selected.required_template_variables.join(", ") || "None"}</div>
              </div>
              <textarea className="mt-4 flex-1 min-h-[180px] w-full resize-none rounded-lg border border-line bg-paper p-3 font-mono text-[12px] leading-relaxed text-ink outline-none focus:border-accent" value={draft} onChange={(event) => setDraft(event.target.value)} spellCheck={false} />
              <div className="mt-3 flex items-center gap-2"><button className={BTN_BORDERED} onClick={resetDraft} disabled={!selected || draft === systemOriginal}>Reset to system original</button><button className={BTN_ACCENT + " ml-auto"} onClick={() => void save()} disabled={!dirty || saving}>{saving ? "Saving…" : "Save Prompt"}</button></div>
            </>
          ) : <div className="text-[12px] text-muted">Select a Prompt to inspect it.</div>}
        </div>
      </div>
    </section>
  );
}

// -- Voice input: deliberate model provisioning + compatibility + microphone test (§37) --------
const voiceError = (error: unknown) =>
  error instanceof Error ? error.message : typeof error === "string" ? error : "Voice Input could not complete that action.";

const formatBytes = (bytes: number) => {
  if (!bytes) return "0 MiB";
  return `${Math.round(bytes / 1024 / 1024)} MiB`;
};

function VoiceInputSection() {
  const [status, setStatus] = useState<DictationStatus | null>(null);
  const [progress, setProgress] = useState<DictationDownloadProgress | null>(null);
  const [phase, setPhase] = useState<"idle" | "downloading" | "verifying" | "testing" | "transcribing">("idle");
  const [error, setError] = useState<string | null>(null);
  const [testTranscript, setTestTranscript] = useState("");
  const desktop = isTauri();

  const publish = (next: DictationStatus) => {
    setStatus(next);
    window.dispatchEvent(new CustomEvent("coworker:voice-input-changed", { detail: next }));
  };

  useEffect(() => {
    if (!desktop) return;
    let active = true;
    let unlisten = () => {};
    void listenDictationDownloadProgress((next) => {
      if (active) setProgress(next);
    }).then((stop) => {
      unlisten = stop;
    });
    void getDictationStatus().then(async (initial) => {
      if (!active || !initial) return;
      publish(initial);
      // One-time migration for models installed by the first STT cut, before verification markers.
      if (initial.model_installed && !initial.model_verified) {
        setPhase("verifying");
        try {
          const verified = await verifyDictationModel();
          if (active) publish(verified);
        } catch (verifyError) {
          if (active) setError(voiceError(verifyError));
        } finally {
          if (active) setPhase("idle");
        }
      }
    });
    return () => {
      active = false;
      unlisten();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [desktop]);

  const download = async () => {
    setError(null);
    setProgress({ downloaded_bytes: 0, total_bytes: status?.model_bytes || 0 });
    setPhase("downloading");
    try {
      publish(await downloadDictationModel());
    } catch (downloadError) {
      setError(voiceError(downloadError));
      const latest = await getDictationStatus();
      if (latest) publish(latest);
    } finally {
      setPhase("idle");
    }
  };

  const cancelDownload = async () => {
    await cancelDictationModelDownload().catch(() => undefined);
  };

  const repair = async () => {
    setError(null);
    try {
      publish(await deleteDictationModel());
      await download();
    } catch (repairError) {
      setError(voiceError(repairError));
    }
  };

  const remove = async () => {
    if (!window.confirm("Delete the local Whisper model and disable Voice Input?")) return;
    setError(null);
    try {
      publish(await deleteDictationModel());
      setTestTranscript("");
      setProgress(null);
    } catch (deleteError) {
      setError(voiceError(deleteError));
    }
  };

  const toggleTest = async () => {
    if (!status?.supported || !status.model_verified) return;
    setError(null);
    try {
      if (status.recording) {
        setPhase("transcribing");
        const transcript = (await stopDictation()).trim();
        setTestTranscript(transcript);
        if (!transcript) throw new Error("No speech was detected. Try again and speak for a little longer.");
        publish(await markDictationTestPassed());
      } else {
        setTestTranscript("");
        setPhase("testing");
        publish(await startDictation());
      }
    } catch (testError) {
      setError(voiceError(testError));
      const latest = await getDictationStatus();
      if (latest) publish(latest);
    } finally {
      setPhase("idle");
    }
  };

  const downloading = phase === "downloading" || !!status?.download_in_progress;
  const progressTotal = progress?.total_bytes || status?.model_bytes || 1;
  const progressPercent = Math.min(100, Math.round(((progress?.downloaded_bytes || 0) / progressTotal) * 100));
  const ready = !!status?.supported && !!status?.model_verified && !!status?.test_passed;

  return (
    <section>
      <PanelHead
        title="Voice input"
        sub="Speak naturally in the composer. Recordings and transcripts stay on this device."
      />

      {!desktop ? (
        <div className={CARD + " p-4 text-[13px] text-muted"}>Voice Input setup is available in the OpenWorker desktop app.</div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-xl border border-green-200 bg-green-50/70 px-4 py-3 text-[12.5px] text-green-800">
            <span className="font-medium">Private by design.</span> Audio is held in memory only while you record and is transcribed locally.
          </div>

          <div className={CARD}>
            <div className="p-4 flex items-start gap-3">
              <Icon name="code" size={18} className="text-accent mt-0.5" />
              <div className="min-w-0 flex-1">
                <div className="text-[13.5px] font-medium">This device</div>
                <div className="text-[12px] text-muted mt-1">{status?.device_summary || "Checking compatibility…"}</div>
                {status?.compatibility_reason && <div className="text-[12px] text-red-600 mt-1.5">{status.compatibility_reason}</div>}
              </div>
              {status && (
                <span className={"text-[11.5px] px-2 py-1 rounded-full " + (status.supported ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600")}>
                  {status.supported ? "● Compatible" : "Unsupported"}
                </span>
              )}
            </div>
            <div className="border-t border-line bg-paper/50 px-4 py-3 grid grid-cols-2 gap-3 text-[12px] text-muted">
              <div><span className="block text-ink font-medium">Mac</span>macOS 12+ · Apple Silicon M1+</div>
              <div><span className="block text-ink font-medium">Windows</span>Windows 10 22H2/11 · x64</div>
              <div><span className="block text-ink font-medium">Memory</span>8 GB recommended</div>
              <div><span className="block text-ink font-medium">Processor</span>4 CPU cores recommended</div>
            </div>
          </div>

          <div className={CARD}>
            <div className="p-4 flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-accentSoft text-accent grid place-items-center font-semibold">W</div>
              <div className="min-w-0 flex-1">
                <div className="text-[13.5px] font-medium">Whisper Base · English</div>
                <div className="text-[12px] text-muted mt-0.5">
                  {status?.model_verified ? `Installed and verified · ${formatBytes(status.model_bytes)}` : `Local voice model · ${formatBytes(status?.model_bytes || 147_964_211)}`}
                </div>
              </div>
              {status?.model_verified ? (
                <>
                  <span className="text-[11.5px] px-2 py-1 rounded-full bg-green-50 text-green-700">Verified</span>
                  <button className={BTN_BORDERED} onClick={() => void repair()}>Repair</button>
                  <button className="text-[12px] text-red-600 px-2 py-2" onClick={() => void remove()}>Delete</button>
                </>
              ) : downloading ? (
                <button className={BTN_BORDERED} onClick={() => void cancelDownload()}>Cancel</button>
              ) : phase === "verifying" ? (
                <span className="text-[12px] text-muted">Verifying…</span>
              ) : (
                <button className={BTN_ACCENT} disabled={!status?.supported} onClick={() => void download()}>Download model</button>
              )}
            </div>
            {downloading && (
              <div className="border-t border-line px-4 py-3">
                <div className="h-1.5 rounded-full bg-line overflow-hidden"><div className="h-full bg-accent transition-all" style={{ width: `${progressPercent}%` }} /></div>
                <div className="mt-1.5 text-[11.5px] text-muted flex"><span>{formatBytes(progress?.downloaded_bytes || 0)} of {formatBytes(progressTotal)}</span><span className="ml-auto">{progressPercent}%</span></div>
              </div>
            )}
          </div>

          <div className={CARD}>
            <div className="p-4 flex items-center gap-3">
              <Icon name="mic" size={18} className={ready ? "text-green-600" : "text-muted"} />
              <div className="min-w-0 flex-1">
                <div className="text-[13.5px] font-medium">Microphone test</div>
                <div className="text-[12px] text-muted mt-0.5">
                  {ready ? "Your microphone and local transcription engine are working." : "Record a short phrase to enable the composer microphone."}
                </div>
              </div>
              {ready && <span className="text-[11.5px] px-2 py-1 rounded-full bg-green-50 text-green-700">● Ready</span>}
              <button className={BTN_BORDERED} disabled={!status?.supported || !status?.model_verified || phase === "transcribing"} onClick={() => void toggleTest()}>
                {status?.recording ? "Stop and check" : phase === "transcribing" ? "Transcribing…" : ready ? "Test again" : "Test microphone"}
              </button>
            </div>
            {status?.recording && <div className="border-t border-line px-4 py-3 text-[12px] text-accent" role="status">● Listening… speak a short phrase, then stop.</div>}
            {testTranscript && <div className="border-t border-line bg-paper/50 px-4 py-3 text-[13px]">“{testTranscript}”</div>}
          </div>

          {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-[12px] text-red-700">{error}</div>}
        </div>
      )}
    </section>
  );
}

// -- Personas: installed/enabled/delete management, the dir/Git importer, and the
// entry point to the Persona Gallery (a screen-sized modal - installs finish back
// here, disabled pending consent; a gallery install re-mounts the list in place).
function PersonasSection({ onOpenPersona }: { onOpenPersona?: (id: string) => void }) {
  const [galleryBump, setGalleryBump] = useState(0);
  const [galleryOpen, setGalleryOpen] = useState(false);

  return (
    <section>
      <PanelHead
        title="Personas"
        sub="Which coworkers are enabled and shown in the picker, plus installing new persona bundles."
      />
      <PersonasTab key={galleryBump} onOpenPersona={onOpenPersona} />
      <button
        className="mt-6 w-full rounded-xl2 border border-line bg-panel px-4 py-3.5 flex items-center gap-3 text-left hover:border-lineStrong"
        data-testid="gallery-link"
        onClick={() => setGalleryOpen(true)}
      >
        <Icon name="sparkle" size={16} className="text-accent shrink-0" />
        <span className="min-w-0 flex-1">
          <span className="block text-[13.5px] font-medium">Browse the Persona Gallery</span>
          <span className="block text-[12px] text-muted">
            Curated coworkers from the OpenWorker team - see what each can do before installing.
          </span>
        </span>
        <span className="text-[12.5px] text-accent shrink-0">Open →</span>
      </button>
      {galleryOpen && (
        <GalleryModal
          onClose={() => setGalleryOpen(false)}
          onInstalled={() => setGalleryBump((b) => b + 1)}
        />
      )}
    </section>
  );
}

// -- Appearance + app behaviour ------------------------------------------------
function AppearanceSection() {
  const [theme, setTheme] = useThemePref();
  const [autostart, setAuto] = useState(false);
  const [keepAwake, setKeep] = useState(false);
  const desktop = isTauri();

  useEffect(() => {
    if (isTauri()) {
      getAutostart().then((v) => setAuto(!!v));
      getKeepAwake().then((v) => setKeep(!!v));
    }
  }, []);

  const toggleAuto = async (v: boolean) => setAuto(!!(await setAutostart(v)));
  const toggleKeep = async (v: boolean) => setKeep(!!(await setKeepAwake(v)));
  const runSetupAgain = async () => {
    await setOnboarded(false);
    window.dispatchEvent(new CustomEvent("coworker:open-onboarding"));
  };

  return (
    <section>
      <PanelHead title="General" sub="How OpenWorker looks and behaves on this machine." />

      <div className={CARD + " p-4 mb-4"}>
        <div className={FIELD_LABEL}>Theme</div>
        <div className="seg mt-2.5" role="radiogroup" aria-label="Appearance">
          {(["light", "dark", "auto"] as const).map((p) => (
            <button key={p} className={p === theme ? "active" : ""} onClick={() => setTheme(p)}>
              {p === "light" ? "Light" : p === "dark" ? "Dark" : "Auto"}
            </button>
          ))}
        </div>
        <div className={FIELD_HELP}>Auto follows your Mac&rsquo;s appearance.</div>
      </div>

      <SidebarCard />

      <FilesCard />

      <TrustedWorkspacesCard />

      {desktop && (
        <div className={CARD + " p-4"}>
          <div className={FIELD_LABEL + " mb-2.5"}>Always-on</div>
          <label className="flex items-start gap-3 py-2">
            <input type="checkbox" className="mt-0.5" checked={autostart} onChange={(e) => toggleAuto(e.target.checked)} />
            <span>
              <span className="block text-[13px] text-ink">Open at login</span>
              <span className="block text-[12px] text-muted">Launch OpenWorker automatically when you sign in.</span>
            </span>
          </label>
          <label className="flex items-start gap-3 py-2">
            <input type="checkbox" className="mt-0.5" checked={keepAwake} onChange={(e) => toggleKeep(e.target.checked)} />
            <span>
              <span className="block text-[13px] text-ink">Keep this system awake</span>
              <span className="block text-[12px] text-muted">Prevent idle sleep so scheduled tasks fire on time.</span>
            </span>
          </label>
        </div>
      )}

      {/* One card for the app-lifecycle actions (UX-021): the onboarding replay (§24 -
          every build, the browser dev shell runs the same first-run flow) and, on
          stable desktop, the manual Vegapunk update check (launch also checks automatically). */}
      <div className={CARD + " p-4 mt-4"}>
        <div className={FIELD_LABEL + " mb-2"}>Setup &amp; updates</div>
        <div className="flex items-center gap-2">
          <button className={BTN_BORDERED} onClick={runSetupAgain}>
            Run setup again
          </button>
          {desktop && <UpdateInline />}
        </div>
        <div className={FIELD_HELP}>Replays the first-run setup: model, first automation, tips.</div>
      </div>
    </section>
  );
}

function TrustedWorkspacesCard() {
  const [workspaces, setWorkspaces] = useState<WorkspaceCommandTrust[] | null>(null);

  const refresh = () =>
    getTrustedWorkspaces()
      .then(setWorkspaces)
      .catch(() => setWorkspaces([]));

  useEffect(() => {
    refresh();
  }, []);

  const revoke = async (path: string) => {
    if (!window.confirm(`Revoke command trust for ${path}?`)) return;
    await setWorkspaceTrusted(path, false);
    refresh();
  };

  return (
    <div className={CARD + " p-4 mb-4"} data-testid="trusted-workspaces-card">
      <div className={FIELD_LABEL}>Trusted workspaces</div>
      <div className={FIELD_HELP}>
        Trusted projects may manage their command allowances in .coworker/config.toml.
      </div>
      {workspaces === null ? (
        <div className="text-[12px] text-muted mt-3">Loading…</div>
      ) : workspaces.length === 0 ? (
        <div className="text-[12px] text-muted mt-3">No workspaces are trusted.</div>
      ) : (
        <div className="mt-3 divide-y divide-line">
          {workspaces.map((workspace) => (
            <div key={workspace.workspace} className="py-2.5 flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <div className="text-[12.5px] text-ink break-all">{workspace.workspace}</div>
                <div className="text-[11.5px] text-muted mt-0.5">
                  {workspace.requested_commands.length
                    ? `${workspace.requested_commands.length} project command allowance${workspace.requested_commands.length === 1 ? "" : "s"}`
                    : "No project command allowances currently declared"}
                  {!workspace.exists ? " · Folder unavailable" : ""}
                </div>
              </div>
              <button
                className="text-[12px] text-red-600 px-2 py-1"
                onClick={() => void revoke(workspace.workspace)}
              >
                Revoke
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function UpdateInline() {
  const updaterEnabled = isUpdaterEnabled();
  const [state, setState] = useState<"idle" | "checking" | "none" | "found" | "installing" | "error">("idle");
  const [version, setVersion] = useState("");

  const check = async () => {
    setState("checking");
    try {
      const u = await checkForUpdate();
      if (u) {
        setVersion(u.version);
        setState("found");
      } else {
        setState("none");
      }
    } catch {
      setState("error");
    }
  };

  const install = async () => {
    setState("installing");
    try {
      await installUpdate(); // success restarts the app
    } catch {
      setState("error");
    }
  };

  if (!updaterEnabled) return null;

  return (
    <span className="inline-flex items-center gap-2.5">
      {state === "found" ? (
        <button className={BTN_BORDERED} onClick={install} data-testid="settings-update-install">
          Update to v{version} and restart
        </button>
      ) : (
        <button
          className={BTN_BORDERED}
          onClick={check}
          disabled={state === "checking" || state === "installing"}
          data-testid="settings-update-check"
        >
          {state === "checking" ? "Checking…" : "Check for updates"}
        </button>
      )}
      {(state === "none" || state === "error" || state === "installing") && (
        <span className="text-[12px] text-muted">
          {state === "none"
            ? "You're on the latest version."
            : state === "error"
              ? "Couldn't check right now - try again later."
              : "Downloading - Vegapunk restarts by itself when it's ready."}
        </span>
      )}
    </span>
  );
}

// Telemetry/Privacy card removed for this release (owner ask 2026-07-22); the
// setCloudTelemetry API stays for a future opt-out surface.

// -- Sidebar density -------------------------------------------------------------
// -- Token savings (PDF attachments; owner ask, 2026-07-17) ---------------------
// Attachments replay with EVERY turn, so a big PDF quietly multiplies token spend.
// Auto-compaction of long histories is a planned follow-up (punchlist §7) - until
// then this card is the user's dial: attach thresholds + the fallback for models
// without native PDF support.
function TokenSavingsCard() {
  const [pdf, setPdf] = useState<PdfSettings | null>(null);

  useEffect(() => {
    getSettings()
      .then((s) =>
        setPdf({
          pdf_fallback: s.pdf_fallback || "text",
          pdf_max_pages: s.pdf_max_pages || 20,
          pdf_max_mb: s.pdf_max_mb || 10,
        }),
      )
      .catch(() => setPdf({ pdf_fallback: "text", pdf_max_pages: 20, pdf_max_mb: 10 }));
  }, []);

  const save = async (patch: Partial<PdfSettings>) => {
    setPdf((p) => (p ? { ...p, ...patch } : p));
    await setPdfSettings(patch);
  };

  if (!pdf) return null;
  return (
    <div className={CARD + " p-4 mb-4"} data-testid="token-savings-card">
      <div className={FIELD_LABEL}>Token savings</div>
      <div className={FIELD_HELP}>
        PDF attachments travel with every turn of a conversation, so large documents multiply
        what you spend on tokens.
      </div>

      <div className="mt-3 text-[13px] text-ink">PDFs on models without native PDF support</div>
      <div className="seg mt-2" role="radiogroup" aria-label="PDF fallback" data-testid="pdf-fallback">
        <button
          className={pdf.pdf_fallback === "text" ? "active" : ""}
          onClick={() => save({ pdf_fallback: "text" })}
        >
          Extract text
        </button>
        <button
          className={pdf.pdf_fallback === "images" ? "active" : ""}
          onClick={() => save({ pdf_fallback: "images" })}
        >
          Send page images
        </button>
      </div>
      <div className={FIELD_HELP}>
        Claude, GPT and Gemini read PDFs natively - this only applies to models that
        don&rsquo;t (GLM, Kimi, DeepSeek, local models…). Text extraction is cheapest; page
        images cost more tokens and need a vision-capable model.
      </div>

      <div className="mt-3 flex items-center gap-5">
        <label className="flex items-center gap-2.5">
          <span className="text-[13px] text-ink">Max pages</span>
          <input
            type="number"
            min={1}
            max={100}
            value={pdf.pdf_max_pages}
            data-testid="pdf-max-pages"
            className="w-16 px-2 py-1.5 rounded-lg border border-line bg-paper text-[13px] text-ink outline-none focus:border-accent"
            onChange={(e) => save({ pdf_max_pages: Math.max(1, Math.min(Number(e.target.value) || 20, 100)) })}
          />
        </label>
        <label className="flex items-center gap-2.5">
          <span className="text-[13px] text-ink">Max size</span>
          <input
            type="number"
            min={1}
            max={10}
            value={pdf.pdf_max_mb}
            data-testid="pdf-max-mb"
            className="w-16 px-2 py-1.5 rounded-lg border border-line bg-paper text-[13px] text-ink outline-none focus:border-accent"
            onChange={(e) => save({ pdf_max_mb: Math.max(1, Math.min(Number(e.target.value) || 10, 10)) })}
          />
          <span className="text-[12.5px] text-muted">MB</span>
        </label>
      </div>
      <div className={FIELD_HELP}>
        PDFs over these limits are not attached - you&rsquo;ll see a notice in the composer
        instead.
      </div>
    </div>
  );
}

function SidebarCard() {
  const [peek, setPeek] = useState<number | null>(null);

  useEffect(() => {
    getSettings()
      .then((s) => setPeek(s.sessions_peek || 5))
      .catch(() => setPeek(5));
  }, []);

  const save = async (n: number) => {
    const clamped = Math.max(1, Math.min(n || 5, 50));
    setPeek(clamped);
    await setSessionsPeek(clamped);
  };

  if (peek === null) return null;
  return (
    <div className={CARD + " p-4 mb-4"}>
      <div className={FIELD_LABEL}>Sidebar</div>
      <label className="flex items-center gap-3 mt-2.5">
        <span className="text-[13px] text-ink">Conversations shown per coworker</span>
        <input
          type="number"
          min={1}
          max={50}
          value={peek}
          className="w-16 px-2 py-1.5 rounded-lg border border-line bg-paper text-[13px] text-ink outline-none focus:border-accent"
          onChange={(e) => save(Number(e.target.value))}
        />
      </label>
      <div className={FIELD_HELP}>
        Longer lists collapse behind &ldquo;Show more&rdquo;. Applies per coworker and per project.
      </div>
    </div>
  );
}

// -- Files (scratch location) - one card inside General (UX-021: a single option
// doesn't earn its own tab) -----------------------------------------------------
function FilesCard() {
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [scratchDraft, setScratchDraft] = useState("");
  const [scratchMsg, setScratchMsg] = useState<string | null>(null);
  const desktop = isTauri();

  const refresh = () =>
    getSettings()
      .then((s) => {
        setSettings(s);
        setScratchDraft((d) => d || s.scratch_base || "");
      })
      .catch(() => setSettings(null));
  useEffect(() => {
    refresh();
  }, []);

  const saveScratch = async () => {
    setScratchMsg(null);
    const res = await setScratchBase(scratchDraft.trim());
    if (res.ok) {
      setScratchMsg("Saved. New conversations will use this location.");
      refresh();
    } else {
      setScratchMsg(res.error || "Could not use that location.");
    }
  };
  const browseScratch = async () => {
    const picked = await pickFolder();
    if (picked) setScratchDraft(picked);
  };

  if (!settings) return null;

  return (
    <div className={CARD + " p-4 mb-4"}>
      <div className={FIELD_LABEL}>Files</div>
        <div className="flex items-center gap-2 mt-2.5">
          <input
            className={INPUT}
            type="text"
            placeholder="~/OpenWorker"
            value={scratchDraft}
            spellCheck={false}
            autoComplete="off"
            onChange={(e) => setScratchDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && saveScratch()}
          />
          {desktop && (
            <button className={BTN_BORDERED} onClick={browseScratch} title="Pick a folder">
              Browse
            </button>
          )}
          <button className={BTN_ACCENT} onClick={saveScratch} disabled={!scratchDraft.trim()}>
            Save
          </button>
        </div>
      <div className={FIELD_HELP}>
        Each conversation gets its own folder under this location. Existing conversations keep their current
        folder; you can grant access to more folders inside any conversation.
      </div>
      {scratchMsg && <div className="text-[12.5px] text-muted mt-2.5">{scratchMsg}</div>}
    </div>
  );
}
