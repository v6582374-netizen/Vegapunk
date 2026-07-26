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
