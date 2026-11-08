const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const KEY = "wz_token";

export function getToken(): string | null { try { return sessionStorage.getItem(KEY); } catch { return null; } }
export function setToken(t: string | null) { try { t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY); } catch {} }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/v1${path}`, {
      method: opts.method || "GET",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the API");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const d = data?.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((x: any) => x.msg).join("; ") : res.statusText;
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

export type Me = { id: number; display_name: string; email: string | null; language: string; role: { key: string; name: string; rank: number } | null; permissions: string[]; auth_mode: string };

/** multipart upload (the browser sets the boundary, so no Content-Type header here) */
export async function upload<T = any>(path: string, form: FormData): Promise<T> {
  const token = getToken();
  let res: Response;
  try { res = await fetch(`${BASE}/api/v1${path}`, { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: form }); }
  catch { throw new ApiError(0, "Cannot reach the API"); }
  const data = await res.json().catch(() => null);
  if (!res.ok) { const d = data?.detail; throw new ApiError(res.status, typeof d === "string" ? d : Array.isArray(d) ? d.map((x: any) => x.msg).join("; ") : res.statusText); }
  return data as T;
}

/** authenticated download: the file is fetched with the bearer token, then saved from memory (a plain link could not send the token) */
export async function download(path: string, filename: string): Promise<void> {
  const token = getToken();
  const res = await fetch(`${BASE}/api/v1${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) { const d = await res.json().catch(() => null); throw new ApiError(res.status, typeof d?.detail === "string" ? d.detail : res.statusText); }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
