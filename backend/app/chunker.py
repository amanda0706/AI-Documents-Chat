"""
chunker.py — Text cleaning and chunking for real-world PDF/TXT ingestion.

Strategy:
  1. Normalize Unicode, whitespace, and obvious encoding noise.
  2. Strip lines that repeat on more than half of all pages (headers/footers).
  3. Split each page into bounded chunks using heading detection, then
     paragraph splitting, then sentence-window fallback.

MAX_CHUNK_CHARS caps each fragment so that vector search and cloud-provider
context windows are not overwhelmed by a single giant page of text.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

MAX_CHUNK_CHARS: int = 1500
MIN_CHUNK_CHARS: int = 40

# Matches the *start* of a clause/section heading line.
# Covers: "1. Definitions", "1.1 Payment", "ARTICLE 2", "SECTION 3", "SCHEDULE A"
_HEADING_RE = re.compile(
    r"(?m)^(?=[ \t]*(?:"
    r"\d+(?:\.\d+)*\.?\s+\w"                             # 1. / 1.1 / 1.1.2
    r"|(?:ARTICLE|SECTION|CLAUSE|PART|SCHEDULE|EXHIBIT|APPENDIX)\s"
    r"|[A-Z][A-Z\s]{4,}$"                                # ALL-CAPS heading ≥ 5 chars
    r"))",
)


def clean_text(text: str) -> str:
    """Normalize Unicode, fix common encoding noise, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\x00", "").replace("�", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse runs of 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Normalize intra-line whitespace without touching newlines
    text = re.sub(r"[^\S\n]+", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def remove_repeated_lines(pages: list[str], threshold: float = 0.5) -> list[str]:
    """
    Remove lines that appear verbatim in more than *threshold* fraction of pages.

    Typical candidates: page numbers, document titles, "CONFIDENTIAL" stamps.
    Has no effect on lists with fewer than 3 pages (not enough signal).
    """
    if len(pages) < 3:
        return pages

    line_counts: Counter[str] = Counter()
    for page in pages:
        for line in set(page.split("\n")):
            stripped = line.strip()
            if stripped:
                line_counts[stripped] += 1

    total = len(pages)
    repeated = {line for line, count in line_counts.items() if count / total > threshold}
    if not repeated:
        return pages

    result = []
    for page in pages:
        kept = [ln for ln in page.split("\n") if ln.strip() not in repeated]
        result.append("\n".join(kept).strip())
    return result


def _split_by_headings(text: str) -> list[str]:
    """Split at clause/section headings; return original list if none found."""
    parts = _HEADING_RE.split(text)
    out = [p.strip() for p in parts if p.strip()]
    return out if len(out) > 1 else [text]


def _window_chunk(text: str, max_chars: int) -> list[str]:
    """Sentence-aware sliding window — last-resort chunking when no structure exists."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for sentence in sentences:
        if length + len(sentence) > max_chars and current:
            chunks.append(" ".join(current))
            current = [sentence]
            length = len(sentence)
        else:
            current.append(sentence)
            length += len(sentence) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """
    Recursively split *text* into chunks no longer than *max_chars*.

    Splitting priority:
      1. Heading-based (clause/section markers).
      2. Paragraph-based (blank lines).
      3. Sentence-window fallback.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    # Try heading split
    parts = _split_by_headings(text)
    if len(parts) > 1:
        result: list[str] = []
        for part in parts:
            result.extend(split_text(part, max_chars))
        return result

    # Try paragraph split
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) > 1:
        result = []
        for para in paragraphs:
            result.extend(split_text(para, max_chars))
        return result

    # Sentence-window fallback
    return _window_chunk(text, max_chars)


def chunk_pages(
    page_texts: list[str],
    max_chars: int = MAX_CHUNK_CHARS,
) -> tuple[list[str], list[int]]:
    """
    Clean and chunk a list of page texts into bounded fragments.

    Returns:
        (chunk_texts, chunk_page_numbers) — parallel lists where
        chunk_page_numbers[i] is the 1-indexed PDF/source page that
        chunk_texts[i] was extracted from.

    For TXT files (which arrive as a single element), all chunks carry
    page number 1.  For PDFs, chunks inherit the page number of the
    PDF page they were split from.

    Strategy: paragraph-first, then within each paragraph apply
    heading-based or window chunking only if the paragraph is over
    *max_chars*.  Splitting at blank lines first preserves retrieval
    granularity — each paragraph becomes its own fragment — while the
    inner ``split_text`` call enforces the length cap on long paragraphs.
    """
    cleaned = [clean_text(t) for t in page_texts]
    cleaned = remove_repeated_lines(cleaned)

    texts: list[str] = []
    pages: list[int] = []

    for page_idx, text in enumerate(cleaned):
        page_num = page_idx + 1
        if not text.strip():
            continue
        # Primary split: blank lines preserve paragraph granularity.
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text]
        for para in paragraphs:
            for chunk in split_text(para, max_chars):
                if len(chunk.strip()) >= MIN_CHUNK_CHARS:
                    texts.append(chunk)
                    pages.append(page_num)

    # Guarantee at least one chunk even for very short documents
    if not texts:
        for page_idx, text in enumerate(cleaned):
            stripped = text.strip()
            if stripped:
                texts.append(stripped)
                pages.append(page_idx + 1)
                break

    return texts, pages
