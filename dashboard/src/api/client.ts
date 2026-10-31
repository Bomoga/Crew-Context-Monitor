import type {
  CheckinRequest,
  CheckinResponse,
  EarthQueue,
  EarthQueueItem,
  EnrollRequest,
  Events,
  History,
  ResetRequest,
  Settings,
  SettingsUpdate,
  Status,
} from "./types.gen";
import type { ContractKind } from "./validate";

/** Thrown for any non-2xx response; `detail` is the API's JSON `detail` when there is one. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

async function reportViolations(kind: ContractKind, path: string, data: unknown) {
  try {
    const { contractViolations } = await import("./validate");
    const problems = contractViolations(kind, data);
    if (problems.length > 0) {
      console.error(`contract violation in ${path} (${kind}):`, problems);
    }
  } catch (e) {
    console.error(`could not check ${path} against the contract:`, e);
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; signal?: AbortSignal; kind?: ContractKind } = {},
): Promise<T> {
  const { method = "GET", body, signal, kind } = options;
  const response = await fetch(path, {
    method,
    signal,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const json = (await response.json()) as { detail?: unknown };
      if (typeof json.detail === "string") detail = json.detail;
    } catch {
      // keep the status text
    }
    throw new ApiError(response.status, detail);
  }
  const data = (await response.json()) as T;
  // Dev builds check every response against the contract without delaying it; production
  // builds drop this branch.
  if (import.meta.env.DEV && kind) void reportViolations(kind, path, data);
  return data;
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export interface HistoryParams {
  metric: History["metric"];
  crew?: string | null;
  hours?: number;
  step?: number;
}

export const api = {
  status: (signal?: AbortSignal) => request<Status>("/api/status", { signal, kind: "status" }),
  history: ({ metric, crew, hours, step }: HistoryParams, signal?: AbortSignal) =>
    request<History>(`/api/history${query({ metric, crew: crew ?? undefined, hours, step })}`, {
      signal,
      kind: "history",
    }),
  events: (params: { since?: number; limit?: number } = {}, signal?: AbortSignal) =>
    request<Events>(`/api/events${query(params)}`, { signal, kind: "events" }),
  earthQueue: (signal?: AbortSignal) =>
    request<EarthQueue>("/api/earth-queue", { signal, kind: "earth_queue" }),
  approve: (id: string) =>
    request<EarthQueueItem>(`/api/earth-queue/${encodeURIComponent(id)}/approve`, {
      method: "POST",
      kind: "earth_queue_item",
    }),
  settings: (signal?: AbortSignal) =>
    request<Settings>("/api/settings", { signal, kind: "settings" }),
  putAutoApprove: (body: SettingsUpdate) =>
    request<Settings>("/api/settings", { method: "PUT", body, kind: "settings" }),
  enroll: (body: EnrollRequest) =>
    request<Settings>("/api/settings/enroll", { method: "POST", body, kind: "settings" }),
  resetBaseline: (body: ResetRequest) =>
    request<Settings>("/api/settings/reset-baseline", { method: "POST", body, kind: "settings" }),
  checkin: (body: CheckinRequest) =>
    request<CheckinResponse>("/api/checkin", {
      method: "POST",
      body,
      kind: "checkin_response",
    }),
};
