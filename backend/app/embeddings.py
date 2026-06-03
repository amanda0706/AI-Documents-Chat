"""
embeddings.py — Local deterministic vector retrieval layer.

Architecture
------------
Every document fragment is mapped to a fixed-dimension float vector and
stored in ``data/embeddings.json``.  At query time the query string is
embedded with the same function and the top-k fragments are returned by
cosine similarity.

Local embedding function
------------------------
``local_embed`` uses the *hashing trick*: each word is hashed (MD5) to a
bucket index (mod EMBED_DIM) and a sign (+/-1 derived from a higher bit).
The accumulated bucket values are L2-normalised to a unit vector.

Properties:
- Fully deterministic — identical text always produces the same vector.
- Zero external dependencies — pure Python stdlib.
- Dimension: ``EMBED_DIM`` (128 floats).
- Not semantically meaningful at this scale; words that collide into the
  same bucket look similar even when unrelated.  Suitable for demo and
  integration testing only.

Migration path to production
-----------------------------
Replace ``local_embed`` with a real embeddings call::

    # OpenAI (1536-dim)
    from openai import OpenAI
    client = OpenAI(api_key=...)
    response = client.embeddings.create(
        model="text-embedding-3-small", input=text
    )
    return response.data[0].embedding

    # sentence-transformers (local GPU-capable, 384-dim)
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model.encode(text).tolist()

Store vectors in PostgreSQL + pgvector::

    ALTER TABLE fragments ADD COLUMN embedding vector(1536);
    CREATE INDEX ON fragments
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);

    -- nearest-neighbour query
    SELECT fragment_id, text, 1 - (embedding <=> $query_vec) AS score
    FROM fragments
    WHERE document_id = $doc_id
    ORDER BY embedding <=> $query_vec
    LIMIT $top_k;
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EMBED_DIM: int = 128
"""Dimensionality of local demo embeddings.
   Production embeddings (OpenAI text-embedding-3-small) use 1536 dims."""

_EMBED_FILE = Path(__file__).resolve().parent.parent / "data" / "embeddings.json"


# ---------------------------------------------------------------------------
# Local deterministic embedding
# ---------------------------------------------------------------------------

def _word_tokens(text: str) -> list[str]:
    """Return lowercase alphabetic tokens of length >= 3."""
    return re.findall(r"[a-zA-Z]{3,}", text.lower())


def local_embed(text: str) -> list[float]:
    """
    Return a deterministic ``EMBED_DIM``-dimensional unit vector for *text*.

    Uses the hashing trick: each word token is hashed via MD5, mapped to a
    bucket index (``hash mod EMBED_DIM``), and a signed count (+/-1) is
    accumulated in that bucket.  The result is L2-normalised so that the
    dot product of two vectors equals their cosine similarity.

    Empty or whitespace-only text returns the zero vector (not normalised).
    """
    vector = [0.0] * EMBED_DIM
    tokens = _word_tokens(text)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.md5(token.encode()).hexdigest()
        h = int(digest[:8], 16)
        dim = h % EMBED_DIM
        sign = 1.0 if (h >> 31) & 1 else -1.0
        vector[dim] += sign
    magnitude = math.sqrt(sum(v * v for v in vector))
    if magnitude > 0:
        vector = [v / magnitude for v in vector]
    return vector


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Return the cosine similarity of two vectors in [-1, 1].

    When both vectors are unit-normalised (as produced by ``local_embed``)
    this is simply the dot product, clamped for floating-point safety.
    """
    dot = sum(x * y for x, y in zip(a, b))
    return float(max(-1.0, min(1.0, dot)))


# ---------------------------------------------------------------------------
# Embedding record
# ---------------------------------------------------------------------------

@dataclass
class EmbeddingRecord:
    """One fragment's embedding with its provenance metadata."""
    document_id: str
    fragment_id: str
    page: int
    text: str
    vector: list[float]
    provider: str
    dim: int


# ---------------------------------------------------------------------------
# Persistent index  (data/embeddings.json)
# ---------------------------------------------------------------------------

def _load_raw() -> dict[str, dict]:
    """Load the raw JSON index; returns ``{}`` if the file is missing or corrupt."""
    if not _EMBED_FILE.exists():
        return {}
    try:
        return json.loads(_EMBED_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_raw(index: dict[str, dict]) -> None:
    _EMBED_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _EMBED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_EMBED_FILE)


def upsert_embeddings(records: list[EmbeddingRecord]) -> None:
    """Write (or overwrite) embedding records, keyed by ``fragment_id``."""
    index = _load_raw()
    for rec in records:
        index[rec.fragment_id] = {
            "document_id": rec.document_id,
            "fragment_id": rec.fragment_id,
            "page": rec.page,
            "text": rec.text,
            "vector": rec.vector,
            "provider": rec.provider,
            "dim": rec.dim,
        }
    _save_raw(index)


def delete_document_embeddings(doc_id: str) -> int:
    """Remove all embeddings for *doc_id*.  Returns the count of removed records."""
    index = _load_raw()
    to_remove = [fid for fid, rec in index.items() if rec.get("document_id") == doc_id]
    for fid in to_remove:
        del index[fid]
    if to_remove:
        _save_raw(index)
    return len(to_remove)


def get_document_embeddings(
    doc_id: str, *, include_vectors: bool = False
) -> list[dict]:
    """
    Return all embedding records for *doc_id*, sorted by page number.

    By default vectors are omitted (128-float arrays are large and rarely
    useful in a list response).  Pass ``include_vectors=True`` to include them.
    """
    index = _load_raw()
    records = [rec for rec in index.values() if rec.get("document_id") == doc_id]
    records.sort(key=lambda r: r.get("page", 0))
    if include_vectors:
        return records
    return [{k: v for k, v in rec.items() if k != "vector"} for rec in records]


def vector_search(
    query: str,
    doc_id: str,
    *,
    top_k: int = 3,
) -> list[tuple[dict, float]]:
    """
    Return the top-*k* fragments for *query* ranked by cosine similarity.

    Returns a list of ``(metadata_dict, score)`` tuples, sorted descending.
    ``metadata_dict`` contains all record fields except ``vector``.
    Returns ``[]`` when no embeddings exist for *doc_id*.
    """
    index = _load_raw()
    records = [rec for rec in index.values() if rec.get("document_id") == doc_id]
    if not records:
        return []
    query_vec = local_embed(query)
    scored: list[tuple[dict, float]] = []
    for rec in records:
        vec = rec.get("vector", [])
        if vec:
            score = cosine_similarity(query_vec, vec)
            meta = {k: v for k, v in rec.items() if k != "vector"}
            scored.append((meta, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


# ---------------------------------------------------------------------------
# Reindex helper
# ---------------------------------------------------------------------------

def reindex_document(
    doc: object,  # DocumentDetail — avoid circular import
    *,
    provider: str = "local",
) -> list[EmbeddingRecord]:
    """
    Compute embeddings for every fragment in *doc* and persist them.

    The *provider* field is stored for future use when replacing
    ``local_embed`` with a cloud embeddings API.  Currently all embeddings
    are always computed locally regardless of this value.
    """
    records = [
        EmbeddingRecord(
            document_id=doc.id,
            fragment_id=frag.id,
            page=frag.page,
            text=frag.text,
            vector=local_embed(frag.text),
            provider=provider,
            dim=EMBED_DIM,
        )
        for frag in doc.fragments
        if frag.text.strip()
    ]
    upsert_embeddings(records)
    return records
