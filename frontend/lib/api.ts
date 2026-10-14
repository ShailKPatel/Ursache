const DEFAULT_API_URL = "http://localhost:8000";

export interface DependencyStatus {
  ok: boolean;
  latency_ms: number;
  error: string | null;
}

export interface HealthReport {
  status: "ok" | "degraded";
  postgres: DependencyStatus;
  qdrant: DependencyStatus;
  quota_remaining: Record<string, number> | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getApiBaseUrl(configured: string | undefined = process.env.NEXT_PUBLIC_API_URL) {
  const base = configured?.trim() || DEFAULT_API_URL;
  return base.replace(/\/+$/, "");
}

export function apiUrl(path: string, base: string = getApiBaseUrl()) {
  return `${base}/${path.replace(/^\/+/, "")}`;
}

async function request<T>(
  path: string,
  init: RequestInit & { acceptStatuses?: number[] } = {},
): Promise<T> {
  const { acceptStatuses = [], ...rest } = init;
  const response = await fetch(apiUrl(path), {
    ...rest,
    headers: { Accept: "application/json", ...rest.headers },
  });
  if (!response.ok && !acceptStatuses.includes(response.status)) {
    throw new ApiError(
      `${rest.method ?? "GET"} ${path} failed: ${response.status}`,
      response.status,
    );
  }
  return (await response.json()) as T;
}

/** 503 still carries a report: the API is up but a dependency is not. */
export function getHealth(signal?: AbortSignal) {
  return request<HealthReport>("/health", { signal, cache: "no-store", acceptStatuses: [503] });
}
