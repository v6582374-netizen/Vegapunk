import type { SessionInfo, WsEvent } from "./types";

declare const __COWORKER_DEV_TOKEN__: string;

// Endpoint resolution order: runtime-injected globals (Tauri sets `window.__COWORKER_HTTP__`
// for its dynamically-chosen sidecar port) → Vite env → same-origin Web Counterpart/Vite dev
// proxy → the 127.0.0.1:8765 fallback. This keeps a single codebase: the Linux server-hosted
// build uses relative REST/WS URLs and the desktop shell still talks to its sidecar.
const hostedWeb = (): boolean =>
  (globalThis as any).__OPENWORKER_WEB__ === true;

// Browser development runs through Vite. Keeping the API same-origin lets the Vite proxy
// carry requests to the loopback sidecar even when the browser opens the UI through a LAN
// address (for example, http://10.0.0.12:1420); direct cross-origin calls would be rejected
// by the sidecar's intentional localhost-only CORS policy. Tauri's injected sidecar address
// and an explicit VITE_COWORKER_HTTP override always take precedence below.
const viteDevProxy = (): boolean => {
  const env = (import.meta as any).env || {};
  const dev = env.DEV === true || env.DEV === "true";
  return dev && !hostedWeb() && !(globalThis as any).__COWORKER_HTTP__ && !env.VITE_COWORKER_HTTP;
};

const sameOriginWs = (): string =>
  `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;

const httpBase = (): string =>
  (globalThis as any).__COWORKER_HTTP__ ||
  (import.meta as any).env?.VITE_COWORKER_HTTP ||
  (hostedWeb() || viteDevProxy() ? "" : "http://127.0.0.1:8765");
const wsBase = (): string =>
  (globalThis as any).__COWORKER_WS__ ||
  (import.meta as any).env?.VITE_COWORKER_WS ||
  (hostedWeb() || viteDevProxy() ? sameOriginWs() : "ws://127.0.0.1:8765");
const apiToken = (): string =>
  (globalThis as any).__COWORKER_API_TOKEN__ ||
  (import.meta as any).env?.VITE_COWORKER_API_TOKEN ||
  (typeof __COWORKER_DEV_TOKEN__ === "string" ? __COWORKER_DEV_TOKEN__ : "");

// All local REST calls pass through this module, so a module-local wrapper applies launch
// authentication without asking every endpoint helper to remember the security header.
const fetch = (
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> => {
  const headers = new Headers(init.headers);
  const token = apiToken();
  if (token) headers.set("X-OpenWorker-Token", token);
  return globalThis.fetch(input, {
    ...init,
    headers,
    // The Web Counterpart authenticates with an HttpOnly same-origin cookie. Explicit
    // credentials keep that session available without changing the desktop/loopback contract.
    ...(hostedWeb() && init.credentials === undefined ? { credentials: "include" as RequestCredentials } : {}),
  });
};

async function fetchJsonWithTimeout<T>(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs: number,
): Promise<{ response: Response; body: T | null }> {
  const controller = new AbortController();
  const parentSignal = init.signal;
  const abortFromParent = () => controller.abort();
  if (parentSignal) {
    if (parentSignal.aborted) controller.abort();
    else parentSignal.addEventListener("abort", abortFromParent, { once: true });
  }
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(input, { ...init, signal: controller.signal });
    let body: T | null = null;
    try {
      body = (await response.json()) as T;
    } catch {
      // Keep the status response available to callers when a sidecar/proxy
      // closes without a JSON body.
    }
    return { response, body };
  } finally {
    globalThis.clearTimeout(timeout);
    parentSignal?.removeEventListener("abort", abortFromParent);
  }
}

const openWebSocket = (url: string): WebSocket => {
  const token = apiToken();
  return token
    ? new WebSocket(url, ["openworker", token])
    : new WebSocket(url);
};

export interface Health {
  status: string;
  default_workspace: string | null;
  model: string;
}

export interface RecentWorkspace {
  path: string;
  name: string;
  exists: boolean;
}

export interface WorkspaceCommandTrust {
  workspace: string;
  requested_commands: string[];
  trusted: boolean;
  required: boolean;
  exists?: boolean;
}

export async function getHealth(): Promise<Health> {
  const res = await fetch(`${httpBase()}/v1/health`);
  return res.json();
}

export type DiscoveryContextId = "preparation" | "launch" | "history";

export interface DiscoveryContext {
  id: DiscoveryContextId;
  label: string;
  description: string;
}

export interface DiscoverySourceEntry {
  source_id: string;
  filename: string;
  extension: string;
  size: number;
  sha256: string;
}

export interface DiscoveryPreparationContent {
  text: string;
  sources: DiscoverySourceEntry[];
}

export interface DiscoveryExecutionInput {
  task_description: string;
  domain: string;
  background: string;
  constraints: string[];
  /** Explicit adapter branch; old revisions omit it and remain sci-compatible. */
  task_type?: "auto" | "sci";
}

export interface DiscoveryInputRevision {
  revision_id: string;
  created_at: string;
  execution_input?: DiscoveryExecutionInput;
  model_id: string | null;
  eligible: boolean;
}

export type DiscoveryConversionStatus = "pending" | "editing" | "saved" | "dirty" | "failed";

export interface DiscoveryConversionState {
  status: DiscoveryConversionStatus;
  execution_input?: DiscoveryExecutionInput;
  model_id: string | null;
  error: string | null;
  saved_revision_id: string | null;
  base_fingerprint: string | null;
  current_fingerprint: string;
}

export interface DiscoveryPreparation {
  status: "empty" | "draft" | "saved";
  dirty: boolean;
  draft: DiscoveryPreparationContent;
  saved: DiscoveryPreparationContent;
  revisions: DiscoveryInputRevision[];
  conversion: DiscoveryConversionState;
}

export type DiscoveryLaunchState =
  | "starting"
  | "running"
  | "stopping"
  | "awaiting_review"
  | "stopped"
  | "interrupted"
  | "completed"
  | "failed";

export interface DiscoveryLaunchAttempt {
  attempt_id: string;
  started_at: string | null;
  finished_at: string | null;
  state: "starting" | "running" | "stopping" | "awaiting_review" | "stopped" | "interrupted" | "completed" | "failed";
  adoption_nonce?: string;
  resume_from_round?: number;
}

export type DiscoveryCheckpointKey = "mas" | "method" | "handoff";

export interface DiscoveryCheckpointArtifactReference {
  path: string;
  label: string;
  detail?: string | null;
}

export interface DiscoveryCheckpoint {
  checkpoint_id?: string;
  seam?: DiscoveryCheckpointKey | string;
  attempt_id: string;
  stage: string;
  round: number;
  reason: string;
  created_at: string;
  artifacts?: DiscoveryCheckpointArtifactReference[];
}

export interface DiscoveryLaunch {
  launch_id: string;
  preparation_id: string;
  revision_id: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  state: DiscoveryLaunchState;
  stage: string;
  round: number;
  attempts: DiscoveryLaunchAttempt[];
  runner_pid: number | null;
  current_attempt_id?: string;
  checkpoint?: DiscoveryCheckpoint | null;
  resumable?: boolean;
  stop_requested_at?: string | null;
  stopped_at?: string | null;
  stop_reason?: string | null;
  outcome: string | null;
  error: string | null;
  title?: string;
  input_summary?: {
    preparation_id?: string | null;
    revision_id?: string | null;
    preparation_fingerprint?: string | null;
    source_count: number;
    source_bytes: number;
    sources: DiscoverySourceEntry[];
    title?: string;
    task_type?: "auto" | "sci";
  };
  configuration_snapshot?: Record<string, unknown>;
}

export interface DiscoverySnapshot {
  module: "discovery";
  schema_version: number;
  contexts: DiscoveryContext[];
  active_context: DiscoveryContextId;
  preparation: DiscoveryPreparation;
  current_launch: DiscoveryLaunch | null;
  history: DiscoveryLaunch[];
}

export interface DiscoveryTimelineAttempt {
  number: number;
  state: string;
  started_at: string | null;
  ended_at: string | null;
  summary: string | null;
}

export interface DiscoveryTimelineMilestone {
  id: string;
  key: string;
  label: string;
  position: number;
  state: string;
  summary: string | null;
  started_at: string | null;
  ended_at: string | null;
  attempts: DiscoveryTimelineAttempt[];
}

export interface DiscoveryProgressTimeline {
  revision: number;
  percent: number;
  current_milestone_id: string | null;
  milestones: DiscoveryTimelineMilestone[];
}

export interface DiscoveryActivityItem {
  sequence: number;
  occurred_at: string;
  level: "info" | "warning" | "error";
  milestone_id: string | null;
  text: string;
}

export interface DiscoveryActivityStream {
  oldest_sequence: number | null;
  newest_sequence: number | null;
  truncated_before_sequence: number;
  items: DiscoveryActivityItem[];
}

export interface DiscoveryLaunchStatus {
  launch: DiscoveryLaunch;
  state: DiscoveryLaunchState;
  stage: string;
  round: number;
  checkpoint: DiscoveryLaunch["checkpoint"];
  timeline: DiscoveryProgressTimeline;
  activity: DiscoveryActivityStream;
  allowed_actions: string[];
  produced_outputs: Array<{ path: string; label: string }>;
  checkpoints?: DiscoveryCheckpoint[];
  latest_event_sequence: number;
}

export interface DiscoveryLaunchEvent {
  sequence: number;
  occurred_at: string;
  type: string;
  data: Record<string, unknown>;
}

export async function getDiscovery(): Promise<DiscoverySnapshot> {
  const { response: res, body } = await fetchJsonWithTimeout<DiscoverySnapshot>(
    `${httpBase()}/v1/discovery`,
    {},
    10_000,
  );
  if (!res.ok) throw new Error(`Discovery request failed (${res.status})`);
  if (!body) throw new Error("Discovery response was empty");
  return body;
}

export interface PromptRecord {
  id: string;
  name: string;
  description: string;
  workflow: string;
  stage: string;
  order: number;
  invocation_type: string;
  mutual_exclusion_group: string | null;
  template_variables: string[];
  required_template_variables: string[];
  text: string;
  source_revision: string;
}

export interface PromptDetail extends PromptRecord {
  system_original_text: string;
}

export interface DiscoveryConversionPrompt {
  instruction: string;
  configured: boolean;
}

async function promptLibraryRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${httpBase()}${path}`, init);
  const body = await res.json();
  if (!res.ok) {
    const message = body?.error?.message || body?.detail || `Prompt request failed (${res.status})`;
    throw new Error(message);
  }
  return body as T;
}

export async function getPromptLibrary(): Promise<{ prompts: PromptRecord[] }> {
  return promptLibraryRequest("/v1/prompt-library/prompts");
}

export async function getPrompt(promptId: string): Promise<{ prompt: PromptDetail }> {
  return promptLibraryRequest(
    `/v1/prompt-library/prompts/${encodeURIComponent(promptId)}`,
  );
}

export async function savePrompt(promptId: string, text: string): Promise<{ prompt: PromptRecord }> {
  return promptLibraryRequest(
    `/v1/prompt-library/prompts/${encodeURIComponent(promptId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    },
  );
}

export async function getDiscoveryConversionPrompt(): Promise<DiscoveryConversionPrompt> {
  return promptLibraryRequest("/v1/discovery/input-conversion-prompt");
}

export async function saveDiscoveryConversionPrompt(
  instruction: string,
): Promise<DiscoveryConversionPrompt> {
  return promptLibraryRequest("/v1/discovery/input-conversion-prompt", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction }),
  });
}

async function discoveryMutation(
  path: string,
  init: RequestInit,
): Promise<DiscoverySnapshot> {
  const res = await fetch(`${httpBase()}${path}`, init);
  if (!res.ok) {
    let detail = `Discovery request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Keep the status-derived message when the sidecar did not return JSON.
    }
    throw new Error(detail);
  }
  return res.json();
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

async function readFileBytes(file: File): Promise<Uint8Array> {
  if (typeof file.arrayBuffer === "function") {
    return new Uint8Array(await file.arrayBuffer());
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (reader.result instanceof ArrayBuffer) {
        resolve(new Uint8Array(reader.result));
      } else {
        reject(new Error("The selected file could not be read."));
      }
    };
    reader.onerror = () => reject(reader.error ?? new Error("The selected file could not be read."));
    reader.readAsArrayBuffer(file);
  });
}

export async function intakeDiscoveryPreparation(
  text: string,
  files: File[],
): Promise<DiscoverySnapshot> {
  const encodedFiles = await Promise.all(
    files.map(async (file) => {
      const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath ?? "";
      return {
        filename: file.name,
        relative_path: relativePath,
        size: file.size,
        content_base64: bytesToBase64(await readFileBytes(file)),
      };
    }),
  );
  return discoveryMutation("/v1/discovery/preparation/intake", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, files: encodedFiles }),
  });
}

export async function deleteDiscoverySource(sourceId: string): Promise<DiscoverySnapshot> {
  return discoveryMutation(
    `/v1/discovery/preparation/sources/${encodeURIComponent(sourceId)}`,
    { method: "DELETE" },
  );
}

export async function saveDiscoveryPreparation(text: string): Promise<DiscoverySnapshot> {
  return discoveryMutation("/v1/discovery/preparation/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export async function resetDiscoveryPreparation(): Promise<DiscoverySnapshot> {
  return discoveryMutation("/v1/discovery/preparation/reset", { method: "POST" });
}

export async function convertDiscoveryPreparation(): Promise<DiscoverySnapshot> {
  return discoveryMutation("/v1/discovery/preparation/convert", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

export async function saveDiscoveryRevision(
  executionInput: DiscoveryExecutionInput,
): Promise<DiscoverySnapshot> {
  return discoveryMutation("/v1/discovery/preparation/revisions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ execution_input: executionInput }),
  });
}

export interface DiscoveryLaunchStartResult {
  launch_id: string;
  state: DiscoveryLaunchState;
  launch?: DiscoveryLaunch;
  snapshot: DiscoverySnapshot;
}

export function createDiscoveryIdempotencyKey(prefix = "discovery"): string {
  const cryptoApi = globalThis.crypto as Crypto & { randomUUID?: () => string };
  return cryptoApi?.randomUUID?.() ?? `${prefix}-${Date.now()}-${Math.random()}`;
}

export async function startDiscoveryLaunch(
  revisionId: string,
  requestKey?: string,
): Promise<DiscoveryLaunchStartResult> {
  const idempotencyKey = requestKey || createDiscoveryIdempotencyKey("discovery-start");
  const res = await fetch(`${httpBase()}/v1/discovery/launches`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({ preparation_id: "preparation", revision_id: revisionId }),
  });
  if (!res.ok) {
    let detail = `Discovery request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Keep the status-derived message when the sidecar did not return JSON.
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function stopDiscoveryLaunch(
  launchId: string,
): Promise<DiscoverySnapshot> {
  return discoveryMutation(`/v1/discovery/launches/${encodeURIComponent(launchId)}/stop`, {
    method: "POST",
  });
}

export async function resumeDiscoveryLaunch(
  launchId: string,
  requestKey = createDiscoveryIdempotencyKey("discovery-resume"),
): Promise<DiscoveryLaunchStartResult> {
  const res = await fetch(
    `${httpBase()}/v1/discovery/launches/${encodeURIComponent(launchId)}/resume`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": requestKey,
      },
    },
  );
  if (!res.ok) {
    let detail = `Discovery request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Keep the status-derived message when the sidecar did not return JSON.
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function getDiscoveryLaunchStatus(
  launchId: string,
): Promise<DiscoveryLaunchStatus> {
  const { response: res, body } = await fetchJsonWithTimeout<DiscoveryLaunchStatus>(
    `${httpBase()}/v1/discovery/launches/${encodeURIComponent(launchId)}/status`,
    {},
    5_000,
  );
  if (!res.ok) throw new Error(`Discovery request failed (${res.status})`);
  if (!body) throw new Error("Discovery response was empty");
  return body;
}

export async function getDiscoveryLaunchEvents(
  launchId: string,
  after = 0,
  signal?: AbortSignal,
): Promise<{
  launch_id: string;
  events: DiscoveryLaunchEvent[];
  oldest_sequence: number | null;
  latest_sequence: number;
  truncated_before_sequence: number;
}> {
  const { response: res, body } = await fetchJsonWithTimeout<{
    launch_id: string;
    events: DiscoveryLaunchEvent[];
    oldest_sequence: number | null;
    latest_sequence: number;
    truncated_before_sequence: number;
  }>(
    `${httpBase()}/v1/discovery/launches/${encodeURIComponent(launchId)}/events?after=${after}`,
    { signal },
    5_000,
  );
  if (!res.ok) throw new Error(`Discovery request failed (${res.status})`);
  if (!body) throw new Error("Discovery response was empty");
  return body;
}

export async function streamDiscoveryLaunchLog(
  launchId: string,
  onLine: (line: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(
    `${httpBase()}/v1/discovery/launches/${encodeURIComponent(launchId)}/logs/stream`,
    { signal },
  );
  if (!res.ok) throw new Error(`Discovery request failed (${res.status})`);
  if (!res.body) return;

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const emitBlock = (block: string) => {
    const dataLines = block
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"));
    if (dataLines.length) {
      onLine(
        dataLines
          .map((line) => line.slice(5).replace(/^ /, ""))
          .join("\n"),
      );
    }
  };
  const consume = (chunk: string) => {
    buffer += chunk;
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";
    for (const block of blocks) emitBlock(block);
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      consume(decoder.decode(value, { stream: true }));
    }
    consume(decoder.decode());
    if (buffer.trim()) {
      emitBlock(buffer);
    }
  } finally {
    reader.releaseLock();
  }
}

export interface DiscoveryArtifactInfo {
  path: string;
  name: string;
  kind: "markdown" | "structured" | "code" | "text" | "image" | "pdf" | "office" | "binary" | string;
  size: number;
  modified_at: number;
  previewable: boolean;
}

export interface DiscoveryArtifactContent extends DiscoveryArtifactInfo {
  ok: boolean;
  error?: string;
  content?: string | null;
  data_url?: string | null;
  truncated?: boolean;
}

async function discoveryArtifactRequest(
  path: string,
  init: RequestInit = {},
): Promise<unknown> {
  const res = await fetch(`${httpBase()}${path}`, init);
  if (!res.ok) {
    let detail = `Discovery artifact request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Keep the status-derived message when the sidecar did not return JSON.
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function getDiscoveryArtifacts(
  launchId: string,
): Promise<DiscoveryArtifactInfo[]> {
  const body = await discoveryArtifactRequest(
    `/v1/discovery/launches/${encodeURIComponent(launchId)}/artifacts`,
  );
  return body && typeof body === "object" && "artifacts" in body && Array.isArray(body.artifacts)
    ? (body.artifacts as DiscoveryArtifactInfo[])
    : [];
}

export async function readDiscoveryArtifact(
  launchId: string,
  path: string,
): Promise<DiscoveryArtifactContent> {
  const query = new URLSearchParams({ path });
  return (await discoveryArtifactRequest(
    `/v1/discovery/launches/${encodeURIComponent(launchId)}/artifacts/read?${query.toString()}`,
  )) as DiscoveryArtifactContent;
}

export async function revealDiscoveryArtifact(
  launchId: string,
  path: string,
  mode: "reveal" | "open" = "reveal",
): Promise<{ ok: boolean; path?: string; mode?: string; error?: string }> {
  return (await discoveryArtifactRequest(
    `/v1/discovery/launches/${encodeURIComponent(launchId)}/artifacts/reveal`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, mode }),
    },
  )) as { ok: boolean; path?: string; mode?: string; error?: string };
}

export async function getRecentWorkspaces(): Promise<RecentWorkspace[]> {
  const res = await fetch(`${httpBase()}/v1/workspaces/recent`);
  return (await res.json()).workspaces ?? [];
}

/** Ask the LOCAL sidecar to open the OS folder picker — the browser GUI can't obtain absolute
 * paths from web file dialogs. Blocks until the user picks or cancels; null on cancel/unavailable. */
export async function pickFolderViaServer(): Promise<string | null> {
  try {
    const res = await fetch(`${httpBase()}/v1/workspaces/pick`, { method: "POST" });
    const d = await res.json();
    return d.ok && d.path ? d.path : null;
  } catch {
    return null;
  }
}

export async function openWorkspace(
  path: string,
  create = false,
): Promise<{
  path: string;
  ok: boolean;
  error?: string;
  git_branch?: string | null;
  command_trust?: WorkspaceCommandTrust;
}> {
  const res = await fetch(`${httpBase()}/v1/workspaces/open`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, create }),
  });
  return res.json();
}

export async function getTrustedWorkspaces(): Promise<WorkspaceCommandTrust[]> {
  const res = await fetch(`${httpBase()}/v1/workspaces/trusted`);
  return (await res.json()).workspaces ?? [];
}

export async function setWorkspaceTrusted(
  path: string,
  trusted: boolean,
): Promise<{ ok: boolean; error?: string } & WorkspaceCommandTrust> {
  const res = await fetch(`${httpBase()}/v1/workspaces/trust`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, trusted }),
  });
  return res.json();
}

export async function getSessions(workspace?: string): Promise<SessionInfo[]> {
  const q = workspace ? `?workspace=${encodeURIComponent(workspace)}` : "";
  const res = await fetch(`${httpBase()}/v1/sessions${q}`);
  return (await res.json()).sessions ?? [];
}

// A structured connector-delivered inbound message (§3.1). Attached to the user message it framed,
// for display only — the model still sees the framed `content`; this drives the ConnectorMessageCard.
export interface MessageSource {
  connector: string; // platform id, e.g. "slack"
  kind: "channel" | "dm";
  channel_id: string; // e.g. "C0BD7KZ1AH5"
  channel_name: string; // resolved; may equal the id (e.g. "#ocw-test")
  sender_id: string;
  sender_name: string; // resolved; may equal the id
  ts: number; // epoch seconds
  text: string; // the RAW message (what the card shows)
}

// A transcript message from GET /v1/sessions/{id}/messages. Kept permissive (open shape) because
// itemsFromMessages reads several role-specific fields; `source` is the optional connector sidecar.
export interface ConversationMessage {
  role: string;
  content?: any;
  tool_calls?: any[];
  tool_call_id?: string;
  source?: MessageSource;
  [key: string]: any;
}

export async function getSessionMessages(sessionId: string): Promise<ConversationMessage[]> {
  const res = await fetch(`${httpBase()}/v1/sessions/${sessionId}/messages`);
  return (await res.json()).messages ?? [];
}

export async function renameSession(sessionId: string, title: string): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  return res.json();
}

export async function setSessionFlags(
  sessionId: string,
  flags: { pinned?: boolean; archived?: boolean },
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(flags),
  });
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  return res.json();
}

export interface ArtifactInfo {
  path: string; // workspace-relative (the display/API identifier)
  abs_path?: string; // absolute — what "Copy path" copies
  name: string;
  kind: "markdown" | "html" | "image" | "code" | "text" | string;
  size: number;
  modified_at: number;
}

export interface ArtifactContent {
  ok: boolean;
  error?: string;
  path: string;
  kind: string;
  content?: string;
  data_url?: string;
  truncated?: boolean;
}

export async function getArtifacts(sessionId: string): Promise<ArtifactInfo[]> {
  const res = await fetch(`${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}/artifacts`);
  return (await res.json()).artifacts ?? [];
}

export async function readArtifact(sessionId: string, path: string): Promise<ArtifactContent> {
  const q = new URLSearchParams({ path });
  const res = await fetch(`${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}/artifacts/read?${q.toString()}`);
  return res.json();
}

/** Show the artifact in the OS file manager ("reveal") or open it with its default app ("open"). */
export async function revealArtifact(
  sessionId: string,
  path: string,
  mode: "reveal" | "open" = "reveal",
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}/artifacts/reveal`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, mode }),
  });
  return res.json();
}

// -- session roots (orphan Cowork: scratch + added folders) -------------------
export interface RootInfo {
  path: string;
  writable: boolean;
  label: string;
  primary: boolean;
  exists: boolean;
}

export async function getRoots(sessionId: string): Promise<RootInfo[]> {
  const res = await fetch(`${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}/roots`);
  return (await res.json()).roots ?? [];
}

export async function addRoot(
  sessionId: string,
  path: string,
  writable: boolean,
): Promise<{ ok: boolean; error?: string; roots?: RootInfo[] }> {
  const res = await fetch(`${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}/roots`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, writable }),
  });
  return res.json();
}

export async function removeRoot(
  sessionId: string,
  path: string,
): Promise<{ ok: boolean; error?: string; roots?: RootInfo[] }> {
  const q = new URLSearchParams({ path });
  const res = await fetch(
    `${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}/roots?${q.toString()}`,
    { method: "DELETE" },
  );
  return res.json();
}

// -- MCP servers --------------------------------------------------------------
export interface McpServer {
  name: string;
  enabled: boolean;
  transport: string;
  requires_approval: boolean;
  // "connected" | "configured" | "disabled" | and for auth:"oauth" servers:
  // "needs_auth" (no tokens yet) | "authorizing" (browser sign-in in flight)
  status: string;
  auth?: "oauth" | null;
  last_error?: string | null;
  tool_count: number | null;
  config: Record<string, any>;
}

export async function getMcpServers(): Promise<McpServer[]> {
  const res = await fetch(`${httpBase()}/v1/mcp`);
  return (await res.json()).servers ?? [];
}

export async function addMcpServer(name: string, config: Record<string, any>) {
  const res = await fetch(`${httpBase()}/v1/mcp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, config }),
  });
  return res.json();
}

export async function patchMcpServer(name: string, changes: Record<string, any>) {
  const res = await fetch(`${httpBase()}/v1/mcp/${encodeURIComponent(name)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
  return res.json();
}

export async function deleteMcpServer(name: string) {
  const res = await fetch(`${httpBase()}/v1/mcp/${encodeURIComponent(name)}`, { method: "DELETE" });
  return res.json();
}

export async function getMcpTools(
  name: string,
): Promise<{ ok: boolean; error?: string; tools: { name: string; description: string }[] }> {
  const res = await fetch(`${httpBase()}/v1/mcp/${encodeURIComponent(name)}/tools`);
  return res.json();
}

export async function reloadMcp() {
  const res = await fetch(`${httpBase()}/v1/mcp/reload`, { method: "POST" });
  return res.json();
}

/** Connect one MCP server now. For OAuth servers this opens the system browser;
 * poll getMcpServers() for the status flip (authorizing → connected / needs_auth). */
export async function connectMcp(name: string): Promise<{ ok: boolean; started?: boolean }> {
  const res = await fetch(`${httpBase()}/v1/mcp/${encodeURIComponent(name)}/connect`, {
    method: "POST",
  });
  return res.json();
}

/** Drop the connection and forget the stored OAuth tokens. */
export async function signoutMcp(name: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${httpBase()}/v1/mcp/${encodeURIComponent(name)}/signout`, {
    method: "POST",
  });
  return res.json();
}

// -- connectors ---------------------------------------------------------------
export interface ConnectorField {
  key: string;
  label: string;
  secret: boolean;
  required: boolean;
  help: string;
  placeholder: string;
}

// A message from a sender not (yet) on the allow-list — parked instead of dropped (§19).
export interface ParkedMessage {
  id: string;
  platform: string;
  chat_id: string;
  chat_name: string | null;
  user_id: string;
  user_name: string | null;
  chat_type: string;
  text: string;
  ts: number;
  team_id?: string | null; // workspace (managed Slack relay); null on manual Socket Mode
}

// One connected Slack workspace (managed relay is multi-workspace; ids are workspace-scoped,
// so each workspace carries its OWN allow-list).
export interface SlackWorkspace {
  team_id: string;
  account: string;
  domain?: string; // slack.com subdomain — unique even when display names collide
  allowed_users: string[];
  allow_all: boolean;
  allowed_user_names?: Record<string, string | null>;
  approval_owner_ids?: string[];
  approval_owner_names?: Record<string, string | null>;
  // Who installed this workspace (authed_user) — pre-added to the allow-list on
  // connect (UX-027); the GUI marks their chip "you" and keys the setup card copy.
  installer_user_id?: string;
  installer_name?: string;
}

// One connected GitHub App installation (managed relay is multi-installation;
// sender logins are global but each installation keeps its OWN allow-list).
export interface GithubInstallation {
  installation_id: string;
  account_login: string; // the org/user the App is installed on
  account_type: string; // "Organization" | "User"
  repo_selection: string; // "all" | "selected"
  github_login: string; // the connecting user's own login
  allowed_users: string[]; // sender logins allowed to trigger work
  allow_all: boolean;
}

// One connected HubSpot portal (multi-portal: `hubspot:portal:<hub_id>` profiles).
export interface HubSpotPortal {
  hub_id: string;
  name: string;
  sandbox: boolean;
  default: boolean;
  managed: boolean;
  access: "read" | "write" | ""; // consent tier granted ("" = manual token, unknown)
}

// One connected Google account (multi-account: `gmail:account:<email>` /
// `google_calendar:account:<email>` profiles — same shape for both).
export interface GmailAccount {
  email: string;
  default: boolean;
  managed: boolean;
  scopes: string;
  needs_reauth: boolean;
}

// "Never show agents" — enforced locally in the tool layer; agents see silent
// omissions, the user sees counts on tool cards + Activity rows.
export interface GmailFilters {
  senders: string[];
  labels: string[];
}

// One account of a generic multi-account connector (`<name>:account:<id>`
// profiles — Notion workspaces, PostHog projects, …). Gmail/Calendar predate
// the generic layer and keep their email-keyed shape above.
export interface AccountRow {
  account_id: string;
  name: string; // display identity captured at connect (workspace name, email, …)
  default: boolean;
  managed: boolean;
}

export interface Connector {
  name: string;
  title: string;
  icon: string;
  blurb: string;
  // Pre-connect detail page copy (UX-DECISIONS §38): optional About paragraph
  // (empty → group omitted) + honest Access bullets.
  about?: string;
  access?: string[];
  auth: string;
  two_way: boolean;
  // Chat-platform capability, narrower than two_way: sessions can subscribe to channels.
  channels: boolean;
  available: boolean;
  fields: ConnectorField[];
  instructions: string[];
  connected: boolean;
  account: string | null;
  enabled: boolean;
  brand_color: string; // hex brand color, e.g. "#611f69" (fallback gray "#6b7280")
  logo: string; // stable logo id keyed into the frontend registry (empty → fallback glyph)
  aliases?: string[]; // extra typeahead terms ("calendar" surfaces Outlook)
  mcp?: boolean; // MCP-backed one-click (vendor-hosted MCP + local OAuth — no cloud sign-in)
  allowed_users: string[]; // the allow-list (managed inline in the Connectors tab)
  allowed_user_names?: Record<string, string | null>; // id → display name (people directory)
  approval_owner_ids?: string[]; // Manual Slack: humans allowed to resolve approvals
  approval_owner_names?: Record<string, string | null>;
  recent?: RecentSender[]; // recently-seen senders on a connected two-way connector
  unauthorized?: ParkedMessage[]; // parked messages from unallowed senders (§19)
  tools: ConnectorTool[];
  managed: boolean; // one-click managed OAuth available (needs cloud sign-in)
  managed_paused?: boolean; // one-click temporarily off (e.g. Google CASA pending) — badge "Coming soon"
  managed_profile: boolean; // current profile came from managed OAuth (vs manual paste)
  mode?: string; // "relay" for the managed cloud path; "" for manual/token connect
  workspaces?: SlackWorkspace[]; // Slack only: connected workspaces (managed relay)
  // Gmail/Calendar: email-keyed rows; generic account connectors (notion,
  // attio, posthog, …): AccountRow. The detail pages narrow by connector.
  accounts?: GmailAccount[] | AccountRow[];
  filters?: GmailFilters; // Gmail only: "Never show agents" senders/labels
  portals?: HubSpotPortal[]; // HubSpot only: connected portals (multi-portal)
  hidden_fields?: string[]; // HubSpot only: properties stripped from agent reads
  installations?: GithubInstallation[]; // GitHub only: App installations (managed relay)
}

// --- OpenWorker Cloud (optional sign-in; manual token paste always works) ---

export interface CloudStatus {
  signed_in: boolean;
  account: string;
  user_id: string;
  telemetry_enabled?: boolean; // Phase 5 opt-out; signed-out users send nothing regardless
}

/** Flip the product-telemetry preference (local; only meaningful when signed in). */
export async function setCloudTelemetry(
  enabled: boolean,
): Promise<{ ok: boolean; telemetry_enabled?: boolean }> {
  const res = await fetch(`${httpBase()}/v1/cloud/telemetry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return res.json();
}

export async function getCloudStatus(): Promise<CloudStatus> {
  const res = await fetch(`${httpBase()}/v1/cloud/status`);
  return res.json();
}

export async function cloudLogin(): Promise<{ ok: boolean }> {
  // The sidecar opens the system browser; the GUI just polls status after.
  const res = await fetch(`${httpBase()}/v1/cloud/login`, { method: "POST" });
  return res.json();
}

/** Poll cloud status until the browser sign-in lands (or the bound runs out).
 *
 * Fast 500ms polls for the first 20s — the moment the user finishes in the
 * browser they're staring at the app waiting for it to flip, and a 2s interval
 * reads as "sign-in is slow" (owner complaint, 2026-07-16) — then relaxes to 2s
 * for the long tail (~2min total). Calls `onDone` with the signed-in status, or
 * null when it timed out. Returns a cancel function (call on unmount). */
export function waitForCloudSignIn(
  onDone: (s: CloudStatus | null) => void,
): () => void {
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let polls = 0;
  const tick = async () => {
    polls += 1;
    const s = await getCloudStatus().catch(() => null);
    if (cancelled) return;
    if (s?.signed_in) return onDone(s);
    if (polls >= 90) return onDone(null); // 40×500ms + 50×2s ≈ 2min
    timer = setTimeout(tick, polls < 40 ? 500 : 2000);
  };
  timer = setTimeout(tick, 500);
  return () => {
    cancelled = true;
    if (timer) clearTimeout(timer);
  };
}

export async function cloudLogout(): Promise<{ ok: boolean }> {
  const res = await fetch(`${httpBase()}/v1/cloud/logout`, { method: "POST" });
  return res.json();
}

export async function connectManaged(
  name: string,
  options?: { access?: "read" | "write" },
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/${encodeURIComponent(name)}/connect-managed`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // `access` names a broker-defined consent tier (hubspot read | write).
      // GitHub needs no flow choice: the broker is authorize-first — one connect
      // links an existing App installation or redirects on to the install page.
      body: JSON.stringify({
        ...(options?.access ? { access: options.access } : {}),
      }),
    },
  );
  return res.json();
}

/** One-click connect for an MCP-backed connector (monday, asana, jira): the sidecar
 * opens the vendor's sign-in in the browser (local OAuth, no cloud account needed);
 * poll getConnectors until the card flips to connected. */
export async function connectMcpBacked(name: string): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/${encodeURIComponent(name)}/mcp-connect`,
    { method: "POST" },
  );
  return res.json();
}

export interface ConnectorTool {
  name: string;
  label: string;
  kind: "read" | "write" | string;
  description: string;
  enabled: boolean;
  requires_approval: boolean;
}

export async function getConnectors(): Promise<Connector[]> {
  const res = await fetch(`${httpBase()}/v1/connectors`);
  return (await res.json()).connectors ?? [];
}

export async function connectConnector(
  name: string,
  fields: Record<string, string>,
): Promise<{ ok: boolean; account?: string; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/connectors/${encodeURIComponent(name)}/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields }),
  });
  return res.json();
}

export async function disconnectConnector(name: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${httpBase()}/v1/connectors/${encodeURIComponent(name)}/disconnect`, {
    method: "POST",
  });
  return res.json();
}

export async function updateConnectorTools(
  name: string,
  enabled: Record<string, boolean>,
): Promise<{ ok: boolean; error?: string; tools?: Record<string, boolean> }> {
  const res = await fetch(`${httpBase()}/v1/connectors/${encodeURIComponent(name)}/tools`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return res.json();
}

export interface AuditEvent {
  id: number;
  timestamp: string;
  session_id: string;
  agent: string;
  workspace: string;
  connector: string;
  tool: string;
  stage: string;
  status: string;
  approval: string;
  args: Record<string, any>;
  result_preview: string;
  reason: string;
  resource: string;
}

export async function getAudit(params: {
  limit?: number;
  session_id?: string;
  connector?: string;
  tool?: string;
} = {}): Promise<AuditEvent[]> {
  const q = new URLSearchParams();
  if (params.limit) q.set("limit", String(params.limit));
  if (params.session_id) q.set("session_id", params.session_id);
  if (params.connector) q.set("connector", params.connector);
  if (params.tool) q.set("tool", params.tool);
  const res = await fetch(`${httpBase()}/v1/audit${q.toString() ? "?" + q.toString() : ""}`);
  return (await res.json()).events ?? [];
}

export interface BrowserState {
  open: boolean;
  url: string;
  title: string;
  status: string;
  last_action: string;
  last_result: string;
  last_error: string;
  screenshot_data_url: string;
  updated_at: string | null;
  controls: any[];
}

export async function getBrowserState(): Promise<BrowserState> {
  const res = await fetch(`${httpBase()}/v1/browser/state`);
  return res.json();
}

export async function takeBrowserScreenshot(): Promise<BrowserState & { ok?: boolean; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/browser/screenshot`, { method: "POST" });
  return res.json();
}

export async function closeBrowser(): Promise<{ ok?: boolean; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/browser/close`, { method: "POST" });
  return res.json();
}

// -- settings (model API key, default model, onboarding) ----------------------
export interface SurfaceVisibility {
  cowork: boolean; // always true
  chat: boolean;
  code: boolean;
}

export interface ModelSettings {
  provider: string;
  model: string;
  models: string[];
  has_key: boolean;
  model_ready: boolean; // can the default model's provider actually run (any provider)?
  source: "env" | "store" | null;
  onboarded: boolean;
  surfaces: SurfaceVisibility;
  scratch_base: string;
  secrets_path: string;  // OS-native on-disk location the server reports (not hardcoded)
  // Sidebar layout preference (§7): "flat" = the persona accordions / today's list; "grouped" =
  // bounded per-persona cards. Defaults to "flat" (absent → flat) so the GUI is robust to an older
  // backend that hasn't shipped the field yet.
  nav_layout?: "flat" | "grouped";
  // Sidebar: sessions shown per group before "Show more" (default 5, 1–50).
  sessions_peek?: number;
  // Curated-matrix display names ({full id → "GLM-5.2 · via Together"}); custom models absent.
  model_labels?: Record<string, string>;
  // Token savings (PDF attachments): fallback for models without native PDF support,
  // and attach-time thresholds. Optional so the GUI is robust to an older backend.
  pdf_fallback?: "text" | "images";
  pdf_max_pages?: number; // default 20, 1–100
  pdf_max_mb?: number; // default 10, 1–10
  discovery_launch_preferences?: DiscoveryLaunchPreferencesDocument;
}

export type ApiServiceStatus = "disabled" | "not_configured" | "connected" | "error" | "not_tested";

export interface ApiService {
  name: string;
  title: string;
  description: string;
  credential_label: string;
  credential_kind: "email" | "api_key";
  endpoint: string | null;
  docs_url: string | null;
  docs_url_editable: boolean;
  requires_credential: boolean;
  enabled: boolean;
  credential_configured: boolean;
  credential_source: "environment" | "stored" | null;
  status: ApiServiceStatus;
  last_test_at: string | null;
  last_error: string | null;
}

export interface ApiServiceTestResult {
  ok: boolean;
  status: ApiServiceStatus | "testing";
  checked_at?: string;
  error?: string;
}

export interface ApiServiceMutationResult {
  ok: boolean;
  service?: ApiService;
  error?: string;
}

export async function getApiServices(): Promise<{ services: ApiService[] }> {
  const res = await fetch(`${httpBase()}/v1/settings/api-services`);
  if (!res.ok) throw new Error("External data could not be loaded.");
  return res.json();
}

export async function setApiService(
  name: string,
  values: { enabled: boolean; credential?: string; docs_url?: string },
): Promise<ApiServiceMutationResult> {
  const res = await fetch(`${httpBase()}/v1/settings/api-services/${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
  const body = (await res.json().catch(() => null)) as ApiServiceMutationResult | null;
  if (!res.ok) throw new Error(body?.error || "API Service could not be saved.");
  return body || { ok: false, error: "API Service could not be saved." };
}

export async function testApiService(
  name: string,
  credential?: string,
  docsUrl?: string,
): Promise<ApiServiceTestResult> {
  const res = await fetch(`${httpBase()}/v1/settings/api-services/${encodeURIComponent(name)}/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...(credential === undefined ? {} : { credential }),
      ...(docsUrl === undefined ? {} : { docs_url: docsUrl }),
    }),
  });
  const body = (await res.json().catch(() => null)) as ApiServiceTestResult | null;
  if (!res.ok) throw new Error(body?.error || "API Service connection test failed.");
  return body || { ok: false, status: "error", error: "API Service connection test failed." };
}

export interface DiscoveryLaunchPreferences {
  backend: "codex" | "qwen_code" | "openhands";
  skip_idea_generation: boolean;
  workflow: {
    loop_rounds: number;
    loop_mode: "fresh" | "incremental";
    max_iterations: number;
    top_ideas_count: number;
    top_ideas_evo: boolean;
    max_concurrent_tasks: number;
  };
  agents: {
    generation: {
      generation_count: number;
      creativity: number;
      failed_similarity_threshold: number;
    };
    reflection: {
      count: number;
      detail_level: "low" | "medium" | "high";
    };
    evolution: {
      creativity_level: number;
      temperature: number;
      use_memory: boolean;
    };
    ranking: {
      criteria: {
        novelty: number;
        plausibility: number;
        testability: number;
        alignment: number;
      };
      strategy: "default" | "distinct";
    };
    scholar: { search_depth: "shallow" | "moderate" | "deep" };
    survey: { max_papers: number };
    dr: { enabled: boolean; mode: "simple" | "complex" | "qa" };
    exp_analyze: { use_llm_for_metric_direction: boolean };
  };
  experiment: { max_runs: number; use_mcts: boolean };
}

export interface DiscoveryLaunchPreferenceDefinition {
  type: "boolean" | "integer" | "number" | "enum" | "object";
  description: string;
  minimum?: number;
  maximum?: number;
  sum?: number;
  values?: string[];
  properties?: string[];
}

export interface DiscoveryLaunchPreferencesDocument {
  schema_version: number;
  values: DiscoveryLaunchPreferences;
  defaults: DiscoveryLaunchPreferences;
  parameters: Record<string, DiscoveryLaunchPreferenceDefinition>;
}

export type DiscoveryLaunchPreferencesPatch = {
  [Key in keyof DiscoveryLaunchPreferences]?: DiscoveryLaunchPreferences[Key] extends object
    ? DiscoveryLaunchPreferencesPatchValue<DiscoveryLaunchPreferences[Key]>
    : DiscoveryLaunchPreferences[Key];
};

type DiscoveryLaunchPreferencesPatchValue<Value> = {
  [Key in keyof Value]?: Value[Key] extends object
    ? DiscoveryLaunchPreferencesPatchValue<Value[Key]>
    : Value[Key];
};

export interface PdfSettings {
  pdf_fallback: "text" | "images";
  pdf_max_pages: number;
  pdf_max_mb: number;
}

/** Persist the Token-savings PDF settings (fallback mode + attach thresholds). */
export async function setPdfSettings(
  patch: Partial<PdfSettings>,
): Promise<{ ok: boolean; error?: string } & Partial<PdfSettings>> {
  const res = await fetch(`${httpBase()}/v1/settings/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return res.json();
}

/** Read the server-owned Discovery Launch defaults and their validation metadata. */
export async function getDiscoveryLaunchPreferences(): Promise<DiscoveryLaunchPreferencesDocument> {
  const res = await fetch(`${httpBase()}/v1/settings/discovery-launch`);
  return res.json();
}

/** Save a complete or nested patch of Discovery Launch defaults. */
export async function setDiscoveryLaunchPreferences(
  values: DiscoveryLaunchPreferencesPatch | { values: DiscoveryLaunchPreferencesPatch },
): Promise<DiscoveryLaunchPreferencesDocument & { ok?: boolean }> {
  const res = await fetch(`${httpBase()}/v1/settings/discovery-launch`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    const message = detail?.detail?.message || detail?.detail || "Discovery Launch preferences could not be saved.";
    throw new Error(typeof message === "string" ? message : "Discovery Launch preferences could not be saved.");
  }
  return res.json();
}

/** Local page/size probe for a PDF data URL — the composer's attach-time threshold check. */
export async function inspectPdf(
  dataUrl: string,
): Promise<{ ok: boolean; pages?: number; bytes?: number; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/attachments/inspect-pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data_url: dataUrl }),
  });
  return res.json();
}

/** Persist how many sessions a sidebar group shows before "Show more". */
export async function setSessionsPeek(
  n: number,
): Promise<{ ok: boolean; sessions_peek?: number; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/settings/sessions-peek`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessions_peek: n }),
  });
  return res.json();
}

export async function setScratchBase(
  path: string,
): Promise<{ ok: boolean; error?: string; scratch_base?: string }> {
  const res = await fetch(`${httpBase()}/v1/settings/scratch-base`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  return res.json();
}

export async function setSurfaces(
  flags: { chat?: boolean; code?: boolean },
): Promise<{ ok: boolean; surfaces: SurfaceVisibility }> {
  const res = await fetch(`${httpBase()}/v1/settings/surfaces`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(flags),
  });
  return res.json();
}

/** Persist the sidebar layout preference (flat ↔ grouped-by-persona); read back from getSettings. */
export async function setNavLayout(
  layout: "flat" | "grouped",
): Promise<{ ok: boolean; nav_layout?: "flat" | "grouped"; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/settings/nav-layout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nav_layout: layout }),
  });
  return res.json();
}

// Fired after a cloud sign-in/out completes so the account row (§26) refreshes without
// waiting for the next window focus.
export const CLOUD_CHANGED = "coworker:cloud-changed";
export function announceCloudChanged() {
  window.dispatchEvent(new CustomEvent(CLOUD_CHANGED));
}

// Fired the first time Inbox machinery is engaged (an item parks, or a session goes
// Unattended) — the account row's inbox chip unlocks stickily on it (§26).
export const INBOX_UNLOCK = "coworker:inbox-unlock";
export function announceInboxUnlock() {
  window.dispatchEvent(new CustomEvent(INBOX_UNLOCK));
}

// -- Personas -----------------------------------------------------------------

// Fired after any persona mutation (enable/disable/install/delete) so always-mounted
// consumers (the sidebar's new-session picker) refetch instead of going stale.
export const PERSONAS_CHANGED = "coworker:personas-changed";
function announcePersonasChanged() {
  window.dispatchEvent(new CustomEvent(PERSONAS_CHANGED));
}

export interface Persona {
  id: string;
  name: string;
  icon: string;
  tagline: string;
  needs_workspace: boolean;
  builtin: boolean;
  family: string;
  workspace: string; // "git" | "project" | "deliverable" | "none" — drives project-scoping
  tools: string[];
  enabled: boolean;
  surfaced: boolean;
  default: boolean;
}

export interface PersonaConsent {
  id: string;
  name: string;
  description: string;
  tools: string[];
  risk: string[];
  connectors: boolean;
  mcp: string[];
  messaging: boolean;
  recommended_mode: string;
  recommended_models: string[];
  source: string | null;
  builtin: boolean;
}

export async function getPersonas(): Promise<Persona[]> {
  const res = await fetch(`${httpBase()}/v1/personas`);
  return (await res.json()).personas;
}

export async function updatePersona(
  id: string,
  body: { enabled?: boolean; surfaced?: boolean; default?: boolean },
): Promise<{ ok: boolean; personas?: Persona[]; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/personas/${encodeURIComponent(id)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const out = await res.json();
  if (out.ok !== false) announcePersonasChanged();
  return out;
}

/** Uninstall a non-builtin persona (its snapshot + state). Local; works signed out. */
export async function deletePersona(
  id: string,
): Promise<{ ok: boolean; personas?: Persona[]; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/personas/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  const out = await res.json();
  if (out.ok) announcePersonasChanged();
  return out;
}

// A curated persona card from the cloud gallery (metadata only — the manifest
// is fetched server-side at install and runs through the normal consent flow).
export interface GalleryPersona {
  slug: string;
  version: number;
  name: string;
  icon: string;
  tagline: string;
  description: string;
  family: string;
  workspace: string;
  publisher: string;
  recommended_connectors: string[];
  risk_summary: string;
  featured?: boolean; // publisher-flagged for the gallery's featured carousel
}

export async function getCloudGallery(): Promise<{
  ok: boolean;
  personas: GalleryPersona[];
  error?: string;
}> {
  const res = await fetch(`${httpBase()}/v1/cloud/gallery`);
  return res.json();
}

// Solo page for one gallery coworker. `capabilities` is the desktop's own
// consent summary derived from the manifest (same parser as install), so the
// page shows exactly what installing would ask the user to approve.
export interface GalleryDetail {
  ok: boolean;
  error?: string;
  card?: GalleryPersona & { pitch_markdown: string };
  capabilities?: {
    tools: string[];
    risk: string[];
    connectors: boolean;
    mcp: string[];
    messaging: boolean;
    recommended_mode: string;
    recommended_models: string[];
  };
  recommends?: { kind: string; ref: string; reason: string; tier: string }[];
}

export async function getCloudGalleryDetail(slug: string): Promise<GalleryDetail> {
  const res = await fetch(`${httpBase()}/v1/cloud/gallery/${encodeURIComponent(slug)}`);
  return res.json();
}

export async function installPersona(
  body: { dir?: string; git_url?: string; gallery_slug?: string },
): Promise<{ ok: boolean; consent?: PersonaConsent[]; personas?: Persona[]; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/personas/install`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const out = await res.json();
  if (out.ok) announcePersonasChanged();
  return out;
}

// -- Persona detail + connection defaults (§5) --------------------------------
// A persona's declared recommendation (manifest `recommends`): a connector or MCP server it works
// best with, with a reason + tier (core/optional). `connected` is annotated server-side from the
// connector list so the detail page can show connect state without a second round-trip.
export interface PersonaRecommendation {
  kind: string; // "connector" | "mcp" | …
  ref: string; // connector id (e.g. "github") or mcp/server name
  reason: string;
  tier: string; // "core" | "optional"
  connected: boolean;
}

// A persona-default connection (the middle of the §4 hierarchy): for a connected connector, whether
// new sessions of this persona get it enabled by default.
export interface PersonaDefaultConnection {
  connector: string; // connector id
  enabled: boolean; // persona-default on/off
  connected: boolean; // is the account actually connected (else the toggle is disabled)
}

export interface PersonaDetail {
  id: string;
  name: string;
  icon: string;
  tagline: string;
  description: string;
  enabled: boolean; // persona on/off (shown in the picker)
  tools: string[];
  recommended_models: string[];
  default_permission_mode: string;
  workspace: string;
  recommends: PersonaRecommendation[];
  default_connections: PersonaDefaultConnection[];
}

export async function getPersonaDetail(id: string): Promise<PersonaDetail> {
  const res = await fetch(`${httpBase()}/v1/personas/${encodeURIComponent(id)}`);
  return res.json();
}

/** Set a persona-default connection (new sessions of this persona get it on/off by default). */
export async function setPersonaConnection(
  id: string,
  connector: string,
  enabled: boolean,
): Promise<{ ok: boolean; default_connections?: PersonaDefaultConnection[]; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/personas/${encodeURIComponent(id)}/connections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ connector, enabled }),
  });
  return res.json();
}

/** Enable/disable the persona (whether it surfaces in the new-session picker). */
export async function setPersonaEnabled(
  id: string,
  enabled: boolean,
): Promise<{ ok: boolean; personas?: Persona[]; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/personas/${encodeURIComponent(id)}/enable`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  const out = await res.json();
  if (out.ok) announcePersonasChanged();
  return out;
}

// -- Per-session connections (Sources bar + drawer, §6) -----------------------
// An effective-enabled connector for a session, with a short human detail (e.g. "#ocw-test · DMs").
// `enabled` reflects the session override/persona default so the drawer toggle shows correct state.
export interface SessionConnectedConnector {
  connector: string;
  enabled: boolean;
  detail: string;
}

// A persona-recommended connector not yet connected (drives the `⚠ N` attention count).
export interface SessionRecommendedConnector {
  connector: string;
  reason: string;
  tier: string;
  connected: boolean;
}

export interface SessionConnections {
  connected: SessionConnectedConnector[];
  recommended: SessionRecommendedConnector[];
  attention: number; // ⚠ count = recommended connectors not yet connected
}

/** `persona` = the active persona hint — required for brand-new sessions (no server-side
 * record yet), otherwise the view resolves to the default persona's defaults/recommends. */
export async function getSessionConnections(
  sessionId: string,
  persona?: string,
): Promise<SessionConnections> {
  const q = persona ? `?persona=${encodeURIComponent(persona)}` : "";
  const res = await fetch(
    `${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}/connections${q}`,
  );
  return res.json();
}

/**
 * Set a per-session connection override (mute/unmute a connector for THIS session). Pass
 * `clear: true` to drop the override and inherit the persona default again.
 */
export async function setSessionConnection(
  sessionId: string,
  connector: string,
  enabled: boolean,
  clear = false,
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}/connections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ connector, enabled, ...(clear ? { clear: true } : {}) }),
  });
  return res.json();
}

// -- Inbox + Unattended -------------------------------------------------------
export interface InboxItem {
  id: string;
  session_id: string;
  kind: "approval" | "question" | "notification" | "directory" | "plan";
  title: string;
  body: string;
  state: "pending" | "resolved";
  resolution: string | null;
  inbox: string;
  created_at: string;
  resolved_at: string | null;
  visibility?: "inline" | "inbox";
  // Question metadata (ask_user): quick-reply choices + a free-text escape.
  options?: string[];
  allow_text?: boolean;
  multi?: boolean;
  // Kind-specific payload (directory: {path, writable}; …).
  data?: Record<string, any>;
  // Originating-session context (server-joined) so the Inbox is self-contained.
  session_title?: string;
  session_agent?: string | null;
  session_workspace?: string | null;
  session_exists?: boolean;
}

export async function getInbox(sessionId?: string, state?: string): Promise<InboxItem[]> {
  const q = new URLSearchParams();
  if (sessionId) q.set("session_id", sessionId);
  if (state) q.set("state", state);
  const res = await fetch(`${httpBase()}/v1/inbox?${q.toString()}`);
  return (await res.json()).items;
}

export async function resolveInboxItem(
  id: string,
  resolution: string,
): Promise<{ ok: boolean }> {
  const res = await fetch(`${httpBase()}/v1/inbox/${encodeURIComponent(id)}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resolution }),
  });
  return res.json();
}

// -- channel subscriptions (view-only) ----------------------------------------
export interface Subscription {
  session_id: string;
  session_title: string;
  agent: string;
  channel: string;
  channel_name?: string | null; // resolved display name ("ocw-test"); address stays the id
  routing_target: string | null;
  collision: boolean; // inbound subscription == outbound Inbox routing on the same channel
}

export interface RecentChannel {
  channel: string;
  name?: string | null; // resolved display name, e.g. "ocw-test" (falls back to the address)
  last_from: string | null;
  last_text: string | null;
}

export async function getSubscriptions(): Promise<Subscription[]> {
  const res = await fetch(`${httpBase()}/v1/subscriptions`);
  return (await res.json()).subscriptions ?? [];
}

// -- inbox routing (where Unattended approvals/questions get mirrored) ---------
export interface InboxBinding {
  name: string;
  channel: string | null; // platform, e.g. "slack" (null = in-app Inbox only)
  target: string; // chat_id, e.g. "C0BEJNCQQ8Y"
}

export async function getInboxRouting(): Promise<InboxBinding[]> {
  const res = await fetch(`${httpBase()}/v1/inbox/routing`);
  return (await res.json()).bindings ?? [];
}

export async function setInboxBinding(
  name: string,
  channel: string | null,
  target: string,
): Promise<{ ok: boolean; bindings?: InboxBinding[]; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/inbox/routing/binding`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, channel, target }),
  });
  return res.json();
}

export interface UnroutedItem {
  source: string;
  sender: string;
  text: string;
  reason: string;
  ts: number;
}

export async function getUnrouted(): Promise<UnroutedItem[]> {
  const res = await fetch(`${httpBase()}/v1/unrouted`);
  return (await res.json()).items ?? [];
}

export async function getRecentChannels(): Promise<RecentChannel[]> {
  const res = await fetch(`${httpBase()}/v1/channels/recent`);
  return (await res.json()).channels ?? [];
}

export async function subscribeChannel(
  sessionId: string,
  channel: string,
): Promise<{ ok: boolean; channel?: string; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/subscriptions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, channel }),
  });
  return res.json();
}

export async function unsubscribeChannel(
  sessionId: string,
  channel: string,
): Promise<{ ok: boolean; removed?: boolean }> {
  const res = await fetch(`${httpBase()}/v1/subscriptions/remove`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, channel }),
  });
  return res.json();
}

export async function getUnattended(sessionId: string): Promise<boolean> {
  const res = await fetch(
    `${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}/unattended`,
  );
  return (await res.json()).unattended;
}

export async function setUnattended(
  sessionId: string,
  unattended: boolean,
): Promise<{ ok: boolean; unattended: boolean }> {
  const res = await fetch(
    `${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}/unattended`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ unattended }),
    },
  );
  return res.json();
}

export async function getSettings(): Promise<ModelSettings> {
  const res = await fetch(`${httpBase()}/v1/settings`);
  return res.json();
}

export async function setModelKey(
  apiKey: string,
): Promise<{ ok: boolean; error?: string; has_key?: boolean; source?: string }> {
  const res = await fetch(`${httpBase()}/v1/settings/model-key`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
  return res.json();
}

export async function setDefaultModel(
  model: string,
): Promise<{ ok: boolean; error?: string; model?: string }> {
  const res = await fetch(`${httpBase()}/v1/settings/default-model`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  return res.json();
}

export async function addModel(model: string): Promise<ModelSettings & { ok: boolean; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/settings/models/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  return res.json();
}

export async function removeModel(model: string): Promise<ModelSettings & { ok: boolean }> {
  const res = await fetch(`${httpBase()}/v1/settings/models/remove`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  return res.json();
}

export async function setOnboarded(value: boolean): Promise<{ ok: boolean; onboarded: boolean }> {
  const res = await fetch(`${httpBase()}/v1/settings/onboarded`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  return res.json();
}

// -- model providers (OpenAI, Ollama, …) --------------------------------------
export interface ProviderField {
  key: string;
  label: string;
  secret: boolean;
  required: boolean;
  help: string;
  placeholder: string;
  default?: string; // pre-filled editable value (e.g. an OpenAI-compatible vendor's endpoint)
  // Non-empty → segmented choice, not a text input. tag = tiny badge ("Easiest");
  // desc = one-liner atop the method panel; command = copyable terminal command.
  choices?: { value: string; label: string; tag?: string; desc?: string; command?: string }[];
  show_when?: Record<string, string> | null; // render only while these fields hold these values
}

export interface ProviderInfo {
  name: string;
  title: string;
  needs_key: boolean;
  fields: ProviderField[];
  configured: boolean;
  values: Record<string, string>; // non-secret stored values (e.g. base_url), for prefilling
  suggested_models: string[]; // bare model-name suggestions for the "add model" datalist
  recommended_model: string | null; // pre-filled default for this provider (e.g. qwen3-coder:30b)
  blurb?: string; // one-line note under the title ("Uses X's OpenAI-compatible API…")
  // True → reachable over the plain OpenAI-compatible HTTP API, so consumers that only speak
  // that dialect (Document Translation's BabelDOC engine) can drive it. Native-SDK providers
  // (Anthropic, Gemini, Bedrock, Vertex) and the Responses-native Relay are false.
  openai_compatible?: boolean;
  key_set_at?: string | null; // ISO date the key was last (re)saved — absent for env-only config
  last_used_at?: number | null; // epoch secs the provider last served a completion
}

export async function getProviders(): Promise<ProviderInfo[]> {
  const res = await fetch(`${httpBase()}/v1/providers`);
  return res.json();
}

export async function setProvider(
  name: string,
  fields: Record<string, string>,
): Promise<{ ok: boolean; error?: string; provider?: string; recommended_model?: string | null }> {
  const res = await fetch(`${httpBase()}/v1/providers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, fields }),
  });
  return res.json();
}

/** Forget a provider's stored config (Settings ▸ Models "Remove key…"). */
export async function removeProvider(name: string): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/providers/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  return res.json();
}

/** Live read-only credential check (does NOT save the key). Triggered by the user's "Test" click. */
export async function verifyProvider(
  name: string,
  fields: Record<string, string>,
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/providers/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, fields }),
  });
  return res.json();
}

/** Client-side provider guess from an API key's shape (mirrors the server's detect_provider). */
export function detectProvider(apiKey: string): string | null {
  const key = (apiKey || "").trim();
  if (!key) return null;
  if (key.startsWith("sk-ant-")) return "anthropic";
  if (key.startsWith("sk-or-")) return "openrouter";
  if (key.startsWith("AIza")) return "gemini";
  if (key.startsWith("sk-") || key.startsWith("sk_")) return "openai";
  return null;
}

// -- super-agent --------------------------------------------------------------
export interface RecentSender {
  user_id: string;
  user_name: string | null;
  chat_id: string;
  chat_type: string;
  target: string;
  authorized: boolean;
  team_id?: string | null; // workspace (managed relay); null on manual Socket Mode
}

// -- direct-message routing ---------------------------------------------------
export async function getDmRoute(): Promise<string | null> {
  const res = await fetch(`${httpBase()}/v1/messaging/dm-route`);
  return (await res.json()).dm_session ?? null;
}

export async function setDmRoute(sessionId: string): Promise<{ ok: boolean; dm_session: string | null }> {
  const res = await fetch(`${httpBase()}/v1/messaging/dm-route`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  return res.json();
}

// -- automations (scheduled tasks) --------------------------------------------
export interface Automation {
  id: string;
  title: string;
  instructions: string;
  schedule: string;
  schedule_raw?: { kind: string; cron?: string | null; fire_at?: string | null; timezone?: string };
  workspace: string;
  agent: string;
  enabled: boolean;
  next_run: number | null;
  last_run: number | null;
  last_status: string | null;
  run_count: number;
  notify_on_completion: boolean;
  // UX-023 sidebar badges: runs started since the user last opened this automation's
  // detail; `unseen_failed` = the newest unseen run errored (danger tint).
  unseen_runs?: number;
  unseen_failed?: boolean;
  seen_runs_at?: number;
  // Standing scoped approvals (§25): target-bound rules this automation may exercise
  // without asking. `entry` is the raw record entry — the revoke handle; `target` is
  // null for legacy name-only entries.
  always_allowed: { entry: string; tool: string; target: string | null }[];
}

export interface AutomationRun {
  run_id: string;
  task_id: string;
  session_id: string;
  started_at: number;
  finished_at: number | null;
  status: string;
  result_text: string | null;
  artifacts: string[];
  error: string | null;
  trigger: string;
}

export async function getAutomations(): Promise<Automation[]> {
  const res = await fetch(`${httpBase()}/v1/automations`);
  return (await res.json()).tasks ?? [];
}

// Fired after any automation mutation the sidebar should reflect immediately
// (mark-seen, create, delete) — its poll covers the rest.
export const AUTOMATIONS_CHANGED = "coworker:automations-changed";
export function announceAutomationsChanged() {
  window.dispatchEvent(new CustomEvent(AUTOMATIONS_CHANGED));
}

/** App-wide event stream (/ws/events): session-independent server pushes — today
 * automation_run_started (the UX-026 toast). Quietly reconnects while the app is
 * open; the returned cleanup stops it for good. */
export function connectEvents(
  onEvent: (msg: { type: string; data?: Record<string, unknown> }) => void
): () => void {
  let ws: WebSocket | null = null;
  let timer: number | null = null;
  let closed = false;
  const open = () => {
    if (closed) return;
    ws = openWebSocket(`${wsBase()}/ws/events`);
    ws.onmessage = (e) => {
      try {
        onEvent(JSON.parse(e.data));
      } catch {
        /* malformed frame — ignore */
      }
    };
    ws.onclose = () => {
      if (!closed) timer = window.setTimeout(open, 5000);
    };
  };
  open();
  return () => {
    closed = true;
    if (timer !== null) window.clearTimeout(timer);
    ws?.close();
  };
}

/** Advance the automation's seen mark — clears its unseen-runs badge (UX-023). */
export async function markAutomationSeen(id: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${httpBase()}/v1/automations/${id}/seen`, { method: "POST" });
  return res.json();
}

export async function createAutomation(payload: {
  title: string;
  instructions: string;
  cron?: string;
  fire_at?: string;
  timezone?: string;
  // §25 standing grants (the creating surface rendered them; submit IS the consent).
  // Only target-bound write entries survive server-side validation.
  permissions?: { tool: string; target: string; access: "read" | "write" }[];
}): Promise<{ ok: boolean; error?: string; task?: Automation }> {
  const res = await fetch(`${httpBase()}/v1/automations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function getAutomation(id: string): Promise<{ task: Automation; runs: AutomationRun[] }> {
  const res = await fetch(`${httpBase()}/v1/automations/${encodeURIComponent(id)}`);
  return res.json();
}

export async function updateAutomation(id: string, changes: Record<string, any>) {
  const res = await fetch(`${httpBase()}/v1/automations/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
  return res.json();
}

export async function deleteAutomation(id: string) {
  const res = await fetch(`${httpBase()}/v1/automations/${encodeURIComponent(id)}`, { method: "DELETE" });
  return res.json();
}

export interface PreparedRun {
  ok: boolean;
  error?: string;
  run_id: string;
  session_id: string;
  workspace: string;
  agent: string;
  prompt: string;
}

/** Prepare a live manual run: returns the session to open + the opening prompt to send. */
export async function runAutomation(id: string): Promise<PreparedRun> {
  const res = await fetch(`${httpBase()}/v1/automations/${encodeURIComponent(id)}/run`, { method: "POST" });
  return res.json();
}

/** Mark a manual run complete after its first turn finished. */
export async function finalizeAutomationRun(id: string, runId: string) {
  const res = await fetch(
    `${httpBase()}/v1/automations/${encodeURIComponent(id)}/runs/${encodeURIComponent(runId)}/finalize`,
    { method: "POST" },
  );
  return res.json();
}

export async function allowUser(
  name: string,
  userId: string,
  teamId?: string | null,
  displayName?: string,
) {
  const res = await fetch(`${httpBase()}/v1/connectors/${encodeURIComponent(name)}/allow`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      ...(teamId ? { team_id: teamId } : {}),
      // Directory picks carry the display name so the chip is readable at once.
      ...(displayName ? { name: displayName } : {}),
    }),
  });
  return res.json();
}

// One workspace member from the roster (people picker; users:read, cached locally).
export interface SlackMember {
  id: string;
  name: string;
  handle: string;
  guest: boolean;
}

// One channel from the workspace roster. Private channels appear only where the
// bot is a member (Slack API constraint); is_member=false → "invite @OpenWorker" hint.
export interface SlackChannelEntry {
  id: string;
  name: string;
  is_private: boolean;
  is_member: boolean;
}

/** Workspace member roster for the people picker (teamId "default" = manual Socket Mode). */
export async function getSlackDirectory(
  teamId: string,
  q = "",
): Promise<{ ok: boolean; error?: string; members?: SlackMember[] }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/slack/workspaces/${encodeURIComponent(teamId)}/directory?q=${encodeURIComponent(q)}`,
  );
  return res.json();
}

/** Channel roster for the channel typeahead (name → id resolution). */
export async function getSlackChannels(
  teamId: string,
  q = "",
): Promise<{ ok: boolean; error?: string; channels?: SlackChannelEntry[] }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/slack/workspaces/${encodeURIComponent(teamId)}/channels?q=${encodeURIComponent(q)}`,
  );
  return res.json();
}

/** Resolve a parked unauthorized message (§19): dismiss / allow / allow_deliver. */
export async function resolveUnauthorized(
  name: string,
  itemId: string,
  action: "dismiss" | "allow" | "allow_deliver",
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/${encodeURIComponent(name)}/unauthorized/${encodeURIComponent(itemId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    },
  );
  return res.json();
}

export async function disallowUser(name: string, userId: string, teamId?: string | null) {
  const res = await fetch(`${httpBase()}/v1/connectors/${encodeURIComponent(name)}/disallow`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(teamId ? { user_id: userId, team_id: teamId } : { user_id: userId }),
  });
  return res.json();
}

export async function addSlackApprovalOwner(
  userId: string,
  displayName?: string,
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/connectors/slack/approval-owners/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      ...(displayName ? { name: displayName } : {}),
    }),
  });
  return res.json();
}

export async function removeSlackApprovalOwner(
  userId: string,
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/connectors/slack/approval-owners/remove`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });
  return res.json();
}

/** Stop relaying one managed Slack workspace (the app stays installed in Slack). */
export async function disconnectSlackWorkspace(teamId: string): Promise<{ ok: boolean; error?: string; remaining_workspaces?: number }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/slack/workspaces/${encodeURIComponent(teamId)}/disconnect`,
    { method: "POST" },
  );
  return res.json();
}

/** Drop ONE Gmail mailbox; the default pointer moves to the next account. */
export async function disconnectGmailAccount(email: string): Promise<{ ok: boolean; error?: string; remaining_accounts?: number }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/gmail/accounts/${encodeURIComponent(email)}/disconnect`,
    { method: "POST" },
  );
  return res.json();
}

export async function setGmailDefaultAccount(email: string): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/gmail/accounts/${encodeURIComponent(email)}/default`,
    { method: "POST" },
  );
  return res.json();
}

/** Drop ONE Google Calendar account; the default pointer moves to the next one. */
export async function disconnectGcalAccount(email: string): Promise<{ ok: boolean; error?: string; remaining_accounts?: number }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/google_calendar/accounts/${encodeURIComponent(email)}/disconnect`,
    { method: "POST" },
  );
  return res.json();
}

export async function setGcalDefaultAccount(email: string): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/google_calendar/accounts/${encodeURIComponent(email)}/default`,
    { method: "POST" },
  );
  return res.json();
}

/** Drop ONE account of a generic multi-account connector (notion, attio,
 * posthog, …); the default pointer moves to the next account. */
export async function disconnectAccount(connector: string, accountId: string): Promise<{ ok: boolean; error?: string; remaining_accounts?: number }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/${encodeURIComponent(connector)}/accounts/${encodeURIComponent(accountId)}/disconnect`,
    { method: "POST" },
  );
  return res.json();
}

export async function setDefaultAccount(connector: string, accountId: string): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/${encodeURIComponent(connector)}/accounts/${encodeURIComponent(accountId)}/default`,
    { method: "POST" },
  );
  return res.json();
}

/** Replace the "Never show agents" lists (senders and/or labels; omit to keep). */
export async function setGmailFilters(filters: { senders?: string[]; labels?: string[] }): Promise<{ ok: boolean; filters?: GmailFilters; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/connectors/gmail/filters`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(filters),
  });
  return res.json();
}

// GitHub relay health, the Slack three-layer shape: shared relay socket /
// cloud sign-in / per-installation token health (+ missed-event counts).
export interface GithubStatus {
  ok: boolean;
  mode: string;
  relay: { state: string; reconnects: number; last_event_at: number | null; last_error: string };
  signed_in: boolean;
  installs: Record<string, { token_ok: boolean }>;
  missed: Record<string, number>;
}

export async function getGithubStatus(): Promise<GithubStatus> {
  const res = await fetch(`${httpBase()}/v1/connectors/github/status`);
  return res.json();
}

/** Stop relaying ONE GitHub App installation to this computer. */
export async function disconnectGithubInstallation(installationId: string): Promise<{ ok: boolean; error?: string; remaining_installs?: number }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/github/installations/${encodeURIComponent(installationId)}/disconnect`,
    { method: "POST" },
  );
  return res.json();
}

/** Drop ONE HubSpot portal; the default pointer moves to the next portal. */
export async function disconnectHubSpotPortal(hubId: string): Promise<{ ok: boolean; error?: string; remaining_portals?: number }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/hubspot/portals/${encodeURIComponent(hubId)}/disconnect`,
    { method: "POST" },
  );
  return res.json();
}

export async function setHubSpotDefaultPortal(hubId: string): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(
    `${httpBase()}/v1/connectors/hubspot/portals/${encodeURIComponent(hubId)}/default`,
    { method: "POST" },
  );
  return res.json();
}

/** Replace the hidden-fields denylist (properties stripped from agent reads). */
export async function setHubSpotHiddenFields(fields: string[]): Promise<{ ok: boolean; hidden_fields?: string[]; error?: string }> {
  const res = await fetch(`${httpBase()}/v1/connectors/hubspot/hidden-fields`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hidden_fields: fields }),
  });
  return res.json();
}

/** Slack health, three honest layers: relay socket / cloud sign-in / per-team tokens. */
export interface SlackStatus {
  mode: string; // "relay" | "" (manual/off)
  relay: {
    state: "live" | "reconnecting" | "offline";
    reconnects: number;
    last_event_at: number | null;
    last_error: string;
  };
  signed_in: boolean;
  teams: Record<string, { token_ok: boolean }>;
}

export async function getSlackStatus(): Promise<SlackStatus> {
  const res = await fetch(`${httpBase()}/v1/connectors/slack/status`);
  return res.json();
}

export type Handlers = {
  onEvent: (event: WsEvent) => void;
  onOpen?: () => void;
  onClose?: () => void;
};

export class Session {
  private ws: WebSocket;
  // Payloads sent before the socket finished opening, replayed on `onopen`. Belt-and-suspenders
  // against the first message being dropped if the user sends in the connect window.
  private outbox: object[] = [];

  constructor(sessionId: string, workspace: string, agent: string, handlers: Handlers) {
    const q = `?workspace=${encodeURIComponent(workspace)}&agent=${encodeURIComponent(agent)}`;
    this.ws = openWebSocket(`${wsBase()}/ws/session/${sessionId}${q}`);
    this.ws.onmessage = (e) => handlers.onEvent(JSON.parse(e.data));
    this.ws.onopen = () => {
      this.flush();
      handlers.onOpen?.();
    };
    this.ws.onclose = () => handlers.onClose?.();
  }

  private flush() {
    if (this.ws.readyState !== WebSocket.OPEN) return;
    const pending = this.outbox;
    this.outbox = [];
    for (const p of pending) this.ws.send(JSON.stringify(p));
  }

  private send(payload: object) {
    if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(payload));
    // Still connecting: queue and flush on open rather than silently dropping.
    else if (this.ws.readyState === WebSocket.CONNECTING) this.outbox.push(payload);
  }

  /** `model` = the composer's CURRENT selection, carried on every message so the turn uses
   * exactly what the user sees — immune to set_model races across reconnects (a new cowork
   * session always reconnects once to adopt its scratch dir, which could drop a queued
   * set_model and leave the engine on a stale/resumed model; found 2026-07-04). */
  userMessage(text: string, attachments?: unknown[], model?: string) {
    this.send({
      type: "user_message",
      text,
      ...(model ? { model } : {}),
      ...(attachments?.length ? { attachments } : {}),
    });
  }

  approve(decision: string) {
    this.send({ type: "approval", decision });
  }

  // Reply to a `request_directory` prompt: grant a folder (with access level) or decline.
  respondDirectory(granted: boolean, path?: string, writable?: boolean) {
    this.send({ type: "directory_response", granted, ...(path ? { path } : {}), writable: !!writable });
  }

  // Reply to a `propose_plan` prompt: approve (choosing the execution mode) or reject with feedback.
  respondPlan(approved: boolean, mode?: string, feedback?: string) {
    this.send({
      type: "plan_response",
      approved,
      ...(mode ? { mode } : {}),
      ...(feedback ? { feedback } : {}),
    });
  }

  // Answer a live `ask_user` prompt (attended sessions; unattended ones answer via the Inbox).
  respondQuestion(answer: string) {
    this.send({ type: "question_response", answer });
  }

  interrupt() {
    this.send({ type: "interrupt" });
  }

  // Re-run a turn that ended in a provider error — no new user message; the server
  // guards on the history tail so a stray frame is a no-op.
  retry() {
    this.send({ type: "retry" });
  }

  setMode(mode: string) {
    this.send({ type: "set_mode", mode });
  }

  setModel(model: string) {
    this.send({ type: "set_model", model });
  }

  close() {
    // Detach before closing: this socket's async `close` event may land AFTER the
    // successor session's `open` (observed when switching into an automation-run
    // session), and a torn-down socket must not clobber the new one's connected state.
    this.ws.onopen = null;
    this.ws.onmessage = null;
    this.ws.onclose = null;
    this.ws.close();
  }
}

/* ------------------------------------------------------------------ document translation

   The BabelDOC-backed translation module. Two channels, mirroring Discovery: a cursor-polled
   append-only event log for structured progress, and an SSE tail for raw runner output. The
   stage list and the event shapes below are BabelDOC's own contract (TRANSLATE_STAGES /
   async_translate), so the visualization is driven by the real stream rather than a reshaping. */

export interface TranslationSettingsValues {
  lang_in: string;
  lang_out: string;
  /** Which configured provider (Settings ▸ Models) supplies the key + endpoint. "" = the
      OpenAI slot: env OPENAI_API_KEY, else the saved OpenAI key. */
  provider: string;
  openai_model: string;
  openai_base_url: string;
  qps: number;
  pool_max_workers: number;
  ignore_cache: boolean;
  pages: string;
  only_include_translated_page: boolean;
  max_pages_per_part: number;
  watermark_output_mode: string;
  no_dual: boolean;
  no_mono: boolean;
  use_alternating_pages_dual: boolean;
  dual_translate_first: boolean;
  split_short_lines: boolean;
  short_line_split_factor: number;
  translate_table_text: boolean;
  merge_alternating_line_numbers: boolean;
  remove_non_formula_lines: boolean;
  skip_form_render: boolean;
  skip_curve_render: boolean;
  enhance_compatibility: boolean;
  skip_clean: boolean;
  disable_rich_text_translate: boolean;
  skip_scanned_detection: boolean;
  auto_enable_ocr_workaround: boolean;
  ocr_workaround: boolean;
  primary_font_family: string;
  formular_font_pattern: string;
  formular_char_pattern: string;
  auto_extract_glossary: boolean;
  save_auto_extracted_glossary: boolean;
  min_text_length: number;
  custom_system_prompt: string;
}

export interface TranslationParameterMeta {
  type: "boolean" | "integer" | "number" | "string" | "enum";
  description?: string;
  values?: string[];
  minimum?: number;
  maximum?: number;
}

export interface TranslationSettingsDocument {
  schema_version: number;
  values: TranslationSettingsValues;
  defaults: TranslationSettingsValues;
  parameters: Record<string, TranslationParameterMeta>;
}

export interface TranslationDocument {
  document_id: string;
  filename: string;
  source_path: string;
  size: number;
  sha256: string;
  pages: number | null;
  bundle_dir: string;
}

export interface TranslationArtifact {
  name: string;
  role: "source" | "mono" | "dual" | "glossary" | "log";
  size: number;
  path: string;
}

export interface TranslationStage {
  name: string;
  weight: number;
}

export type TranslationRunState = "queued" | "running" | "done" | "error" | "cancelled";

export interface TranslationRun {
  run_id: string;
  document_id: string;
  filename: string;
  source_path: string;
  bundle_dir: string;
  state: TranslationRunState;
  stage: string | null;
  stage_index: number;
  stage_total_count: number;
  stage_current: number;
  stage_total: number;
  stage_progress: number;
  overall_progress: number;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  elapsed_seconds: number;
  error: string | null;
  lang_in: string;
  lang_out: string;
  stages: TranslationStage[];
  artifacts: TranslationArtifact[];
  result: Record<string, unknown> | null;
}

export interface TranslationRunEvent {
  sequence: number;
  at: number;
  type: string;
  stage?: string;
  stage_progress?: number;
  stage_current?: number;
  stage_total?: number;
  overall_progress?: number;
  message?: string;
  [key: string]: unknown;
}

export interface TranslationUploadFile {
  filename: string;
  content_base64: string;
  size: number;
}

async function translationRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${httpBase()}${path}`, init);
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    const raw = detail?.detail?.message ?? detail?.detail ?? detail?.message;
    const message = typeof raw === "string" ? raw : `Translation request failed (${res.status})`;
    const error = new Error(message) as Error & { status?: number; violations?: unknown };
    error.status = res.status;
    error.violations = detail?.detail?.violations;
    throw error;
  }
  return (await res.json()) as T;
}

const jsonBody = (payload: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});

export const getTranslationSettings = (): Promise<TranslationSettingsDocument> =>
  translationRequest<TranslationSettingsDocument>("/v1/translation/settings");

export const setTranslationSettings = (
  values: Partial<TranslationSettingsValues>,
): Promise<TranslationSettingsDocument> =>
  translationRequest<TranslationSettingsDocument>("/v1/translation/settings", {
    ...jsonBody({ values }),
    method: "PUT",
  });

/** Register documents to translate: uploaded bytes, already-local absolute paths, or both. */
export const registerTranslationDocuments = (payload: {
  files?: TranslationUploadFile[];
  paths?: string[];
}): Promise<{ documents: TranslationDocument[] }> =>
  translationRequest<{ documents: TranslationDocument[] }>("/v1/translation/documents", jsonBody(payload));

export const listTranslationDocuments = (): Promise<{ documents: TranslationDocument[] }> =>
  translationRequest<{ documents: TranslationDocument[] }>("/v1/translation/documents");

/** What removing one queue entry actually deleted, so the UI can say it plainly. */
export interface TranslationDocumentRemoval {
  document_id: string;
  filename: string;
  removed_runs: number;
  cancelled_runs: string[];
  /** True → an uploaded copy this module staged was deleted. A path-registered document,
      and any bundle holding finished artifacts, is always left alone. */
  source_deleted: boolean;
  bundle_dir: string;
}

/** Forget one queued document: cancels its active run, drops its run history, and deletes
    only the staged copy this module created. Never touches a user's own file on disk. */
export const forgetTranslationDocument = (documentId: string): Promise<TranslationDocumentRemoval> =>
  translationRequest<TranslationDocumentRemoval>(
    `/v1/translation/documents/${encodeURIComponent(documentId)}`,
    { method: "DELETE" },
  );

export const startTranslationRuns = (
  documentIds: string[],
  overrides?: Partial<TranslationSettingsValues>,
): Promise<{ runs: TranslationRun[] }> =>
  translationRequest<{ runs: TranslationRun[] }>(
    "/v1/translation/runs",
    jsonBody({ document_ids: documentIds, ...(overrides ? { overrides } : {}) }),
  );

export const listTranslationRuns = (): Promise<{ runs: TranslationRun[] }> =>
  translationRequest<{ runs: TranslationRun[] }>("/v1/translation/runs");

export const getTranslationRun = (runId: string): Promise<TranslationRun> =>
  translationRequest<TranslationRun>(`/v1/translation/runs/${encodeURIComponent(runId)}`);

export const cancelTranslationRun = (runId: string): Promise<TranslationRun> =>
  translationRequest<TranslationRun>(`/v1/translation/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });

export const getTranslationRunEvents = (
  runId: string,
  after = 0,
): Promise<{
  run_id: string;
  events: TranslationRunEvent[];
  oldest_sequence: number | null;
  latest_sequence: number;
  truncated_before_sequence: number;
}> =>
  translationRequest(`/v1/translation/runs/${encodeURIComponent(runId)}/events?after=${Math.max(0, after)}`);

/** Absolute URL of one artifact inside a run's bundle — for preview iframes and downloads. */
export const translationArtifactUrl = (runId: string, name: string): string =>
  `${httpBase()}/v1/translation/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(name)}`;

/** Fetch an artifact as a blob URL so authenticated previews work in an <iframe>/<object>. */
export async function fetchTranslationArtifactBlobUrl(runId: string, name: string): Promise<string> {
  const res = await fetch(translationArtifactUrl(runId, name));
  if (!res.ok) throw new Error(`Artifact could not be loaded (${res.status})`);
  return URL.createObjectURL(await res.blob());
}

/** SSE tail of a run's raw log. Mirrors streamDiscoveryLaunchLog's bare `data:` framing. */
export async function streamTranslationRunLog(
  runId: string,
  onLine: (line: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${httpBase()}/v1/translation/runs/${encodeURIComponent(runId)}/logs/stream`, { signal });
  if (!res.ok) throw new Error(`Translation log stream failed (${res.status})`);
  if (!res.body) return;

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const emitBlock = (block: string) => {
    const dataLines = block.split(/\r?\n/).filter((line) => line.startsWith("data:"));
    if (dataLines.length) onLine(dataLines.map((line) => line.slice(5).replace(/^ /, "")).join("\n"));
  };
  const consume = (chunk: string) => {
    buffer += chunk;
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";
    for (const block of blocks) emitBlock(block);
  };
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      consume(decoder.decode(value, { stream: true }));
    }
    consume(decoder.decode());
    if (buffer.trim()) emitBlock(buffer);
  } finally {
    reader.releaseLock();
  }
}
