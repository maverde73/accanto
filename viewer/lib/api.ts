import "server-only";

import { readToken } from "@/lib/session";
import type { Alert, Checkin, LocationPoint, Snapshot, SubjectSummary } from "@/lib/types";

/** Server-side client for the Accanto backend.
 *
 * Everything goes through here so the token stays on the server. The browser
 * never learns the backend's address either.
 */

export const API_URL = process.env.ACCANTO_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class Unauthenticated extends ApiError {
  constructor() {
    super(401, "Sessione scaduta");
    this.name = "Unauthenticated";
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Presence data goes stale in seconds; never serve it from a cache. */
  revalidate?: number | false;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = await readToken();
  if (!token) throw new Unauthenticated();

  const response = await fetch(`${API_URL}/v1${path}`, {
    method: options.method ?? "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
  });

  if (response.status === 401) throw new Unauthenticated();
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Non-JSON error bodies are not worth surfacing verbatim.
  }
  return `Errore ${response.status}`;
}

export async function login(email: string, password: string): Promise<string> {
  const response = await fetch(`${API_URL}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
    cache: "no-store",
  });
  if (!response.ok) throw new ApiError(response.status, "Credenziali non valide");
  const body = (await response.json()) as { access_token: string };
  return body.access_token;
}

export const api = {
  subjects: () => request<SubjectSummary[]>("/subjects"),
  snapshot: (id: string) => request<Snapshot>(`/subjects/${id}/snapshot`),
  latestLocation: (id: string) => request<LocationPoint | null>(`/subjects/${id}/location/latest`),
  alerts: (id: string) => request<Alert[]>(`/subjects/${id}/alerts?limit=20`),
  checkins: (id: string) => request<Checkin[]>(`/subjects/${id}/checkins?limit=5`),
  requestCheckin: (id: string) => request<Checkin>(`/subjects/${id}/checkin`, { method: "POST" }),
  escalate: (id: string, actionType: string, params: Record<string, unknown> = {}) =>
    request<{ id: string; rung: number; status: string }>(`/subjects/${id}/escalate`, {
      method: "POST",
      body: { action_type: actionType, params },
    }),
  setLiveLocation: (id: string, enabled: boolean) =>
    request<{ live: boolean }>(`/subjects/${id}/location/live?enabled=${enabled}`, {
      method: "POST",
    }),
};
