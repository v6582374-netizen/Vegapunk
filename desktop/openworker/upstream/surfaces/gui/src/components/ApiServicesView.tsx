import { useCallback, useEffect, useMemo, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import {
  getApiServices,
  setApiService,
  testApiService,
  type ApiService,
  type ApiServiceStatus,
} from "../api";
import { PanelHead } from "./IntegrationsView";

type Draft = {
  credential: string;
  credentialDirty: boolean;
  enabled: boolean;
  showCredential: boolean;
  testing: boolean;
  saving: boolean;
  error: string | null;
  testStatus: ApiServiceStatus | null;
  testMessage: string | null;
  lastTestAt: string | null;
};

const statusLabel: Record<ApiServiceStatus | "testing", string> = {
  disabled: "Disabled",
  not_configured: "Not configured",
  connected: "Connected",
  error: "Could not connect",
  not_tested: "Not tested",
  testing: "Testing…",
};

const statusTone: Record<ApiServiceStatus | "testing", string> = {
  disabled: "border-line bg-paper text-muted",
  not_configured: "border-danger/20 bg-dangerSoft text-danger",
  connected: "border-okLine bg-okSoft text-ok",
  error: "border-danger/20 bg-dangerSoft text-danger",
  not_tested: "border-warnSoft bg-warnSoft text-warnInk",
  testing: "border-accent/20 bg-accentSoft text-accent",
};

const statusDot: Record<ApiServiceStatus | "testing", string> = {
  disabled: "bg-faint",
  not_configured: "bg-danger",
  connected: "bg-ok",
  error: "bg-danger",
  not_tested: "bg-warnInk",
  testing: "bg-accent animate-pulse",
};

function draftFrom(service: ApiService): Draft {
  return {
    credential: "",
    credentialDirty: false,
    enabled: service.enabled,
    showCredential: false,
    testing: false,
    saving: false,
    error: null,
    testStatus: null,
    testMessage: null,
    lastTestAt: service.last_test_at,
  };
}

function displayStatus(service: ApiService, draft: Draft): ApiServiceStatus | "testing" {
  if (!draft.enabled) return "disabled";
  if (draft.testing) return "testing";
  if (draft.testStatus) return draft.testStatus;
  if (service.requires_credential && !service.credential_configured && !draft.credentialDirty && !draft.credential.trim()) {
    return "not_configured";
  }
  if (draft.credentialDirty) return "not_tested";
  return service.status === "disabled" ? "not_tested" : service.status;
}

function formatCheckedAt(value: string | null): string {
  if (!value) return "Never checked";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Checked recently";
  return `Checked ${date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`;
}

function statusMessage(service: ApiService, draft: Draft, status: ApiServiceStatus | "testing"): string {
  if (status === "disabled") return "Service is off";
  if (status === "testing") return "Checking the service";
  if (status === "not_configured") return "Add a credential to connect";
  if (status === "connected") {
    return draft.testMessage || (draft.lastTestAt ? formatCheckedAt(draft.lastTestAt) : "Connection is ready");
  }
  if (status === "error") return draft.testMessage || service.last_error || "Check the credential and try again";
  return "Test this connection when ready";
}

function StatusChip({ status }: { status: ApiServiceStatus | "testing" }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[11px] font-medium ${statusTone[status]}`}
      aria-label={`Connection status: ${statusLabel[status]}`}
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDot[status]}`} aria-hidden="true" />
      {statusLabel[status]}
    </span>
  );
}

function EnabledSwitch({ service, draft, onToggle }: { service: ApiService; draft: Draft; onToggle: () => void }) {
  return (
    <div className="flex items-center gap-2 text-[11px] text-muted">
      <span>{draft.enabled ? "Enabled" : "Disabled"}</span>
      <button
        type="button"
        role="switch"
        aria-checked={draft.enabled}
        aria-label={`${draft.enabled ? "Disable" : "Enable"} ${service.title}`}
        onClick={onToggle}
        className={`relative h-5 w-9 shrink-0 rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
          draft.enabled ? "border-accent bg-accent" : "border-lineStrong bg-paper"
        }`}
      >
        <span
          aria-hidden="true"
          className={`absolute left-[3px] top-[3px] h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform ${
            draft.enabled ? "translate-x-4" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}

export function ApiServicesView() {
  const [services, setServices] = useState<ApiService[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const result = await getApiServices();
      setServices(result.services);
      setDrafts(Object.fromEntries(result.services.map((service) => [service.name, draftFrom(service)])));
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "API Services could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const updateDraft = useCallback((name: string, patch: Partial<Draft>) => {
    setDrafts((current) => ({ ...current, [name]: { ...current[name], ...patch } }));
  }, []);

  const enabledCount = useMemo(() => services.filter((service) => drafts[service.name]?.enabled).length, [drafts, services]);
  const connectedCount = useMemo(
    () => services.filter((service) => displayStatus(service, drafts[service.name] || draftFrom(service)) === "connected").length,
    [drafts, services],
  );

  const save = async (service: ApiService, draft: Draft) => {
    updateDraft(service.name, { saving: true, error: null });
    try {
      const result = await setApiService(
        service.name,
        draft.credentialDirty
          ? { enabled: draft.enabled, credential: draft.credential }
          : { enabled: draft.enabled },
      );
      if (!result.ok || !result.service) throw new Error(result.error || "API Service could not be saved.");
      setServices((current) => current.map((item) => (item.name === service.name ? result.service! : item)));
      updateDraft(service.name, {
        ...draftFrom(result.service),
        enabled: result.service.enabled,
        saving: false,
      });
    } catch (error) {
      updateDraft(service.name, {
        saving: false,
        error: error instanceof Error ? error.message : "API Service could not be saved.",
      });
    }
  };

  const test = async (service: ApiService, draft: Draft) => {
    if (!draft.enabled || draft.testing) return;
    updateDraft(service.name, { testing: true, error: null, testMessage: null });
    try {
      const result = await testApiService(
        service.name,
        draft.credentialDirty ? draft.credential : undefined,
      );
      const status = result.status === "testing" ? "not_tested" : result.status;
      updateDraft(service.name, {
        testing: false,
        testStatus: status,
        testMessage: result.error || null,
        lastTestAt: result.checked_at || draft.lastTestAt,
        error: result.ok ? null : result.error || "Connection test failed.",
      });
    } catch (error) {
      updateDraft(service.name, {
        testing: false,
        testStatus: "error",
        testMessage: error instanceof Error ? error.message : "Connection test failed.",
        error: error instanceof Error ? error.message : "Connection test failed.",
      });
    }
  };

  return (
    <section aria-label="API Services">
      <PanelHead
        title="API Services"
        sub="Connect the scholarly services used by discovery. Each profile is saved independently and credentials stay on this computer."
      />

      <div className="mt-4 flex flex-wrap items-center gap-2" aria-label="API Services summary">
        <span className="rounded-full border border-line bg-panel px-2.5 py-1 text-[11px] text-muted">{services.length || 4} services</span>
        <span className="rounded-full border border-line bg-panel px-2.5 py-1 text-[11px] text-muted">Local credentials</span>
        <span className="rounded-full border border-line bg-panel px-2.5 py-1 text-[11px] text-muted">Linux desktop</span>
        {!loading && <span className="ml-auto text-[11px] text-faint">{enabledCount} enabled · {connectedCount} connected</span>}
      </div>

      {loading ? (
        <div className="mt-7 grid grid-cols-1 gap-3.5 md:grid-cols-2" aria-busy="true" aria-label="Loading API Services">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="h-[290px] animate-pulse rounded-xl2 border border-line bg-panel/70" />
          ))}
        </div>
      ) : loadError ? (
        <div className="mt-7 rounded-xl2 border border-danger/25 bg-dangerSoft px-4 py-3 text-[13px] text-danger" role="alert">
          <div>{loadError}</div>
          <button type="button" className="mt-2 text-[12px] font-medium underline" onClick={() => void load()}>
            Try again
          </button>
        </div>
      ) : (
        <div className="mt-7 grid grid-cols-1 gap-3.5 md:grid-cols-2" aria-label="API service connections">
          {services.map((service, index) => {
            const draft = drafts[service.name] || draftFrom(service);
            const status = displayStatus(service, draft);
            const dirty = draft.enabled !== service.enabled || draft.credentialDirty;
            const credentialInputType = service.credential_kind === "api_key" && !draft.showCredential ? "password" : service.credential_kind === "email" ? "email" : "text";
            const placeholder = service.credential_configured
              ? service.credential_source === "environment"
                ? "Provided by environment · enter a new credential to replace it"
                : "Stored securely · enter a new credential to replace it"
              : service.credential_kind === "email"
                ? "you@lab.org"
                : "Paste your API key";

            return (
              <article
                key={service.name}
                className={`relative min-w-0 overflow-hidden rounded-xl2 border border-line bg-panel p-5 shadow-[0_1px_2px_rgba(20,28,40,0.04)] transition-colors motion-safe:animate-[api-card-in_300ms_ease_both] ${
                  !draft.enabled ? "bg-panel/70" : ""
                }`}
                style={{ animationDelay: `${index * 45}ms` }}
              >
                <div className="absolute inset-x-0 top-0 h-0.5 bg-lineStrong" aria-hidden="true" />
                <div className="flex items-start justify-between gap-3.5">
                  <div className="min-w-0 pt-px">
                    <h3 className="truncate text-[16px] font-semibold tracking-[-0.02em] text-ink">{service.title}</h3>
                    <p className="mt-0.5 text-[11px] text-faint">{service.description}</p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-2">
                    <StatusChip status={status} />
                    <EnabledSwitch
                      service={service}
                      draft={draft}
                      onToggle={() => updateDraft(service.name, { enabled: !draft.enabled, testStatus: null, error: null })}
                    />
                  </div>
                </div>

                <div className="mt-5 grid gap-3">
                  <label className="block min-w-0">
                    <span className="mb-1.5 flex items-center justify-between gap-2 text-[12px] font-medium text-ink">
                      <span>{service.credential_label}</span>
                      {draft.credentialDirty && <span className="text-[10px] font-normal text-warnInk">Unsaved</span>}
                    </span>
                    <span className="flex min-w-0 items-center rounded-lg border border-line bg-paper focus-within:border-accent">
                      <input
                        className="min-w-0 flex-1 bg-transparent px-3 py-2 text-[13px] text-ink outline-none placeholder:text-faint"
                        type={credentialInputType}
                        value={draft.credential}
                        placeholder={placeholder}
                        autoComplete="off"
                        aria-label={`${service.title} ${service.credential_label}`}
                        onChange={(event) =>
                          updateDraft(service.name, {
                            credential: event.target.value,
                            credentialDirty: true,
                            testStatus: null,
                            testMessage: null,
                            error: null,
                          })
                        }
                      />
                      {service.credential_kind === "api_key" && (
                        <button
                          type="button"
                          className="mr-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted hover:bg-panel hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
                          aria-label={draft.showCredential ? `Hide ${service.title} API key` : `Show ${service.title} API key`}
                          onClick={() => updateDraft(service.name, { showCredential: !draft.showCredential })}
                        >
                          {draft.showCredential ? <EyeOff size={15} strokeWidth={1.7} /> : <Eye size={15} strokeWidth={1.7} />}
                        </button>
                      )}
                    </span>
                  </label>

                  <label className="block min-w-0">
                    <span className="mb-1.5 flex items-center justify-between gap-2 text-[12px] font-medium text-ink">
                      <span>Service address</span>
                      <span className="text-[10px] font-normal text-faint">Fixed · read-only</span>
                    </span>
                    <input
                      className="w-full min-w-0 rounded-lg border border-line bg-paper px-3 py-2 font-mono text-[11px] text-muted outline-none"
                      type="text"
                      value={service.endpoint}
                      readOnly
                      aria-readonly="true"
                      aria-label={`${service.title} service address`}
                    />
                  </label>
                </div>

                <div className="mt-4 border-t border-line pt-3.5">
                  <div className="mb-3 flex min-w-0 items-center gap-2 text-[11px] text-muted" aria-live="polite">
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDot[status]}`} aria-hidden="true" />
                    <span className={status === "error" || status === "not_configured" ? "text-danger" : status === "connected" ? "text-ok" : ""}>
                      {statusMessage(service, draft, status)}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <button
                      type="button"
                      className="rounded-lg border border-line bg-paper px-3 py-2 text-[12.5px] text-ink transition-colors hover:border-lineStrong disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={!draft.enabled || draft.testing}
                      onClick={() => void test(service, draft)}
                    >
                      {draft.testing ? "Testing…" : "Test connection"}
                    </button>
                    <button
                      type="button"
                      className="rounded-lg bg-accent px-3 py-2 text-[12.5px] text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={!dirty || draft.saving}
                      onClick={() => void save(service, draft)}
                    >
                      {draft.saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
                    </button>
                  </div>
                  {draft.error && <p className="mt-2 text-right text-[11px] text-danger" role="alert">{draft.error}</p>}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {!loading && !loadError && (
        <p className="mt-4 text-[11px] leading-relaxed text-faint">
          Color is reserved for connection state. Fixed service addresses are shown for transparency; retrieval and launch parameters live outside this module.
        </p>
      )}

      <style>{`
        @keyframes api-card-in {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @media (prefers-reduced-motion: reduce) {
          @keyframes api-card-in { from, to { opacity: 1; transform: none; } }
        }
      `}</style>
    </section>
  );
}
