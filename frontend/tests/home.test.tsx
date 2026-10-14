import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import Home from "@/app/page";

describe("Home page", () => {
  it("shows the waking-up state while the backend has not answered", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    render(<Home />);

    expect(screen.getByRole("heading", { name: "Ursache" })).toBeInTheDocument();
    expect(screen.getByText(/waking up the backend/i)).toBeInTheDocument();
  });

  it("shows readiness and remaining quota once /health answers", async () => {
    const report = {
      status: "ok",
      postgres: { ok: true, latency_ms: 2, error: null },
      qdrant: { ok: true, latency_ms: 3, error: null },
      quota_remaining: { "gemini/gemini-3.8-flash": 18 },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(report))));
    render(<Home />);

    expect(await screen.findByText("Backend ready")).toBeInTheDocument();
    expect(screen.getByText("18 left today")).toBeInTheDocument();
  });
});
