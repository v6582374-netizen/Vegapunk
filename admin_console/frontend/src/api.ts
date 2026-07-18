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
    let detail: string | undefined;
    try {
      detail = ((await response.json()) as { detail?: string }).detail;
    } catch {
      detail = undefined;
    }
    throw new Error(detail ?? `Request to ${url} failed: ${response.status}`);
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
