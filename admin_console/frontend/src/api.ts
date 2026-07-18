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

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request to ${url} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchLaunches(): Promise<LaunchSummary[]> {
  return (await getJson<{ launches: LaunchSummary[] }>("/api/launches")).launches;
}

export async function fetchTasks(): Promise<string[]> {
  return (await getJson<{ tasks: string[] }>("/api/tasks")).tasks;
}

export async function fetchQueue(): Promise<QueueEntry[]> {
  return (await getJson<{ entries: QueueEntry[] }>("/api/queue")).entries;
}

export async function submitLaunch(task: string): Promise<QueueEntry> {
  const response = await fetch("/api/queue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task }),
  });
  if (!response.ok) {
    const detail = (await response.json()) as { detail?: string };
    throw new Error(detail.detail ?? `Submit failed: ${response.status}`);
  }
  return (await response.json()) as QueueEntry;
}

export async function cancelQueued(queueId: string): Promise<void> {
  const response = await fetch(`/api/queue/${queueId}`, { method: "DELETE" });
  if (!response.ok) {
    const detail = (await response.json()) as { detail?: string };
    throw new Error(detail.detail ?? `Cancel failed: ${response.status}`);
  }
}
