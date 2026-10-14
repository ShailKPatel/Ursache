import { describe, expect, it, vi } from "vitest";

import { apiUrl, getApiBaseUrl, getHealth } from "@/lib/api";

describe("getApiBaseUrl", () => {
  it("reads NEXT_PUBLIC_API_URL and strips trailing slashes", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://ursache-api.onrender.com//");
    expect(getApiBaseUrl()).toBe("https://ursache-api.onrender.com");
  });

  it("falls back to the local API when unset or blank", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "  ");
    expect(getApiBaseUrl()).toBe("http://localhost:8000");
    expect(getApiBaseUrl(undefined)).toBe("http://localhost:8000");
  });
});

describe("apiUrl", () => {
  it("joins base and path with exactly one slash", () => {
    expect(apiUrl("/health", "https://api.example")).toBe("https://api.example/health");
    expect(apiUrl("health", "https://api.example")).toBe("https://api.example/health");
  });

  it("uses the env base by default", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example/v");
    expect(apiUrl("/health")).toBe("https://api.example/v/health");
  });
});

describe("getHealth", () => {
  const body = {
    status: "degraded",
    postgres: { ok: true, latency_ms: 1, error: null },
    qdrant: { ok: false, latency_ms: 1, error: "ConnectError" },
    quota_remaining: null,
  };

  it("returns the report for a 503 so the UI can show which dependency is down", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example");
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(body), { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getHealth()).resolves.toEqual(body);
    expect(fetchMock).toHaveBeenCalledWith("https://api.example/health", expect.anything());
  });

  it("throws on other error statuses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 500 })));
    await expect(getHealth()).rejects.toMatchObject({ name: "ApiError", status: 500 });
  });
});
