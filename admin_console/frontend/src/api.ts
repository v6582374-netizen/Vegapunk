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
  const response = await fetch(url, init);
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
  return (await request<{ launches: LaunchSummary[] }>("/api/launches")).launches;
}

export async function fetchTasks(): Promise<string[]> {
  return (await request<{ tasks: string[] }>("/api/tasks")).tasks;
}

export async function fetchQueue(): Promise<QueueEntry[]> {
  return (await request<{ entries: QueueEntry[] }>("/api/queue")).entries;
}

export async function submitLaunch(task: string): Promise<QueueEntry> {
  return request<QueueEntry>("/api/queue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task }),
  });
}

export async function cancelQueued(queueId: string): Promise<void> {
  await request<QueueEntry>(`/api/queue/${queueId}`, { method: "DELETE" });
}

export async function gracefulStop(queueId: string): Promise<void> {
  await request<QueueEntry>(`/api/queue/${queueId}/stop`, { method: "POST" });
}

export async function forceKill(queueId: string): Promise<void> {
  await request<QueueEntry>(`/api/queue/${queueId}/kill`, { method: "POST" });
}

export async function resumeLaunch(launchId: string): Promise<QueueEntry> {
  return request<QueueEntry>(`/api/launches/${launchId}/resume`, { method: "POST" });
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

export async function fetchParameters(): Promise<{
  catalog: ParameterField[];
  values: Record<string, unknown>;
}> {
  return request("/api/parameters");
}

export async function saveParameters(
  values: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const body = await request<{ values: Record<string, unknown> }>("/api/parameters", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
  return body.values;
}

export interface LaunchStatus {
  state: string;
  rounds: number;
  recent_artifacts: { path: string; modified_at: number; size: number }[];
}

export async function fetchLaunchStatus(launchId: string): Promise<LaunchStatus> {
  return request(`/api/launches/${launchId}/status`);
}

export function logStreamUrl(launchId: string, file: string): string {
  return `/api/launches/${launchId}/logs/stream?file=${encodeURIComponent(file)}`;
}

export interface ArtifactNode {
  path: string;
  name: string;
  kind: "file" | "directory";
  size?: number;
  children?: ArtifactNode[];
}

export async function fetchArtifactTree(launchId: string): Promise<ArtifactNode[]> {
  return (await request<{ tree: ArtifactNode[] }>(`/api/artifacts/${launchId}/tree`)).tree;
}

export function artifactFileUrl(launchId: string, path: string): string {
  return `/api/artifacts/${launchId}/file?path=${encodeURIComponent(path)}`;
}

export async function fetchArtifactText(launchId: string, path: string): Promise<string> {
  const response = await fetch(artifactFileUrl(launchId, path));
  if (!response.ok) {
    throw new Error(`Failed to load artifact ${path}: ${response.status}`);
  }
  return response.text();
}
