"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getHealth, type HealthReport } from "@/lib/api";

// Render's free tier sleeps after inactivity; a cold start takes up to about a minute.
const RETRY_DELAY_MS = 3_000;
const REQUEST_TIMEOUT_MS = 10_000;
const MAX_ATTEMPTS = 30;

type State =
  | { kind: "waking"; attempt: number }
  | { kind: "ready"; report: HealthReport }
  | { kind: "unreachable" };

export function HealthStatus() {
  const [state, setState] = useState<State>({ kind: "waking", attempt: 1 });

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll(attempt: number) {
      try {
        const report = await getHealth(AbortSignal.timeout(REQUEST_TIMEOUT_MS));
        if (!cancelled) setState({ kind: "ready", report });
      } catch {
        if (cancelled) return;
        if (attempt >= MAX_ATTEMPTS) {
          setState({ kind: "unreachable" });
          return;
        }
        setState({ kind: "waking", attempt: attempt + 1 });
        timer = setTimeout(() => void poll(attempt + 1), RETRY_DELAY_MS);
      }
    }

    void poll(1);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  return (
    <Card className="w-full max-w-md" aria-live="polite">
      <CardHeader>
        <CardTitle>Backend status</CardTitle>
        <CardDescription>
          FastAPI on Render, Postgres on Neon, vectors on Qdrant Cloud
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {state.kind === "waking" && (
          <p className="flex items-center gap-2">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            Waking up the backend… (attempt {state.attempt})
          </p>
        )}
        {state.kind === "unreachable" && (
          <p className="text-destructive flex items-center gap-2">
            <TriangleAlert className="size-4" aria-hidden />
            Backend unreachable. Try again in a minute.
          </p>
        )}
        {state.kind === "ready" && <Report report={state.report} />}
      </CardContent>
    </Card>
  );
}

function Report({ report }: { report: HealthReport }) {
  const ok = report.status === "ok";
  return (
    <>
      <p className="flex items-center gap-2">
        {ok ? (
          <CheckCircle2 className="size-4 text-emerald-600" aria-hidden />
        ) : (
          <TriangleAlert className="size-4 text-amber-600" aria-hidden />
        )}
        {ok ? "Backend ready" : "Backend degraded"}
      </p>
      <div className="flex gap-2">
        <Badge variant={report.postgres.ok ? "secondary" : "destructive"}>Postgres</Badge>
        <Badge variant={report.qdrant.ok ? "secondary" : "destructive"}>Qdrant</Badge>
      </div>
      {report.quota_remaining && (
        <ul className="text-muted-foreground space-y-1">
          {Object.entries(report.quota_remaining).map(([model, remaining]) => (
            <li key={model} className="flex justify-between gap-4">
              <span className="font-mono">{model}</span>
              <span>{remaining} left today</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
