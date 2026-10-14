# ADR 0005: Free-tier hosting and an LLM call budget

- Status: accepted
- Date: 2026-10-14

## Context

The project has a budget of zero: every service must have a free tier that needs no credit
card. The server must not run ML models, because free web instances have about 512 MB of
RAM and sleep when idle. The binding constraint is the **Gemini Flash free-tier daily
request quota**, which is small, applies per project, and resets at midnight Pacific time.
A public demo could use it up within minutes.

## Decision

Hosting:

| Concern    | Choice                      |
| ---------- | --------------------------- |
| Frontend   | Vercel Hobby                |
| API        | Render free web service (Docker) |
| Postgres   | Neon Free                   |
| Vectors    | Qdrant Cloud free cluster (Cloud Inference for BM25) |
| Images     | Backblaze B2                |
| Traces     | Langfuse Cloud Hobby (OTLP) |
| LLM / embeddings | Gemini API free tier  |
| Rerank     | Cohere trial key            |

No models run on the server. Embeddings, BM25 (via Qdrant Cloud Inference in production)
and reranking are API calls. DINOv2 image vectors are computed offline.

LLM budget:

1. **A rule-based first pass** narrows the search (time window, equipment, defect class)
   without any LLM call.
2. **At most 2 Flash calls per investigation**: hypothesis generation and the report.
   Flash-Lite handles light tasks such as query rewriting and classification.
3. **A Postgres response cache** (`app.llm_cache`, keyed by the SHA-256 of model, prompt
   and parameters). A cache hit uses no quota.
4. **A daily quota guard** (`app.quota_usage`, an atomic conditional upsert) raises
   `QuotaExceeded` at a configurable cap per model, below the provider's limit.
5. **Per-IP limits** via slowapi: a general request rate and a small number of live
   investigations per IP per day.
6. **Labelled replays**: when the quota is spent, the UI offers stored investigations,
   clearly marked as replays (`app.investigations.is_replay`), instead of failing.

## Alternatives considered

- **Hugging Face Docker Spaces** for the API. Rejected because Docker Spaces now require
  a paid plan.
- **Running small models on the server** (local embeddings, cross-encoder rerank). Free
  instances lack the RAM, cold starts get much slower, and the image grows.
- **Self-hosting Postgres and Qdrant on one VM.** No free option without a card, and more
  to operate.
- **Paid API tiers.** These would remove the main design constraint the project is meant
  to show.

## Consequences

- Cold starts: Render sleeps after inactivity, so the UI shows a "waking up the backend"
  state while it waits for `/health`.
- Qdrant Cloud suspends free clusters that are idle for a week. A weekly GitHub Actions
  keep-alive runs one read query against Qdrant and one against Neon.
- The quota caps are configuration, not code. They should be set below the limits shown
  in AI Studio for the project.
- All data is synthetic or public ([ADR 0003](0003-simulated-plant-with-planted-root-causes.md)),
  so sending it to free-tier APIs whose terms allow training on inputs is acceptable.
