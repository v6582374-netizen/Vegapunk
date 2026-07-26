export interface LaunchSummary {
  id: string;
  task: string;
  started_at: string;
  state: string;
}

export interface QueueEntry {
  queue_id: string;
  task: string;
  state: string;
  submitted_at: string;
  launch_id: string | null;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin", ...init });
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = ((await response.json()) as { detail?: unknown }).detail;
    } catch {
      detail = undefined;
    }
    const text =
      typeof detail === "string" ? detail : detail === undefined ? undefined : JSON.stringify(detail);
    throw new Error(text ?? `Request to ${url} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchLaunches(): Promise<LaunchSummary[]> {
  return (await request<{ launches: LaunchSummary[] }>("/api/admin/launches")).launches;
}

export interface TaskSummary {
  name: string;
  has_baseline_code: boolean;
  path_mode: "experiment" | "report";
  kind: "auto" | "sci";
}

export async function fetchTasks(): Promise<TaskSummary[]> {
  return (await request<{ tasks: TaskSummary[] }>("/api/admin/tasks")).tasks;
}

export async function createTask(form: FormData): Promise<TaskSummary> {
  return request<TaskSummary>("/api/admin/tasks", { method: "POST", body: form });
}

export async function fetchQueue(): Promise<QueueEntry[]> {
  return (await request<{ entries: QueueEntry[] }>("/api/admin/queue")).entries;
}

export async function submitLaunch(task: string): Promise<QueueEntry> {
  return request<QueueEntry>("/api/admin/queue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task }),
  });
}

export async function cancelQueued(queueId: string): Promise<void> {
  await request<QueueEntry>(`/api/admin/queue/${queueId}`, { method: "DELETE" });
}

export async function gracefulStop(queueId: string): Promise<void> {
  await request<QueueEntry>(`/api/admin/queue/${queueId}/stop`, { method: "POST" });
}

export async function forceKill(queueId: string): Promise<void> {
  await request<QueueEntry>(`/api/admin/queue/${queueId}/kill`, { method: "POST" });
}

export async function resumeLaunch(launchId: string): Promise<QueueEntry> {
  return request<QueueEntry>(`/api/admin/launches/${launchId}/resume`, { method: "POST" });
}

export interface ParameterField {
  path: string;
  description: string;
  type: string;
  ge?: number;
  le?: number;
  gt?: number;
  lt?: number;
}

export interface PromptRecord {
  id: string;
  name: string;
  description: string;
  workflow: string;
  stage: string;
  order: number;
  invocation_type: "single" | "repeated" | "conditional" | "mutually_exclusive";
  mutual_exclusion_group: string | null;
  template_variables: string[];
  required_template_variables: string[];
  file: string;
  text: string;
  source_revision: string;
  chinese_mirror?: ChinesePromptMirror;
}

export interface ChinesePromptMirror {
  state: "ready" | "missing" | "stale";
  file: string;
  text: string | null;
}

export async function fetchPrompts(): Promise<PromptRecord[]> {
  return (await request<{ prompts: PromptRecord[] }>("/api/admin/prompts")).prompts;
}

export async function savePrompt(id: string, text: string): Promise<PromptRecord> {
  return request<PromptRecord>(`/api/admin/prompts/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export async function synchronizePrompt(
  id: string,
  chineseText: string,
  sourceRevision: string,
): Promise<PromptRecord> {
  return request<PromptRecord>(`/api/admin/prompts/${id}/synchronize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chinese_text: chineseText,
      source_revision: sourceRevision,
    }),
  });
}

export interface PromptTranslationInstruction {
  instruction: string;
  configured: boolean;
}

export interface DiscoveryInputConversionPrompt {
  instruction: string;
  configured: boolean;
}

export async function fetchPromptTranslationInstruction(): Promise<PromptTranslationInstruction> {
  return request("/api/admin/prompt-translation-instruction");
}

export async function savePromptTranslationInstruction(
  instruction: string,
): Promise<PromptTranslationInstruction> {
  return request("/api/admin/prompt-translation-instruction", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction }),
  });
}

export async function fetchDiscoveryInputConversionPrompt(): Promise<DiscoveryInputConversionPrompt> {
  return request("/api/admin/discovery-input-conversion-prompt");
}

export async function saveDiscoveryInputConversionPrompt(
  instruction: string,
): Promise<DiscoveryInputConversionPrompt> {
  return request("/api/admin/discovery-input-conversion-prompt", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction }),
  });
}

export interface PromptMirrorBatchAvailability {
  available: boolean;
  reason: string | null;
  model_id: string | null;
}

export interface PromptMirrorBatchItem {
  prompt_id: string;
  name: string;
  state: "pending" | "success" | "failure" | "skipped";
  error: string | null;
}

export interface PromptMirrorBatch {
  id: string;
  state: "running" | "completed";
  items: PromptMirrorBatchItem[];
  progress: {
    total: number;
    pending: number;
    success: number;
    failure: number;
    skipped: number;
  };
}

export async function fetchPromptMirrorBatchAvailability(): Promise<PromptMirrorBatchAvailability> {
  return request("/api/admin/prompt-mirror-batches/availability");
}

export async function startPromptMirrorBatch(): Promise<PromptMirrorBatch> {
  return request("/api/admin/prompt-mirror-batches", { method: "POST" });
}

export async function fetchPromptMirrorBatch(batchId: string): Promise<PromptMirrorBatch> {
  return request(`/api/admin/prompt-mirror-batches/${batchId}`);
}

export async function retryPromptMirrorBatch(batchId: string): Promise<PromptMirrorBatch> {
  return request(`/api/admin/prompt-mirror-batches/${batchId}/retry`, { method: "POST" });
}

export type VerificationStatus =
  | "unverified"
  | "valid"
  | "authentication_failed"
  | "unreachable";

export interface ProviderConnection {
  provider: "relay" | "qwen";
  name: string;
  base_url: string;
  base_url_configurable: boolean;
  credential_configured: boolean;
  credential_source: "vault" | "environment" | "missing";
  environment_variable: string | null;
  verification_status: VerificationStatus;
  model_count: number;
}

export async function fetchProviderConnections(): Promise<ProviderConnection[]> {
  return (
    await request<{ connections: ProviderConnection[] }>(
      "/api/admin/provider-connections",
    )
  ).connections;
}

export async function saveProviderConnection(
  provider: string,
  values: { api_key?: string; base_url?: string },
): Promise<ProviderConnection> {
  return request(`/api/admin/provider-connections/${provider}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
}

export async function revealProviderCredential(
  provider: string,
): Promise<{ api_key: string }> {
  return request(`/api/admin/provider-connections/${provider}/credential/reveal`, {
    method: "POST",
  });
}

export async function verifyProviderConnection(
  provider: string,
): Promise<ProviderConnection> {
  return request(`/api/admin/provider-connections/${provider}/verify`, {
    method: "POST",
  });
}

export async function deleteProviderCredential(
  provider: string,
): Promise<ProviderConnection> {
  return request(`/api/admin/provider-connections/${provider}/credential`, {
    method: "DELETE",
  });
}

export interface ModelOption {
  id: string;
  provider: string;
  model: string;
  capabilities: string[];
}

export interface DefaultConfiguration {
  revision: string;
  bindings: {
    active_text_model: string;
    image_model: string;
    embedding_model: string;
  };
  models: ModelOption[];
  parameter_catalog: ParameterField[];
  parameters: Record<string, unknown>;
  readiness: {
    ready: boolean;
    connections: ProviderConnection[];
  };
}

export async function fetchDefaultConfiguration(): Promise<DefaultConfiguration> {
  return request("/api/admin/default-configuration");
}

export async function saveDefaultConfiguration(values: {
  bindings: DefaultConfiguration["bindings"];
  parameters: Record<string, unknown>;
}): Promise<DefaultConfiguration> {
  return request("/api/admin/default-configuration", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
}

export async function fetchParameters(): Promise<{
  catalog: ParameterField[];
  values: Record<string, unknown>;
}> {
  return request("/api/admin/parameters");
}

export async function saveParameters(
  values: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const body = await request<{ values: Record<string, unknown> }>("/api/admin/parameters", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
  return body.values;
}

export type ModelCatalog = {
  version: number;
  active_text_model: string;
  capability_models: Record<string, string>;
  providers: Record<string, Record<string, unknown>>;
  models: Record<
    string,
    {
      provider: string;
      model: string;
      capabilities: string[];
      protocol?: string;
    }
  >;
  retry?: Record<string, unknown>;
};

export async function fetchModelCatalog(): Promise<ModelCatalog> {
  return request<ModelCatalog>("/api/admin/model-catalog");
}

export async function saveModelCatalog(catalog: ModelCatalog): Promise<ModelCatalog> {
  return request<ModelCatalog>("/api/admin/model-catalog", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(catalog),
  });
}

export interface LaunchStatus {
  state: string;
  stage: string;
  rounds: number;
  recent_artifacts: { path: string; modified_at: number; size: number }[];
}

export async function fetchLaunchStatus(launchId: string): Promise<LaunchStatus> {
  return request(`/api/admin/launches/${launchId}/status`);
}

export function logStreamUrl(launchId: string, file: string): string {
  return `/api/admin/launches/${launchId}/logs/stream?file=${encodeURIComponent(file)}`;
}

export interface ArtifactNode {
  path: string;
  name: string;
  kind: "file" | "directory";
  size?: number;
  children?: ArtifactNode[];
}

export async function fetchArtifactTree(launchId: string): Promise<ArtifactNode[]> {
  return (await request<{ tree: ArtifactNode[] }>(`/api/admin/artifacts/${launchId}/tree`)).tree;
}

export function artifactFileUrl(launchId: string, path: string): string {
  return `/api/admin/artifacts/${launchId}/file?path=${encodeURIComponent(path)}`;
}

export async function fetchArtifactText(launchId: string, path: string): Promise<string> {
  const response = await fetch(artifactFileUrl(launchId, path));
  if (!response.ok) {
    throw new Error(`Failed to load artifact ${path}: ${response.status}`);
  }
  return response.text();
}

export interface TimelineRun {
  id: string;
  path: string;
  outcome: string;
  metrics_path: string | null;
  combined_score: number | null;
}

export interface TimelineCandidate {
  name: string;
  path: string;
  method_path: string | null;
  runs: TimelineRun[];
}

export interface TimelineRound {
  id: string;
  path: string;
  ideas_path: string | null;
  ideas: { name?: string; title?: string; description?: string }[];
  candidates: TimelineCandidate[];
}

export interface LaunchTimeline {
  stage: string;
  rounds: TimelineRound[];
  paper: { path: string | null; present: boolean };
}

export async function fetchLaunchTimeline(launchId: string): Promise<LaunchTimeline> {
  return request(`/api/admin/launches/${launchId}/timeline`);
}

export interface ExperimentRunDetail {
  path: string;
  id: string;
  outcome: string;
  metrics: Record<string, unknown> | null;
  metrics_path: string | null;
  log_path: string | null;
  traceback_path: string | null;
  log_preview: string;
  code_files: { path: string; name: string }[];
  code_diff: string;
}

export async function fetchExperimentRun(
  launchId: string,
  path: string,
): Promise<ExperimentRunDetail> {
  return request(
    `/api/admin/launches/${launchId}/experiment-run?path=${encodeURIComponent(path)}`,
  );
}
