export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiGet<T>(
  path: string,
  getAccessToken: () => Promise<string | null>,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = await getAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`/api${path}`, { headers });
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function apiPost<T>(
  path: string,
  body: unknown,
  getAccessToken: () => Promise<string | null>,
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  const token = await getAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`/api${path}`, { method: "POST", headers, body: JSON.stringify(body) });
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export interface HealthResponse {
  status: "ok";
  version: string;
  database: "ok" | "unavailable";
}

export interface CurrentUser {
  user_id: string;
  name: string;
  email: string | null;
  roles: string[];
  auth_mode: "entra" | "dev_bypass";
}
