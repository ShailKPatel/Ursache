# ADR 0001: Postgres is the source of truth; Qdrant is a derived index

- Status: accepted
- Date: 2026-10-14

## Context

Ursache stores relational plant data (coils, readings, maintenance), document chunks with
their metadata, and vectors for hybrid text search and image similarity. Evidence shown to
an engineer must trace back to a stable record. Embedding models and chunking strategies
will change over the project's life, and the evaluation needs to compare index variants
side by side.

## Decision

- **Postgres is the single source of truth** for every entity, including chunk text and
  image metadata.
- **Qdrant is a derived index**, rebuilt entirely from Postgres. A Qdrant point ID equals
  the UUID of the Postgres row it represents. Payloads hold only filter fields and IDs.
- Collections are **versioned by content and model**
  (`doc_chunks__gemb2_768__v1`, `defect_images__gemb2_dinov2__v1`). Readers always go
  through **aliases** (`doc_chunks`, `defect_images`).
- `kb.index_state` records which item has been indexed into which collection, with which
  model version, so indexing is incremental and resumable.
- Re-indexing means building a new versioned collection and switching the alias in one
  atomic `update_collection_aliases` call.

## Alternatives considered

- **pgvector only.** One database and transactional consistency. However, the free Neon
  tier is small (0.5 GB), there is no native sparse/BM25 hybrid with an IDF modifier, and
  multi-vector image search is less convenient. It remains the **fallback**: chunks
  already live in Postgres, so a `vector` column and an HNSW index could replace Qdrant
  without changing ingestion.
- **Qdrant as the primary store.** Simpler writes, but no relational integrity, no joins
  with process data, and evidence could not be audited against a stable record.
- **One unversioned collection.** Re-embedding would mean downtime or mixed-model
  vectors, and ablations would need separate deployments.

## Consequences

- Every index can be thrown away and rebuilt. Losing the Qdrant free cluster loses no
  data.
- Ablations (different embedding dimensions, chunking, sparse on or off) are new
  collections queried side by side, with aliases left untouched.
- Writes become two steps (Postgres first, then indexing), so the index is eventually
  consistent. `index_state` makes the lag visible.
- Point IDs must be UUIDs. The relational schema uses UUID keys for every indexed entity.
