export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail: string | null = null,
  ) {
    super(message);
  }
}

type TokenGetter = () => Promise<string | null>;

async function authHeaders(getAccessToken: TokenGetter, json: boolean): Promise<Record<string, string>> {
  const headers: Record<string, string> = { Accept: json ? "application/json" : "*/*" };
  if (json) {
    headers["Content-Type"] = "application/json";
  }
  const token = await getAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

/** The server's `detail` when it is a plain message (409 / 400 / 403 / 404), else null. */
async function errorDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}

async function send(method: string, path: string, body: unknown, getAccessToken: TokenGetter): Promise<Response> {
  const headers = await authHeaders(getAccessToken, body !== undefined);
  const response = await fetch(`/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await errorDetail(response);
    throw new ApiError(response.status, detail ?? `${response.status} ${response.statusText}`, detail);
  }
  return response;
}

export async function apiGet<T>(path: string, getAccessToken: TokenGetter): Promise<T> {
  return (await (await send("GET", path, undefined, getAccessToken)).json()) as T;
}

export async function apiPost<T>(path: string, body: unknown, getAccessToken: TokenGetter): Promise<T> {
  return (await (await send("POST", path, body ?? {}, getAccessToken)).json()) as T;
}

export async function apiPut<T>(path: string, body: unknown, getAccessToken: TokenGetter): Promise<T> {
  return (await (await send("PUT", path, body, getAccessToken)).json()) as T;
}

export async function apiGetText(path: string, getAccessToken: TokenGetter): Promise<string> {
  return (await send("GET", path, undefined, getAccessToken)).text();
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

/** A file download (export): the body as a Blob plus the server's suggested filename. */
export async function apiGetFile(path: string, getAccessToken: TokenGetter): Promise<{ blob: Blob; filename: string | null }> {
  const response = await send("GET", path, undefined, getAccessToken);
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  return { blob: await response.blob(), filename: match ? match[1] : null };
}
