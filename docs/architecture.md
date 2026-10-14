# Architecture

## Components

| Component       | Where                       | Responsibility                                                              |
| --------------- | --------------------------- | --------------------------------------------------------------------------- |
| Web UI          | `frontend/` → Vercel        | Starts investigations, shows evidence and hypotheses, collects the review   |
| API             | `backend/src/ursache/api`   | HTTP and SSE endpoints, CORS, per-IP rate limits, health                    |
| Agent           | `ursache/agent` (LangGraph) | Orchestrates the investigation; checkpoints to Postgres; pauses for review  |
| Typed tools     | `ursache/tools`             | The only way the agent reaches data (SQL, retrieval, images)                |
| Retrieval       | `ursache/retrieval`         | Hybrid dense + BM25 search, Cohere rerank, filters on payload               |
| Grounding       | `ursache/grounding`         | Checks that every claim in a report cites stored evidence                   |
| Ingestion       | `ursache/ingestion`         | Parses documents and images; writes Postgres rows and blobs                 |
| Indexing        | `ursache/indexing`          | Builds Qdrant points from Postgres rows; manages collections and aliases    |
| LLM layer       | `ursache/llm`               | `LLMClient` protocol, Gemini client, Postgres response cache, quota guard    |
| Simulator       | `backend/simulator`         | Generates the plant, documents and planted causes (writes `plant`, `kb`, `eval`) |
| Evals           | `backend/evals`             | Scores retrieval and RCA against the planted ground truth                   |
| CLI             | `ursache` (Typer)           | `db-migrate`, `db-roles`, `db-seed`, `qdrant-bootstrap`, `simulate`, `ingest-docs`, `health` |

Implemented so far: the API health endpoint, the CLI, the LLM layer, storage, the indexing
bootstrap (Phase 1), the simulator (Phase 2, see [simulator.md](simulator.md)) and document
chunking (Phase 3, see [ingestion.md](ingestion.md)). The other packages are placeholders.

## Data flow

```
                 ┌────────────┐   rows (UUID ids)    ┌──────────────┐
 documents  ───▶ │ ingestion  │ ───────────────────▶ │ Postgres     │  source of truth
 images     ───▶ │            │ ───── blobs ───────▶ │ (Neon)       │
                 └────────────┘          │           └──────┬───────┘
                                         ▼                  │ read rows not yet indexed
                                   Backblaze B2             ▼ (kb.index_state)
                                                     ┌──────────────┐
                                                     │ indexing job │── embeddings via Gemini
                                                     └──────┬───────┘── BM25 via Qdrant/fastembed
                                                            ▼ upsert, point id = row UUID
                                                     ┌──────────────┐
                                                     │ Qdrant       │  derived index (aliases)
                                                     └──────┬───────┘
                                                            │
  UI ──▶ API ──▶ agent ──▶ typed tools ─────────────────────┘ (and read-only SQL on plant, kb)
                    │
                    └──▶ app schema: investigations, steps, evidence, hypotheses, reports
```

1. **Ingestion** writes document and chunk rows to `kb` in Postgres (Neon) and uploads
   images to B2. The SHA-256 of each item makes re-ingestion idempotent.
2. **Indexing** reads rows that are new or changed according to `kb.index_state`. It embeds
   them and upserts them into Qdrant with **point ID = the row's UUID**, so every hit maps
   back to exactly one row. The collection names carry the model and version
   (`doc_chunks__gemb2_768__v1`). Queries go through aliases (`doc_chunks`), which allows
   re-indexing and switching without downtime ([ADR 0001](adr/0001-postgres-source-of-truth-qdrant-derived-index.md)).
3. **The agent reaches data only through typed tools**, such as "readings for an equipment
   and parameter in a time window", "maintenance events near a time" and "search controlled
   documents". A guarded text-to-SQL tool is the fallback ([ADR 0002](adr/0002-typed-tools-before-text-to-sql.md)).
   SQL tools connect as `ursache_agent`.
4. Each tool result becomes an `app.evidence` row holding a snapshot. Hypotheses link to
   evidence with a stance (supports or contradicts). The final report is scored for
   grounding.

## LLM call path

```
caller ─▶ CachedLLMClient ─▶ cache hit? ─yes─▶ return stored response (no quota used)
                               │no
                               ▼
                            QuotaGuard.acquire (atomic upsert in app.quota_usage; raises QuotaExceeded at cap)
                               ▼
                            GeminiClient ─▶ store in app.llm_cache, add tokens to quota_usage
```

The quota day follows Gemini's reset at midnight Pacific time.

## Schemas and access

| Schema  | Contents                                                       | `ursache_app` | `ursache_agent`       | `ursache_eval` |
| ------- | -------------------------------------------------------------- | ------------- | --------------------- | -------------- |
| `plant` | lines, equipment, coils, readings, inspections, defects, …     | read/write    | **SELECT**            | SELECT         |
| `kb`    | documents, chunks, images, index_state                         | read/write    | **SELECT**            | SELECT         |
| `app`   | users, investigations, steps, evidence, hypotheses, cache, quota | read/write  | none                  | SELECT         |
| `eval`  | planted root causes, injections, questions, runs, results      | none          | none                  | SELECT         |

- The **migration role** (the Neon project owner, or `postgres` locally) owns every object.
  It runs Alembic and `roles.sql`. Default privileges make sure future tables inherit
  these grants.
- `ursache_agent` also has `statement_timeout = 5s` and
  `default_transaction_read_only = on` set on the role.
- The ground truth in `eval` is visible only to `ursache_eval`, which the evaluation
  harness uses. The agent and the API cannot read it, and integration tests enforce this.
- The **simulator** connects with `MIGRATION_DATABASE_URL`, the owner role, because it
  writes `plant`, `kb` and `eval` and no restricted role can write `eval` (`ursache_app`
  cannot even read it). It runs from a workstation or CI, never inside the
  API: `backend/simulator` is excluded from the Docker image, so the deployed service never
  holds code that writes ground truth. Nothing it writes to `plant` or `kb` carries cause
  labels or injection ids; those exist only in `eval`.
- **Ingestion** connects as `ursache_app` (`APP_DATABASE_URL`), not the owner: it only
  writes `kb`, which that role may read and write ([ingestion.md](ingestion.md)).
- `plant.coil_process_summary` is a materialized view with one row per coil and the
  mean/min/max of each process parameter. The parameter list is one constant,
  `ursache.db.views.PROCESS_PARAMETERS`.
