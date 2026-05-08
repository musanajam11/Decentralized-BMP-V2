// Tiny typed fetch wrapper around the backend.
const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

/** Public base URL of the backend, used to build absolute download links. */
export const apiBaseUrl = API_BASE;

const ACCESS_KEY = "dbmp.access";
const REFRESH_KEY = "dbmp.refresh";

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh: string) {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  retry = true,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (tokens.access) headers.Authorization = `Bearer ${tokens.access}`;

  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (resp.status === 401 && retry && tokens.refresh) {
    const refreshed = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokens.refresh }),
    });
    if (refreshed.ok) {
      const data = (await refreshed.json()) as {
        access_token: string;
        refresh_token: string;
      };
      tokens.set(data.access_token, data.refresh_token);
      return request<T>(method, path, body, false);
    }
    tokens.clear();
  }

  if (resp.status === 204) return undefined as unknown as T;
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const j = await resp.json();
      detail = (j.detail as string) ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

export const api = {
  get: <T,>(p: string) => request<T>("GET", p),
  post: <T,>(p: string, body?: unknown) => request<T>("POST", p, body),
  patch: <T,>(p: string, body?: unknown) => request<T>("PATCH", p, body),
  delete: <T,>(p: string) => request<T>("DELETE", p),
};
