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
