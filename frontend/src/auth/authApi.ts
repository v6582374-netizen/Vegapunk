export interface AdminSession {
  authenticated: boolean;
  username?: string;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = ((await response.json()) as { detail?: unknown }).detail;
    } catch {
      detail = undefined;
    }
    throw new Error(
      typeof detail === "string" ? detail : `请求失败：${response.status}`,
    );
  }
  return (await response.json()) as T;
}

export function fetchAdminSession(): Promise<AdminSession> {
  return request<AdminSession>("/api/auth/me");
}

export function loginAdmin(username: string, password: string): Promise<AdminSession> {
  return request<AdminSession>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logoutAdmin(): Promise<AdminSession> {
  return request<AdminSession>("/api/auth/logout", { method: "POST" });
}
