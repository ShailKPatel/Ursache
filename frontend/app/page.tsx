import { HealthStatus } from "@/components/health-status";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center gap-8 px-4 py-16">
      <div className="space-y-3 text-center">
        <h1 className="text-4xl font-semibold tracking-tight">Ursache</h1>
        <p className="text-muted-foreground">
          Evidence-grounded root-cause analysis for the D4 step of an 8D investigation in a
          simulated hot-rolling steel mill.
        </p>
      </div>
      <HealthStatus />
    </main>
  );
}
