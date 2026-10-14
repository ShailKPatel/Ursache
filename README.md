# Ursache

Ursache (German: *cause*) helps a quality engineer with the root-cause step (D4) of an 8D
investigation in a hot-rolling steel mill. Given an incident, it collects evidence from
process data, maintenance logs, inspection results, defect images and controlled documents
(work instructions, supplier certificates, past 8D reports). It proposes 6M root-cause
hypotheses and supports each one with citations that the engineer can check. An engineer
reviews the hypotheses before any report is written.

> **Status:** Phase 2. The foundation (configuration, database schema, infrastructure,
> deploy configs, CI) and the plant simulator are in place. Retrieval and the agent come in
> later phases.

## Why a simulated plant

No public dataset links defect images, process time series and documents for the same
coils. So the plant is **simulated**, with **planted root causes**: for example, a worn
descaler nozzle on one stand during a known time window. The planted causes are the ground
truth for evaluation. They live in a separate `eval` schema that the agent's database role
cannot read, so the system cannot cheat. The defect images are real: the public NEU-DET
hot-rolled strip dataset ([ADR 0003](docs/adr/0003-simulated-plant-with-planted-root-causes.md)).

The simulator (`backend/simulator`) is deterministic: a seed fixes every row and file. It
models two hot-strip lines over 90 days (about 7,200 coils and 500,000 sensor readings),
plants six causes covering the 6M categories, writes the incidents they produce as shift
reports that never name the cause, and generates work instructions, SOPs, manual sections,
supplier certificates and past 8D reports as Markdown. Details, effect sizes and the size
estimate: [docs/simulator.md](docs/simulator.md).

All data is synthetic or public. Nothing confidential leaves the machine. That is why the
project can use free-tier hosted APIs for the LLM, embeddings and reranking.

## Architecture

```
Next.js (Vercel) ──HTTPS──▶ FastAPI (Render, Docker)
                              ├── Postgres (Neon)      source of truth: plant, kb, app, eval
                              ├── Qdrant Cloud         derived index: dense + BM25 + image vectors
                              ├── Backblaze B2         defect images (S3 API)
                              ├── Gemini API           Flash / Flash-Lite / gemini-embedding-2
                              ├── Cohere API           multilingual rerank
                              └── Langfuse Cloud       traces via OpenTelemetry (OTLP/HTTP)
```

The server runs no ML models. More detail: [docs/architecture.md](docs/architecture.md) and
the [ADRs](docs/adr/).

### Hosting map (all free tiers, no credit card)

| Concern          | Service                         | Notes                                                        |
| ---------------- | ------------------------------- | ------------------------------------------------------------ |
| Frontend         | Vercel Hobby                    | Root directory `frontend/`, env `NEXT_PUBLIC_API_URL`         |
| API              | Render free web service         | `render.yaml`, Docker; sleeps when idle (cold start ≈ 1 min) |
| Database         | Neon Free (Postgres 18)         | Four schemas, three restricted roles                          |
| Vectors          | Qdrant Cloud free cluster       | Cloud Inference for BM25; weekly keep-alive workflow           |
| Images           | Backblaze B2                    | S3-compatible API via boto3                                   |
| Tracing          | Langfuse Cloud Hobby            | OTLP/HTTP; tracing is off when keys are unset                 |
| LLM + embeddings | Gemini API (free tier)          | `gemini-3.8-flash`, `gemini-3.5-flash-lite`, `gemini-embedding-2` |
| Rerank           | Cohere (trial key)              | `rerank-v4.0-fast`                                            |

## Tech stack

**Backend:** Python 3.12, uv, FastAPI, Pydantic v2, SQLAlchemy 2 (async, psycopg 3),
Alembic, qdrant-client, LangGraph, google-genai, cohere, boto3, OpenTelemetry, Typer,
slowapi. Checked with ruff, pyright (strict on `src/`) and pytest.

**Frontend:** Next.js 16 (App Router), React 19, TypeScript (strict), Tailwind CSS 4,
shadcn/ui. Checked with ESLint, Prettier and Vitest.

## Local quickstart

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/) and [pnpm](https://pnpm.io/)
(Node 24 LTS).

```bash
cp .env.example .env           # defaults match docker-compose.yml
make install                   # uv sync + pnpm install
make up                        # Postgres 18 + Qdrant, waits until healthy
make migrate roles seed bootstrap
make simulate                  # plant data, documents, ground truth (~130 MB, ~50 s)
make api                       # http://localhost:8000/health
make web                       # http://localhost:3000 (second terminal)
```

Checks:

```bash
make lint typecheck test       # backend + frontend, no services needed
make test-integration          # needs `make up`; uses a throwaway database
```

Run `make help` to list every target. The operations CLI is `uv run ursache --help`, run
from `backend/`.

## Deploying (manual, one time)

1. **Neon:** create a project with Postgres 18. From a workstation, set
   `MIGRATION_DATABASE_URL` to the owner connection string and set the three role URLs
   with strong passwords. Then run `make roles migrate`. The default privileges set by
   `roles` carry over to the tables that `migrate` creates. The API never holds the owner
   credentials.
2. **Qdrant Cloud:** create a free cluster and run `make bootstrap` with `QDRANT_URL` and
   `QDRANT_API_KEY` set and `QDRANT_CLOUD_INFERENCE=true`.
3. **Render:** create a Blueprint from `render.yaml` and fill in the `sync: false` secrets.
4. **Vercel:** import the repository, set **Root Directory** to `frontend`, and set
   `NEXT_PUBLIC_API_URL` to the Render URL. Add the Vercel URL to `CORS_ALLOWED_ORIGINS` on
   Render.
5. **GitHub:** add the repository secrets `QDRANT_URL`, `QDRANT_API_KEY` and
   `NEON_READONLY_URL` (a libpq URL for `ursache_agent`) for the weekly keep-alive.

## Results

_To be filled in when the evaluation harness lands._

## Ablations

_To be filled in when the evaluation harness lands._
