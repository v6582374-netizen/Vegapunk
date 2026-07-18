export interface LaunchSummary {
  id: string;
  task: string;
  started_at: string;
  state: string;
}

export async function fetchLaunches(): Promise<LaunchSummary[]> {
  const response = await fetch("/api/launches");
  if (!response.ok) {
    throw new Error(`Failed to load launches: ${response.status}`);
  }
  const body = (await response.json()) as { launches: LaunchSummary[] };
  return body.launches;
}
