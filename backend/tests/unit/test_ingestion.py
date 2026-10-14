import uuid
from datetime import date

import pytest

from simulator import SimConfig, generate
from simulator.model import DocumentRow
from ursache.ingestion import (
    DocumentInfo,
    approx_tokens,
    build_chunk_rows,
    chunk_document,
    split_markdown,
)
from ursache.ingestion.chunking import MAX_TOKENS, MIN_TOKENS, TARGET_TOKENS

CONFIG = SimConfig(seed=42, days=21, coils_per_day=12, samples_per_coil=1)


def info(doc: DocumentRow) -> DocumentInfo:
    return DocumentInfo(
        id=doc.id,
        doc_type=doc.doc_type,
        title=doc.title,
        language=doc.language,
        version=doc.version,
        effective_from=doc.effective_from,
        effective_to=doc.effective_to,
        source_path=doc.source_path,
        sha256=doc.sha256,
    )


@pytest.fixture(scope="module")
def documents() -> list[DocumentRow]:
    return generate(CONFIG).documents


def paragraph(words: int, seed: str = "word") -> str:
    return " ".join(f"{seed}{i}" for i in range(words)) + "."


def test_approx_tokens_counts_words_and_punctuation() -> None:
    assert approx_tokens("") == 0
    assert approx_tokens("Roll gap") == 2
    assert approx_tokens("Roll force") == 3
    assert approx_tokens("Abstellmaßnahmen") == 4
    assert approx_tokens("| a | b |") == 5
    assert approx_tokens("|---|---|") == 3


def test_headings_become_section_paths() -> None:
    text = (
        "# WI-1 Title\n\nIntro.\n\n## 1 Scope\n\n" + paragraph(200, "a") + "\n\n"
        "## 2 Steps\n\n### 2.1 Prepare\n\n" + paragraph(200, "b") + "\n\n"
        "### 2.2 Run\n\n" + paragraph(200, "c") + "\n\n## 3 Close\n\n" + paragraph(200, "d")
    )
    heading, pieces = split_markdown(text)
    assert heading == "WI-1 Title"
    paths = [p.section_path for p in pieces]
    assert paths == ["1 Scope", "2 Steps > 2.1 Prepare", "2 Steps > 2.2 Run", "3 Close"]
    assert pieces[0].text.startswith("Intro.\n\n## 1 Scope")
    assert pieces[1].text.startswith("## 2 Steps\n\n### 2.1 Prepare\n\nb0")
    assert all("# WI-1 Title" not in p.text for p in pieces)


def test_small_sections_merge_into_neighbours() -> None:
    text = "# T\n\n## 1 A\n\nShort.\n\n## 2 B\n\nAlso short.\n\n## 3 C\n\n" + paragraph(100)
    _, pieces = split_markdown(text)
    assert [p.section_path for p in pieces] == ["1 A; 2 B; 3 C"]


def test_long_sections_split_on_paragraph_boundaries() -> None:
    paragraphs = [paragraph(150, f"p{i}x") for i in range(8)]
    _, pieces = split_markdown("## 1 Long\n\n" + "\n\n".join(paragraphs))
    assert len(pieces) > 1
    assert all(p.section_path == "1 Long" for p in pieces)
    for piece in pieces:
        body = piece.text.removeprefix("## 1 Long\n\n")
        assert all(chunk in paragraphs for chunk in body.split("\n\n"))
    assert "\n\n".join(p.text for p in pieces) == "## 1 Long\n\n" + "\n\n".join(paragraphs)


def test_tables_and_numbered_steps_stay_whole() -> None:
    table = "| Step | Value |\n|---|---|\n" + "".join(f"| s{i} | {i} |\n" for i in range(60))
    steps = "\n".join(f"{i}. {paragraph(40, f'step{i}w')}" for i in range(1, 16))
    text = f"## 1 Data\n\n{table}\n{paragraph(250)}\n\n## 2 Steps\n\n{steps}\n"
    _, pieces = split_markdown(text)
    assert sum(table.strip() in p.text for p in pieces) == 1
    for i in range(1, 16):
        step = f"{i}. {paragraph(40, f'step{i}w')}"
        assert sum(step in p.text for p in pieces) == 1, i
    assert len([p for p in pieces if p.section_path == "2 Steps"]) > 1
    assert all(p.token_count <= MAX_TOKENS for p in pieces)


def test_oversized_paragraph_falls_back_to_sentences() -> None:
    sentences = [f"Sentence {i} " + paragraph(30, f"s{i}w") for i in range(40)]
    _, pieces = split_markdown("## Long\n\n" + " ".join(sentences))
    assert len(pieces) > 1
    assert all(p.token_count <= MAX_TOKENS for p in pieces)


def test_context_header_names_document_revision_and_section() -> None:
    text = "# WI-HSM2-RC-007 Work-roll change\n\n## 3 Change interval\n\n" + paragraph(10)
    [chunk] = chunk_document(
        text, title="Work-roll change", version="3", source_path="wi/WI-HSM2-RC-007_rev3.md"
    )
    assert chunk.context_header == "WI-HSM2-RC-007 rev 3 · Work-roll change · 3 Change interval"

    [cert] = chunk_document(
        "# Certificate X\n\nBody.", title="Certificate X", version="1", source_path="c/AB-1.md"
    )
    assert cert.context_header == "AB-1 rev 1 · Certificate X"


def test_simulator_documents_respect_token_bounds(documents: list[DocumentRow]) -> None:
    for doc in documents:
        rows = build_chunk_rows(info(doc), doc.content)
        assert rows, doc.source_path
        assert [r.ordinal for r in rows] == list(range(len(rows)))
        for row in rows:
            assert row.text.strip(), doc.source_path
            assert 0 < row.token_count <= MAX_TOKENS, doc.source_path
            assert row.token_count == approx_tokens(row.text)
        if approx_tokens(doc.content) >= MIN_TOKENS:
            assert all(r.token_count >= MIN_TOKENS for r in rows), doc.source_path
        if len(rows) > 1:
            assert all(r.token_count >= TARGET_TOKENS // 2 for r in rows[:-1]), doc.source_path


def test_simulator_documents_keep_language_and_metadata(documents: list[DocumentRow]) -> None:
    german = [d for d in documents if d.language == "de"]
    assert {d.doc_type for d in german} >= {"work_instruction", "sop", "maintenance_manual"}
    for doc in documents:
        for row in build_chunk_rows(info(doc), doc.content):
            assert row.language == doc.language
            assert row.metadata == {
                "doc_type": doc.doc_type,
                "version": doc.version,
                "effective_from": doc.effective_from.isoformat(),
                "effective_to": doc.effective_to.isoformat() if doc.effective_to else None,
            }
            assert f" rev {doc.version} · {doc.title}" in row.context_header


def test_superseded_revision_carries_effective_to(documents: list[DocumentRow]) -> None:
    rev2 = next(d for d in documents if d.source_path.endswith("WI-HSM2-RC-007_rev2.md"))
    [row, *_] = build_chunk_rows(info(rev2), rev2.content)
    assert row.metadata["effective_to"] is not None
    assert row.context_header.startswith("WI-HSM2-RC-007 rev 2 · Work-roll change")


def test_same_input_gives_same_chunks(documents: list[DocumentRow]) -> None:
    again = generate(CONFIG).documents
    for a, b in zip(documents, again, strict=True):
        assert build_chunk_rows(info(a), a.content) == build_chunk_rows(info(b), b.content)


def test_chunk_ids_depend_on_document_and_text() -> None:
    doc = DocumentInfo(
        uuid.UUID(int=1), "sop", "T", "en", "1", date(2026, 1, 1), None, "s/SOP-1.md", "0" * 64
    )
    first = build_chunk_rows(doc, "# T\n\nSome text.")
    changed = build_chunk_rows(doc, "# T\n\nOther text.")
    other_doc = build_chunk_rows(
        DocumentInfo(
            uuid.UUID(int=2), "sop", "T", "en", "1", date(2026, 1, 1), None, "s/S.md", "0" * 64
        ),
        "# T\n\nSome text.",
    )
    assert first[0].id != changed[0].id
    assert first[0].id != other_doc[0].id
    assert first == build_chunk_rows(doc, "# T\n\nSome text.")
