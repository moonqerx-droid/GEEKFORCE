"""Deterministic chunking of normalized document text.

Every chunk is a contiguous span of the source text, so its offsets always point back
to the original and an evidence quote from a chunk is a quote from the document.
Markdown headings (DOCX headings are converted to them on extraction) start a new chunk
and stay at its top; long sections are split at paragraphs, then sentences, then words,
and neighbouring chunks of one section share a short overlap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
_TOKEN = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class Chunk:
    position: int
    text: str
    heading: str | None
    start: int
    end: int

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def token_count(self) -> int:
        return len(_TOKEN.findall(self.text))


@dataclass(frozen=True)
class _Block:
    start: int
    end: int
    heading: str | None  # set only for a heading line


def chunk_text(text: str, *, max_chars: int = 1200, overlap: int = 150) -> list[Chunk]:
    if max_chars < 50:
        raise ValueError("max_chars is too small")
    overlap = max(0, min(overlap, max_chars // 3))
    chunks: list[Chunk] = []
    for heading, blocks in _sections(text):
        for start, end in _pack(text, blocks, max_chars, overlap):
            start, end = _trim(text, start, end)
            if start < end:
                chunks.append(Chunk(len(chunks), text[start:end], heading, start, end))
    return chunks


def _blocks(text: str) -> list[_Block]:
    """Paragraphs and heading lines with their offsets."""
    blocks: list[_Block] = []
    paragraph_start: int | None = None
    paragraph_end = 0
    offset = 0
    for line in text.split("\n"):
        line_start, line_end = offset, offset + len(line)
        offset = line_end + 1
        heading = _HEADING.match(line.strip())
        if not line.strip() or heading:
            if paragraph_start is not None:
                blocks.append(_Block(paragraph_start, paragraph_end, None))
                paragraph_start = None
            if heading:
                blocks.append(_Block(line_start, line_end, heading.group(2).strip()))
            continue
        if paragraph_start is None:
            paragraph_start = line_start
        paragraph_end = line_end
    if paragraph_start is not None:
        blocks.append(_Block(paragraph_start, paragraph_end, None))
    return blocks


def _sections(text: str) -> list[tuple[str | None, list[_Block]]]:
    sections: list[tuple[str | None, list[_Block]]] = []
    for block in _blocks(text):
        if block.heading is not None or not sections:
            sections.append((block.heading, []))
        sections[-1][1].append(block)
    return [section for section in sections if section[1]]


def _pieces(text: str, block: _Block, limit: int) -> list[tuple[int, int]]:
    """A block as spans of at most `limit` characters: sentences first, then words."""
    if block.end - block.start <= limit:
        return [(block.start, block.end)]
    pieces: list[tuple[int, int]] = []
    start = block.start
    while block.end - start > limit:
        window = text[start:start + limit]
        cut = max((match.end() for match in re.finditer(r"[.!?…](\s+)", window)), default=0)
        if cut < limit // 3:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit
        pieces.append((start, start + cut))
        start += cut
        while start < block.end and text[start].isspace():
            start += 1
    if start < block.end:
        pieces.append((start, block.end))
    return pieces


def _pack(text: str, blocks: list[_Block], max_chars: int, overlap: int) -> list[tuple[int, int]]:
    pieces = [piece for block in blocks for piece in _pieces(text, block, max_chars - overlap)]
    spans: list[tuple[int, int]] = []
    section_start = pieces[0][0]
    start, end = pieces[0]
    for piece_start, piece_end in pieces[1:]:
        if piece_end - start <= max_chars:
            end = piece_end
            continue
        spans.append((start, end))
        start = max(_overlap_start(text, end, overlap, section_start), 0)
        if piece_end - start > max_chars:
            start = piece_start
        end = piece_end
    spans.append((start, end))
    return spans


def _overlap_start(text: str, end: int, overlap: int, floor: int) -> int:
    """Start of the last `overlap` characters before `end`, moved forward to a word start."""
    if overlap <= 0:
        return end
    start = max(floor, end - overlap)
    if start > floor and not text[start - 1].isspace():
        next_space = text.find(" ", start, end)
        next_break = text.find("\n", start, end)
        candidates = [index for index in (next_space, next_break) if index != -1]
        start = min(candidates) + 1 if candidates else end
    return start


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end
