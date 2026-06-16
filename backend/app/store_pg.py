"""
store_pg.py — PostgreSQL persistence for LuminaClause (core document lifecycle).

Implements the four core document operations against the schema in db/schema.sql:
  create_document  — INSERT document + fragments + initial activity in one transaction
  list_documents   — SELECT all documents with their related rows
  get_document     — SELECT one document with related rows
  delete_document  — DELETE document (CASCADE removes fragments, embeddings, shares,
                     comments, and activity automatically)

All other store.py-equivalent operations are intentional stubs that raise
NotImplementedError with a clear message pointing at the roadmap.

SQL injection
-------------
Every value is passed through psycopg2 parameterised placeholders (%s).
No string interpolation is used anywhere in the query bodies.

Connection model
----------------
``_connection()`` is a context manager that:
  - reads DATABASE_URL from the environment at *call time* (not import time),
    so monkeypatching os.environ in tests takes effect,
  - commits on clean exit,
  - rolls back and re-raises on any exception,
  - always closes the connection in the finally block.

Each public function acquires its own connection and holds it only for the
duration of the operation.

Transaction model
-----------------
  create_document  — single transaction: document row + fragments + activity.
  delete_document  — single DELETE; FK CASCADE handles children automatically.
  list_documents   — read-only; commit is a no-op.
  get_document     — read-only; commit is a no-op.

RealDictCursor
--------------
psycopg2.extras.RealDictCursor makes every fetched row a plain dict, so the
helper functions can access columns by name without index gymnastics.

JSONB columns
-------------
psycopg2 automatically deserialises JSONB → Python list/dict on read.
On write, values are serialised via json.dumps() before passing to %s.

UUID columns
------------
UUID column values are returned as uuid.UUID objects by psycopg2.
str() is applied before constructing model objects so the API keeps
returning plain strings.

Migration path
--------------
1. Implement the remaining stubs (create_document_version, add_comment, etc.)
   following the pattern established here.
2. Remove the NotImplementedError stub bodies.
3. Set STORAGE_BACKEND=postgres in the deployment environment.
4. Run the existing test suite — no test changes required for the JSON path.
"""
from __future__ import annotations

import contextlib
import json
import os
import uuid
from collections.abc import Generator
from typing import Any

import psycopg2
import psycopg2.extras

from .models import (
    ActivityItem,
    CommentItem,
    DocumentDetail,
    DocumentFragment,
    DocumentSummary,
    MissingClauseItem,
    RiskItem,
    SuggestionItem,
)


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """
    Yield a psycopg2 connection that commits on success and rolls back on error.

    DATABASE_URL is read from the environment at call time so that
    ``monkeypatch.setenv("DATABASE_URL", ...)`` in tests takes effect.

    Raises RuntimeError immediately when DATABASE_URL is not set, so that
    misconfiguration is detected at the first operation — not silently.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Provide a PostgreSQL connection URL when STORAGE_BACKEND=postgres. "
            "Example: postgresql://luminaclause:secret@localhost:5432/luminaclause"
        )
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Row → model helpers
# ---------------------------------------------------------------------------

def _str_date(val: Any) -> str:
    """Convert a DATE/None from PostgreSQL to an ISO-8601 string or empty."""
    return str(val) if val else ""


def _build_summary(row: dict) -> DocumentSummary:
    return DocumentSummary(
        title=row["summary_title"],
        summary=row["summary_text"],
        highlights=row["summary_highlights"],
        risks=[RiskItem(**r) for r in row["summary_risks"]],
        suggestions=[SuggestionItem(**s) for s in row["summary_suggestions"]],
        missing_clauses=[MissingClauseItem(**m) for m in row["summary_missing"]],
        language=row["summary_language"],
        overall_score=row["overall_score"],
    )


def _fetch_related(
    cur: psycopg2.extensions.cursor,
    doc_id: str,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """
    Fetch fragments, shares, comments, and activity for one document.

    All four queries use parameterised placeholders — no string interpolation.
    Returns four plain lists of RealDictRow objects (behave like dicts).
    """
    cur.execute(
        "SELECT id, page, text"
        "  FROM document_fragments"
        " WHERE document_id = %s"
        " ORDER BY page ASC",
        (doc_id,),
    )
    fragments = list(cur.fetchall())

    cur.execute(
        "SELECT shared_with_email"
        "  FROM document_shares"
        " WHERE document_id = %s",
        (doc_id,),
    )
    shares = list(cur.fetchall())

    cur.execute(
        "SELECT author, body"
        "  FROM comments"
        " WHERE document_id = %s"
        " ORDER BY created_at DESC",
        (doc_id,),
    )
    comments = list(cur.fetchall())

    cur.execute(
        "SELECT type, label, detail"
        "  FROM activity_events"
        " WHERE document_id = %s"
        " ORDER BY created_at DESC",
        (doc_id,),
    )
    activity = list(cur.fetchall())

    return fragments, shares, comments, activity


def _row_to_detail(
    row: dict,
    fragments: list[dict],
    shares: list[dict],
    comments: list[dict],
    activity: list[dict],
) -> DocumentDetail:
    """Assemble a DocumentDetail from database rows and related data."""
    return DocumentDetail(
        id=str(row["id"]),
        filename=row["filename"],
        version_group_id=str(row["version_group_id"]),
        version_number=row["version_number"],
        is_latest_version=row["is_latest_version"],
        extraction_method=row["extraction_method"],
        ocr_applied=row["ocr_applied"],
        page_count=row["page_count"],
        owner=row["owner_email"],
        counterparty=row["counterparty"],
        contract_type=row["contract_type"],
        effective_date=_str_date(row["effective_date"]),
        expiry_date=_str_date(row["expiry_date"]),
        renewal_date=_str_date(row["renewal_date"]),
        review_status=row["review_status"],
        shared_with=[s["shared_with_email"] for s in shares],
        comments=[CommentItem(author=c["author"], body=c["body"]) for c in comments],
        activity=[
            ActivityItem(type=a["type"], label=a["label"], detail=a["detail"])
            for a in activity
        ],
        summary=_build_summary(row),
        fragments=[
            DocumentFragment(id=f["id"], page=f["page"], text=f["text"])
            for f in fragments
        ],
    )


# ---------------------------------------------------------------------------
# Core operations (implemented)
# ---------------------------------------------------------------------------

def create_document(
    filename: str,
    page_texts: list[str],
    summary: DocumentSummary,
    *,
    version_group_id: str | None = None,
    extraction_method: str = "text",
    owner: str = "",
    chunk_pages: list[int] | None = None,
) -> DocumentDetail:
    """
    Persist a new document with its fragments and an initial upload activity.

    All three INSERTs run inside a single transaction.  The UNIQUE index on
    (version_group_id) WHERE is_latest_version = TRUE is honoured by
    marking the previous latest version FALSE before inserting the new one.

    Parameters use %s placeholders throughout — no string interpolation.
    """
    doc_id = str(uuid.uuid4())
    group_id = version_group_id or doc_id

    with _connection() as conn:
        with conn.cursor() as cur:

            # --- determine version number -----------------------------------
            cur.execute(
                "SELECT COUNT(*) AS cnt"
                "  FROM documents"
                " WHERE version_group_id = %s",
                (group_id,),
            )
            row = cur.fetchone()
            version_number = (row["cnt"] if row else 0) + 1

            # --- demote previous latest version -----------------------------
            if version_number > 1:
                cur.execute(
                    "UPDATE documents"
                    "   SET is_latest_version = FALSE"
                    " WHERE version_group_id = %s",
                    (group_id,),
                )

            # --- insert document row ----------------------------------------
            cur.execute(
                """
                INSERT INTO documents (
                    id, filename, version_group_id, version_number,
                    is_latest_version, extraction_method, ocr_applied,
                    page_count, owner_email,
                    summary_title, summary_text, summary_language, overall_score,
                    summary_highlights, summary_risks,
                    summary_suggestions, summary_missing
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s
                )
                """,
                (
                    doc_id,
                    filename,
                    group_id,
                    version_number,
                    True,
                    extraction_method,
                    extraction_method == "ocr",
                    len(page_texts),
                    owner,
                    summary.title,
                    summary.summary,
                    summary.language,
                    summary.overall_score,
                    json.dumps(summary.highlights),
                    json.dumps([r.model_dump() for r in summary.risks]),
                    json.dumps([s.model_dump() for s in summary.suggestions]),
                    json.dumps([m.model_dump() for m in summary.missing_clauses]),
                ),
            )

            # --- insert fragments --------------------------------------------
            page_numbers = chunk_pages if chunk_pages else list(range(1, len(page_texts) + 1))
            pairs = [(text, pg) for text, pg in zip(page_texts, page_numbers) if text.strip()]
            built_fragments: list[DocumentFragment] = []
            for index, (text, pg) in enumerate(pairs):
                frag_id = f"{doc_id}-{index}"
                cur.execute(
                    "INSERT INTO document_fragments"
                    "    (id, document_id, page, text)"
                    " VALUES (%s, %s, %s, %s)",
                    (frag_id, doc_id, pg, text),
                )
                built_fragments.append(
                    DocumentFragment(id=frag_id, page=pg, text=text)
                )

            # --- insert upload activity -------------------------------------
            cur.execute(
                "INSERT INTO activity_events"
                "    (document_id, type, label, detail)"
                " VALUES (%s, %s, %s, %s)",
                (
                    doc_id,
                    "upload",
                    "Document uploaded",
                    "File added and analyzed locally.",
                ),
            )

    # Build and return the model directly (no round-trip SELECT needed).
    return DocumentDetail(
        id=doc_id,
        filename=filename,
        version_group_id=group_id,
        version_number=version_number,
        is_latest_version=True,
        extraction_method=extraction_method,
        ocr_applied=extraction_method == "ocr",
        page_count=len(page_texts),
        owner=owner,
        counterparty="",
        contract_type="",
        effective_date="",
        expiry_date="",
        renewal_date="",
        review_status="draft",
        shared_with=[],
        comments=[],
        activity=[
            ActivityItem(
                type="upload",
                label="Document uploaded",
                detail="File added and analyzed locally.",
            )
        ],
        summary=summary,
        fragments=built_fragments,
    )


def get_document(doc_id: str) -> DocumentDetail | None:
    """
    Return one document by id, or None if not found.

    Runs five parameterised SELECTs in a single connection:
    one for the document row, four for related tables.
    """
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM documents WHERE id = %s",
                (doc_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            fragments, shares, comments, activity = _fetch_related(cur, doc_id)

    return _row_to_detail(dict(row), fragments, shares, comments, activity)


def list_documents() -> list[DocumentDetail]:
    """
    Return all documents ordered by creation time (newest first).

    For each document row, four additional parameterised SELECTs fetch
    related data (fragments, shares, comments, activity).
    All queries run inside a single connection.
    """
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM documents ORDER BY created_at DESC",
            )
            rows = list(cur.fetchall())

            results: list[DocumentDetail] = []
            for row in rows:
                doc_id = str(row["id"])
                fragments, shares, comments, activity = _fetch_related(cur, doc_id)
                results.append(
                    _row_to_detail(dict(row), fragments, shares, comments, activity)
                )

    return results


def delete_document(doc_id: str) -> bool:
    """
    Delete a document by id.  Returns True if found and deleted, False otherwise.

    Fragments, embeddings (document_embeddings), shares, comments, and activity
    are removed automatically by the ON DELETE CASCADE foreign keys defined
    in db/schema.sql — no explicit child DELETEs are needed.

    Both the existence check and the DELETE use parameterised placeholders.
    """
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM documents WHERE id = %s",
                (doc_id,),
            )
            if cur.fetchone() is None:
                return False

            cur.execute(
                "DELETE FROM documents WHERE id = %s",
                (doc_id,),
            )

    return True


# ---------------------------------------------------------------------------
# Unimplemented stubs — fail clearly rather than silently
# ---------------------------------------------------------------------------

def _not_implemented(operation: str) -> None:
    raise NotImplementedError(
        f"store_pg.{operation} is not yet implemented. "
        "Use STORAGE_BACKEND=json for full document workflow support. "
        "See docs/architecture.md for the PostgreSQL migration roadmap."
    )


def create_document_version(*_a: Any, **_kw: Any) -> None:  # type: ignore[return]
    _not_implemented("create_document_version")


def list_document_versions(*_a: Any, **_kw: Any) -> None:  # type: ignore[return]
    _not_implemented("list_document_versions")


def add_activity(*_a: Any, **_kw: Any) -> None:  # type: ignore[return]
    _not_implemented("add_activity")


def share_document(*_a: Any, **_kw: Any) -> None:  # type: ignore[return]
    _not_implemented("share_document")


def add_comment(*_a: Any, **_kw: Any) -> None:  # type: ignore[return]
    _not_implemented("add_comment")


def update_review_status(*_a: Any, **_kw: Any) -> None:  # type: ignore[return]
    _not_implemented("update_review_status")


def update_metadata(*_a: Any, **_kw: Any) -> None:  # type: ignore[return]
    _not_implemented("update_metadata")
