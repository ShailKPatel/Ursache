# ADR 0002: Typed SQL tools first; text-to-SQL is a guarded fallback

- Status: accepted
- Date: 2026-10-14

## Context

The agent has to query process readings, maintenance events, lots and defects to test
hypotheses. Free-form text-to-SQL is flexible, but it fails in ways that are hard to see:
wrong joins, unit confusion, unbounded scans, and in the worst case reads of data it should
never see, such as the planted ground truth in `eval`. Each LLM call also uses part of a
small daily quota ([ADR 0005](0005-free-tier-hosting-and-llm-call-budget.md)).

## Decision

1. The agent's first-line tools are **typed functions** with Pydantic inputs and outputs,
   for example `readings(equipment_tag, parameter, start, end, agg)`,
   `maintenance_near(equipment_tag, ts, window)` and `defects_for_coil(coil_id)`. Each one
   is a reviewed, parameterised query. Tool outputs are stored as evidence snapshots.
2. **Text-to-SQL is a fallback** for questions the typed tools cannot express. Every
   generated statement passes these guards:
   - it is parsed with **sqlglot**, and anything other than a single `SELECT` is rejected;
   - it may reference only an **allowlist of tables** in the `plant` and `kb` schemas;
   - a **`LIMIT` is forced** (and capped);
   - it runs as **`ursache_agent`**, a role with SELECT only on `plant` and `kb`,
     `default_transaction_read_only = on`, and **`statement_timeout = 5s`**.
3. The database role is the last line of defence. The parser guards are the first and give
   clear error messages, but they are never trusted on their own.

## Alternatives considered

- **Text-to-SQL only.** Least code to write, but low reliability, hard to evaluate, and
  dependent on prompt quality for safety.
- **Typed tools only.** Safest, but the agent stalls on long-tail questions. The fallback
  is cheap to keep because the guards already exist.
- **A semantic layer or metrics store.** Too much machinery for a portfolio-scale schema.

## Consequences

- Most queries are deterministic and unit-testable, and evals can score tool selection
  separately from SQL generation.
- New question types need either a new typed tool or the fallback. Logs show which one,
  which tells us where to add typed tools.
- Access to `eval` is impossible from the agent at the database level. Integration tests
  assert this.
