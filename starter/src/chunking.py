"""Fixed-size and structure-aware chunking.

Both strategies chunk one page at a time, so every chunk keeps a single
(document_id, page) for traceability. Structure metadata (chuong, muc, dieu)
is resolved from the page's heading offsets with ingestion.metadata_at().
"""
from __future__ import annotations

import hashlib
import re

from .ingestion import metadata_at
from .models import Chunk, DocumentPage

HEADING_RE = re.compile(r"^(Chương [IVXL]+$|Mục \d+$|Điều \d+\. )")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;:])\s+")


def _make_chunk(page: DocumentPage, kind: str, idx: int, start: int, end: int) -> Chunk:
    text = page.text[start:end].strip()
    lead = len(page.text[start:end]) - len(page.text[start:end].lstrip())
    start += lead
    meta = metadata_at(page, start)
    dieu_heads = [h for h in page.metadata.get("headings", [])
                  if h["type"] == "dieu" and start <= h["offset"] < end]
    carried = meta["dieu"]
    if dieu_heads:
        before = page.text[start:dieu_heads[0]["offset"]].split("\n")
        if all(not ln or HEADING_RE.match(ln) or _is_title(ln) for ln in before):
            # chunk opens with headings only (e.g. "Chương VII / title / Điều 105."),
            # so it does not contain any text of the previous article
            carried = None
            meta.update(dieu=dieu_heads[0]["value"], dieu_title=dieu_heads[0]["title"])
    dieu_list = sorted({d for d in [carried, *(h["value"] for h in dieu_heads)] if d is not None})
    meta.update(
        dieu_list=dieu_list,
        char_start=start,
        char_end=start + len(text),
        cong_bao_page=page.metadata.get("cong_bao_page"),
        content_hash=hashlib.sha1(text.encode("utf-8")).hexdigest()[:12],
    )
    return Chunk(
        chunk_id=f"{page.document_id}:p{page.page:03d}:{kind}:c{idx:02d}",
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text,
        metadata=meta,
    )


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Sliding character windows of `size` with `overlap`, ignoring structure."""
    if not 0 <= overlap < size:
        raise ValueError("need 0 <= overlap < size")
    chunks: list[Chunk] = []
    step, start, n = size - overlap, 0, len(page.text)
    while start < n:
        end = min(start + size, n)
        if page.text[start:end].strip():
            chunks.append(_make_chunk(page, f"fixed{size}o{overlap}", len(chunks), start, end))
        if end == n:
            break
        start += step
    return chunks


def _split_long(start: int, text: str, max_size: int) -> list[tuple[int, int]]:
    """Split one oversized paragraph at sentence/clause ends, then hard-split as last resort."""
    spans: list[tuple[int, int]] = []
    pieces, pos = [], 0
    for m in SENTENCE_SPLIT_RE.finditer(text):
        pieces.append((pos, m.start()))
        pos = m.end()
    pieces.append((pos, len(text)))
    cur_s, cur_e = pieces[0]
    for s, e in pieces[1:]:
        if e - cur_s <= max_size:
            cur_e = e
        else:
            spans.append((cur_s, cur_e))
            cur_s, cur_e = s, e
    spans.append((cur_s, cur_e))
    out: list[tuple[int, int]] = []
    for s, e in spans:  # hard split pieces that still exceed max_size
        while e - s > max_size:
            cut = text.rfind(" ", s, s + max_size)
            cut = cut if cut > s else s + max_size
            out.append((start + s, start + cut))
            s = cut + 1
        out.append((start + s, start + e))
    return out


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Group whole paragraphs (khoản/điểm lines) up to `max_size` characters.

    A new chunk starts before every Chương/Mục/Điều heading once the current
    chunk already holds body text, so a chunk never mixes two articles and
    headings stay attached to the text that follows them. Paragraphs longer
    than max_size are split at sentence/clause boundaries.
    """
    spans: list[tuple[int, int]] = []  # (start, end) of units: paragraphs or paragraph pieces
    offset = 0
    for para in page.text.split("\n"):
        end = offset + len(para)
        if len(para) > max_size:
            spans.extend((s, e, False) for s, e in _split_long(offset, para, max_size))
        elif para:
            spans.append((offset, end, bool(HEADING_RE.match(para)) or _is_title(para)))
        offset = end + 1

    chunks: list[Chunk] = []
    cur_start: int | None = None
    cur_end = 0
    has_body = False
    for s, e, is_heading in spans:
        starts_article = is_heading and has_body
        too_big = cur_start is not None and e - cur_start > max_size
        if cur_start is not None and (starts_article or too_big):
            chunks.append(_make_chunk(page, f"para{max_size}", len(chunks), cur_start, cur_end))
            cur_start, has_body = None, False
        if cur_start is None:
            cur_start = s
        cur_end = e
        has_body = has_body or not is_heading
    if cur_start is not None:
        chunks.append(_make_chunk(page, f"para{max_size}", len(chunks), cur_start, cur_end))
    return chunks


def _is_title(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)
