# ADR 0004: Hand-written retrieval; LangGraph for orchestration

- Status: accepted
- Date: 2026-10-14

## Context

Retrieval quality decides whether hypotheses are grounded. We want to measure each stage
on its own: dense recall, BM25 recall, fusion, metadata filters (such as which documents
were in effect on the incident date), rerank lift, and context building. The investigation
itself runs for several steps, must survive restarts on a free host that sleeps, and must
pause for a human review before a report is written.

## Decision

- **Retrieval is hand-written** on qdrant-client: hybrid query with dense
  (`gemini-embedding-2`, 768-d) and sparse BM25 (IDF modifier), fused with Qdrant's query
  API, payload filters, and then Cohere multilingual rerank. Each stage is a plain function
  with typed inputs and outputs, so evals can turn stages on or off and record
  per-stage metrics.
- **LangGraph handles orchestration only**: the state machine of investigation steps, the
  **Postgres checkpointer** (resume after a cold start or crash) and the
  **`interrupt` for human review** of hypotheses before the report.
- LangChain retriever, vector store and document abstractions are not used.

## Alternatives considered

- **LangChain or LlamaIndex retrieval pipelines.** Quick to start, but they hide the
  stage boundaries we want to measure, add an abstraction over Qdrant's hybrid query API,
  and make ablations harder to express.
- **A hand-written orchestration loop.** No dependency, but checkpointing, resumption and
  human-in-the-loop interrupts would have to be rebuilt and tested by hand.
- **A hosted agent platform.** It conflicts with the zero-budget constraint and hides the
  control flow.

## Consequences

- More retrieval code to own and test, in exchange for an evaluation in which every number
  can be attributed to a stage.
- The agent graph state must be serialisable for the checkpointer. Large artefacts are
  stored as evidence rows and referenced by ID.
- LangGraph is a dependency with an API that changes fairly often. Its use is limited to
  `ursache/agent` to keep upgrades contained.
