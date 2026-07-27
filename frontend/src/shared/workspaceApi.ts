export interface DiscoverySource {
  name: string;
  kind: "reference" | "baseline_code";
  extension: string;
}

export interface DiscoveryPreparationRecord {
  id: string;
  created_at: string;
  research_text: string;
  sources: DiscoverySource[];
  revisions?: FormattedDiscoveryInputRevision[];
}

export interface FormattedDiscoveryInputRevision {
  id: string;
  created_at: string;
  formatted_input: string;
}

export interface DiscoveryInputConversion {
  preparation_id: string;
  formatted_input: string;
  model_id: string;
}

export interface DiscoveryLaunchSummary {
  id: string;
  task: string;
  started_at: string;
  state: string;
}

export interface DiscoveryLaunchStatus {
  state: string;
  stage: string;
  rounds: number;
  total_rounds: number;
  stopped_how: string | null;
  recent_artifacts: { path: string; modified_at: number; size: number }[];
}

export interface DiscoveryArtifactNode {
  path: string;
  name: string;
  kind: "file" | "directory";
  size?: number;
  children?: DiscoveryArtifactNode[];
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
    const message = typeof detail === "string" ? detail : `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export async function fetchDiscoveryPreparations(): Promise<DiscoveryPreparationRecord[]> {
  return (
    await request<{ preparations: DiscoveryPreparationRecord[] }>(
      "/api/workspace/discovery-preparations",
    )
  ).preparations;
}

export async function createDiscoveryPreparation(
  researchText: string,
  sources: File[],
): Promise<DiscoveryPreparationRecord> {
  const form = new FormData();
  form.set("research_text", researchText);
  for (const source of sources) {
    form.append("sources", source);
  }
  return request<DiscoveryPreparationRecord>("/api/workspace/discovery-preparations", {
    method: "POST",
    body: form,
  });
}

export async function convertDiscoveryPreparation(
  preparationId: string,
): Promise<DiscoveryInputConversion> {
  return request<DiscoveryInputConversion>(
    `/api/workspace/discovery-preparations/${preparationId}/conversion`,
    { method: "POST" },
  );
}

export async function updateDiscoveryPreparation(
  preparationId: string,
  researchText: string,
): Promise<DiscoveryPreparationRecord> {
  return request<DiscoveryPreparationRecord>(
    `/api/workspace/discovery-preparations/${preparationId}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ research_text: researchText }),
    },
  );
}

export async function saveFormattedDiscoveryInputRevision(
  preparationId: string,
  formattedInput: string,
): Promise<FormattedDiscoveryInputRevision> {
  return request<FormattedDiscoveryInputRevision>(
    `/api/workspace/discovery-preparations/${preparationId}/revisions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ formatted_input: formattedInput }),
    },
  );
}

export async function fetchDiscoveryLaunches(): Promise<DiscoveryLaunchSummary[]> {
  return (await request<{ launches: DiscoveryLaunchSummary[] }>("/api/workspace/discovery-launches")).launches;
}

export async function submitDiscoveryLaunch(
  preparationId: string,
  revisionId: string,
): Promise<{ launch_id: string; state: string }> {
  return request("/api/workspace/discovery-launches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preparation_id: preparationId, revision_id: revisionId }),
  });
}

export async function fetchDiscoveryLaunchStatus(
  launchId: string,
): Promise<DiscoveryLaunchStatus> {
  return request(`/api/workspace/discovery-launches/${launchId}/status`);
}

export function discoveryLogStreamUrl(launchId: string): string {
  return `/api/workspace/discovery-launches/${launchId}/logs/stream?file=runner.log`;
}

export async function fetchDiscoveryArtifactTree(
  launchId: string,
): Promise<DiscoveryArtifactNode[]> {
  return (
    await request<{ tree: DiscoveryArtifactNode[] }>(
      `/api/workspace/discovery-launches/${launchId}/artifacts/tree`,
    )
  ).tree;
}

export function discoveryArtifactFileUrl(launchId: string, path: string): string {
  return `/api/workspace/discovery-launches/${launchId}/artifacts/file?path=${encodeURIComponent(path)}`;
}

export async function fetchDiscoveryArtifactText(
  launchId: string,
  path: string,
): Promise<string> {
  const response = await fetch(discoveryArtifactFileUrl(launchId, path), {
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error(`无法读取产物 ${path}: ${response.status}`);
  }
  return response.text();
}
