"""Split controlled Markdown documents into retrieval chunks.

Pure and deterministic: the same text and settings always give the same chunks.
See docs/ingestion.md for the rules.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

TARGET_TOKENS = 350
MAX_TOKENS = 600
# Sections smaller than this are merged into a neighbour even past the target.
MIN_TOKENS = 80

PATH_SEPARATOR = " > "
PATHS_JOINER = "; "
HEADER_SEPARATOR = " · "

_TOKEN = re.compile(r"\w+|[^\w\s]+")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_LIST_ITEM = re.compile(r"^(\d+[.)]|[-*+])[ \t]+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9\"(])")
_REVISION_SUFFIX = re.compile(r"_rev[^_]*$")


def approx_tokens(text: str) -> int:
    """Estimate subword tokens without a tokenizer.

    Every word and every run of punctuation counts as one token per started four characters.
    """
    return sum(math.ceil(len(m.group()) / 4) for m in _TOKEN.finditer(text))


@dataclass(frozen=True, slots=True)
class Piece:
    """Chunk text with its heading trail, before document context is attached."""

    section_path: str
    text: str
    token_count: int


@dataclass(frozen=True, slots=True)
class Chunk:
    ordinal: int
    text: str
    section_path: str
    context_header: str
    token_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    joiner: str  # separator placed before this unit when it follows another one
    tokens: int


@dataclass(frozen=True, slots=True)
class _Part:
    paths: tuple[str, ...]
    units: tuple[_Unit, ...]

    @property
    def tokens(self) -> int:
        return sum(u.tokens for u in self.units)


def chunk_document(
    text: str,
    *,
    title: str,
    version: str,
    source_path: str,
    target: int = TARGET_TOKENS,
    maximum: int = MAX_TOKENS,
) -> list[Chunk]:
    """Chunk one document and attach the context header and hash to each piece."""
    heading, pieces = split_markdown(text, target=target, maximum=maximum)
    code = document_code(heading, title, source_path)
    return [
        Chunk(
            ordinal=i,
            text=p.text,
            section_path=p.section_path,
            context_header=context_header(code, version, title, p.section_path),
            token_count=p.token_count,
            sha256=hashlib.sha256(p.text.encode("utf-8")).hexdigest(),
        )
        for i, p in enumerate(pieces)
    ]


def document_code(heading: str | None, title: str, source_path: str) -> str:
    """Document number from the title heading ("# WI-HSM-014 Laminar ...") or the file name."""
    if heading and heading.endswith(title) and len(heading) > len(title):
        return heading[: -len(title)].strip()
    return _REVISION_SUFFIX.sub("", PurePosixPath(source_path).stem)


def context_header(code: str, version: str, title: str, section_path: str) -> str:
    parts = [f"{code} rev {version}", title]
    if section_path:
        parts.append(section_path)
    return HEADER_SEPARATOR.join(parts)


def split_markdown(
    text: str, *, target: int = TARGET_TOKENS, maximum: int = MAX_TOKENS
) -> tuple[str | None, list[Piece]]:
    """Return the document heading (leading H1, removed from the text) and the pieces."""
    heading, sections = _sections(text)
    parts: list[_Part] = []
    carried: list[str] = []
    for i, (path, body) in enumerate(sections):
        lines = [*carried, "", *body] if carried else body
        last = i == len(sections) - 1
        if not last and all(not line.strip() or _HEADING.match(line) for line in body):
            # A heading with no text of its own opens the next section instead.
            carried = lines
            continue
        carried = []
        units = _units(lines, maximum)
        if units:
            parts.extend(_split_long(path, units, target, maximum))
    return heading, [_render(p) for p in _merge(parts, target, maximum)]


def _sections(text: str) -> tuple[str | None, list[tuple[str, list[str]]]]:
    heading: str | None = None
    trail: list[tuple[int, str]] = []
    sections: list[tuple[str, list[str]]] = [("", [])]
    in_fence = False
    seen_content = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match is None:
            sections[-1][1].append(line)
            seen_content = seen_content or bool(line.strip())
            continue
        level, name = len(match.group(1)), match.group(2).strip()
        if level == 1 and heading is None and not seen_content:
            heading = name
            continue
        while trail and trail[-1][0] >= level:
            trail.pop()
        trail.append((level, name))
        sections.append((PATH_SEPARATOR.join(n for _, n in trail), [line]))
        seen_content = True
    return heading, sections


def _blocks(lines: list[str]) -> list[list[str]]:
    """Group lines into blank-line separated blocks; fenced code stays in one block."""
    blocks: list[list[str]] = []
    current: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
        if not line.strip() and not in_fence:
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line.rstrip())
    if current:
        blocks.append(current)
    return blocks


def _units(lines: list[str], maximum: int) -> list[_Unit]:
    """Atomic pieces of a section. A heading sticks to the block that follows it."""
    units: list[_Unit] = []
    pending_heading: str | None = None
    for block in _blocks(lines):
        if len(block) == 1 and _HEADING.match(block[0]):
            heading = block[0]
            pending_heading = (
                heading if pending_heading is None else f"{pending_heading}\n\n{heading}"
            )
            continue
        pieces = _block_pieces(block, maximum)
        if pending_heading is not None:
            first_text, first_joiner = pieces[0]
            pieces[0] = (f"{pending_heading}\n\n{first_text}", first_joiner)
            pending_heading = None
        for i, (piece, joiner) in enumerate(pieces):
            units.append(_Unit(piece, "\n\n" if i == 0 else joiner, approx_tokens(piece)))
    if pending_heading is not None:
        units.append(_Unit(pending_heading, "\n\n", approx_tokens(pending_heading)))
    return units


def _block_pieces(block: list[str], maximum: int) -> list[tuple[str, str]]:
    """Split a block only where allowed: between list items, else between sentences."""
    text = "\n".join(block)
    if approx_tokens(text) <= maximum or block[0].lstrip().startswith(("|", "```", "~~~")):
        return [(text, "\n\n")]
    if _LIST_ITEM.match(block[0]):
        items: list[list[str]] = []
        for line in block:
            if _LIST_ITEM.match(line) or not items:
                items.append([line])
            else:
                items[-1].append(line)
        return [("\n".join(item), "\n") for item in items]
    return [(sentence, " ") for sentence in _SENTENCE_END.split(text)]


def _split_long(path: str, units: list[_Unit], target: int, maximum: int) -> list[_Part]:
    if sum(u.tokens for u in units) <= maximum:
        return [_Part((path,), tuple(units))]
    parts: list[list[_Unit]] = [[]]
    for unit in units:
        size = sum(u.tokens for u in parts[-1])
        if parts[-1] and size + unit.tokens > target:
            parts.append([])
        parts[-1].append(unit)
    if len(parts) > 1 and sum(u.tokens for u in parts[-1]) < MIN_TOKENS:
        tail = parts.pop()
        if sum(u.tokens for u in parts[-1] + tail) <= maximum:
            parts[-1].extend(tail)
        else:
            parts.append(tail)
    return [_Part((path,), tuple(p)) for p in parts]


def _merge(parts: list[_Part], target: int, maximum: int) -> list[_Part]:
    """Join neighbours up to the target; tiny parts may join up to the maximum."""
    merged: list[_Part] = []
    for part in parts:
        if merged:
            last = merged[-1]
            size = last.tokens + part.tokens
            tiny = min(last.tokens, part.tokens) < MIN_TOKENS
            if size <= target or (tiny and size <= maximum):
                merged[-1] = _Part(last.paths + part.paths, last.units + part.units)
                continue
        merged.append(part)
    return merged


def _render(part: _Part) -> Piece:
    text = part.units[0].text + "".join(u.joiner + u.text for u in part.units[1:])
    paths = list(dict.fromkeys(p for p in part.paths if p))
    return Piece(PATHS_JOINER.join(paths), text, approx_tokens(text))
