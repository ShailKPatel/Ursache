# Document ingestion

`ursache/ingestion` turns the controlled documents listed in `kb.documents` into
`kb.chunks` rows. It reads each row's Markdown file from `GENERATED_DOCS_DIR`, splits it
into chunks and replaces that document's chunks. Embeddings, Qdrant points and images are
built later from these rows ([ADR 0001](adr/0001-postgres-source-of-truth-qdrant-derived-index.md)).
Ingestion makes no network or LLM calls.

```bash
make ingest                         # after `make simulate`
make ingest FORCE=1                 # rebuild every document
cd backend && uv run ursache ingest-docs --help
```

The command prints one JSON line:

```json
{"documents": 148, "ingested": 148, "skipped": 0, "missing": 0, "chunks": 148}
```

`documents` is the number of `kb.documents` rows, `ingested` the documents whose chunks
were (re)written, `skipped` the unchanged ones, `missing` the rows whose file was not
found and `chunks` the number of chunk rows written in this run.

## Code layout

| Module         | Responsibility                                                         |
| -------------- | ---------------------------------------------------------------------- |
| `chunking.py`  | Pure Markdown splitter, token estimate, context header; no I/O          |
| `documents.py` | Reads `kb.documents`, loads files, compares and replaces `kb.chunks`    |

## Chunking rules

1. **Sections.** The document is split at ATX headings (`#` to `######`) outside fenced
   code. A leading level-1 heading is the document title: it is removed from the chunk
   text and used for the document number. `section_path` is the heading trail below the
   title, joined with ` > ` (`2 Steps > 2.1 Prepare`). A heading with no text of its own
   opens the following section, so a chunk never ends on a bare heading.
2. **Blocks.** Inside a section, blank lines separate blocks. Tables, fenced code and
   paragraphs are never split. A list is split only between items, so a numbered step
   stays whole together with its continuation lines.
3. **Long sections.** A section above `MAX_TOKENS` (600) is cut between blocks, packing
   blocks up to `TARGET_TOKENS` (350). A remainder under `MIN_TOKENS` (80) joins the
   previous piece if the result stays within the maximum. Only a single paragraph above
   the maximum is cut further, between sentences.
4. **Small sections.** Neighbouring pieces are merged while the result stays within the
   target. A piece under `MIN_TOKENS` is merged into its neighbour even past the target, up
   to the maximum. The merged chunk's `section_path` lists its sections joined with `; `
   (`1 Scope; 2 Safety; 3 Change interval`).
5. **Limits.** Every chunk has at most 600 estimated tokens, unless one table, list item,
   code block or sentence alone is larger: those are kept whole rather than cut. No chunk
   is empty.

Each chunk row gets:

| Column           | Value                                                                    |
| ---------------- | ------------------------------------------------------------------------ |
| `id`             | UUIDv5 of the document id and `"<ordinal>:<sha256>"`; stable across runs |
| `ordinal`        | 0, 1, 2, … in document order                                             |
| `text`           | The Markdown of the chunk, headings included, title heading excluded     |
| `context_header` | `<number> rev <version> · <title> · <section_path>`                      |
| `section_path`   | See above; empty for a document without headings                         |
| `page`           | `NULL` (Markdown has no pages)                                           |
| `language`       | `kb.documents.language`                                                  |
| `token_count`    | Estimated tokens of `text`                                               |
| `sha256`         | SHA-256 of `text` (UTF-8)                                                |
| `metadata`       | `doc_type`, `version`, `effective_from`, `effective_to` (ISO dates)      |

The document number comes from the title heading (`# WI-HSM2-RC-007 Work-roll change, …`
gives `WI-HSM2-RC-007`). When the heading is the title alone, as on certificates, the file
name without its `_rev…` suffix is used. An example header:

```
WI-HSM2-RC-007 rev 3 · Work-roll change, finishing stands HSM-2 · 1 Scope; 2 Safety; 3 Change interval; 4 Procedure; Change history
```

`metadata` repeats the document fields that retrieval filters on (for example "documents
effective on the incident date"), so the Qdrant payload can be built from the chunk row
alone. The header is stored separately from the text; the indexing step decides how to
combine them for embedding.

## Token estimate

There is no tokenizer dependency. `approx_tokens` matches every word (`\w+`) and every run
of punctuation (`[^\w\s]+`) and counts one token per started four characters of each
match: `roll` is 1, `force` is 2, `Abstellmaßnahmen` is 4, `|---|` is 2. Whitespace is free.

It is not calibrated against a specific tokenizer. Subword tokenizers treat most common
English words of five to eight letters as one token, where the estimate counts two, so it
tends to run high for English; long German compounds, which tokenizers also cut into
several pieces, come out closer. Erring high keeps real chunk sizes under the limits. The
estimate is used only for the chunk bounds and `token_count`, never for billing or quota.

## Result on the default dataset

Every simulated document is short (the largest, `WI-HSM2-RC-007` revision 3, is about 400
estimated tokens), so with these rules each one becomes a single chunk. For seed 42 and 90
days that is 148 documents and 148 chunks:

| `doc_type`             | Documents | Chunks | Tokens (min / mean / max) |
| ---------------------- | --------- | ------ | ------------------------- |
| `work_instruction`     | 5         | 5      | 179 / 267 / 378           |
| `sop`                  | 4         | 4      | 150 / 193 / 254           |
| `maintenance_manual`   | 5         | 5      | 121 / 177 / 212           |
| `8d_report`            | 4         | 4      | 162 / 163 / 164           |
| `material_certificate` | 130       | 130    | 199 / 208 / 220           |

Longer documents split as described above; the unit tests cover that with synthetic text.

## Idempotency

For every document the chunks are rebuilt in memory (cheap) and compared with the stored
ones on id, ordinal, hash, header, section path, language, token count and metadata.

- **Unchanged** (same file content and the same chunking result): skipped, nothing written.
- **New or changed** (new file, edited file, changed document fields or chunking rules):
  the document's chunks are deleted and inserted again in one transaction, so a failure
  leaves either the old or the new set, never a mix.
- **Missing file** (or a `source_path` that points outside the directory): a warning is
  logged and the document is skipped; the run continues.
- A file whose hash differs from `kb.documents.sha256` is chunked from disk, with a
  warning.
- `--force` skips the comparison and rewrites every document. Because ids derive from the
  document and the text, a forced rebuild gives the same ids.

Chunk ids are stable while the text is stable, so a Qdrant point (id = chunk id) stays
valid across reruns.

## Database role

Ingestion connects as `ursache_app` (`APP_DATABASE_URL`). It writes only `kb`, which that
role may read and write; it never needs the owner role that the simulator and migrations
use. `ursache_agent` can read `kb.chunks` but not write it; the integration tests check
both.
