"""
repository.py — Document storage abstraction for LuminaClause.

This module defines a structural Protocol (PEP 544) for document persistence
and provides two implementations:

  JsonDocumentRepository
      Wraps the existing ``store.py`` functions.  Active by default when
      ``STORAGE_BACKEND=json`` (or the var is unset).  All existing test
      monkeypatching (``store.INDEX_FILE``, ``store.DATA_DIR``) continues to
      work because every method delegates to the store functions at call time.

  PostgresDocumentRepository
      Placeholder that raises ``NotImplementedError`` at construction time.
      Selecting this backend before ``store_pg.py`` is implemented fails
      immediately and loudly rather than partway through a request.

Factory
-------
``get_repository()`` is called once at application startup in ``main.py`` and
the result is stored as ``main.repo``.  Every route calls ``repo.*`` instead of
importing store functions directly, so swapping the backend requires only two
changes: implement ``PostgresDocumentRepository`` and set the env var.

Configuration
-------------
  STORAGE_BACKEND=json      — default; JSON filesystem (data/documents.json)
  STORAGE_BACKEND=postgres  — raises ValueError (not yet implemented)

Migration path
--------------
1. Add asyncpg or SQLAlchemy to requirements.txt.
2. Create ``store_pg.py`` with the same function signatures as ``store.py``
   (the contract is documented in ``docs/database-schema.md``).
3. Implement ``PostgresDocumentRepository`` methods to delegate to ``store_pg``.
4. Remove the ``__init__`` guard in ``PostgresDocumentRepository``.
5. Set ``STORAGE_BACKEND=postgres`` in the deployment environment.
6. Run the existing test suite — no test changes required because every test
   that talks to the store does so via monkeypatched ``store.*`` attributes.
"""
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from . import store as _store
from .models import ActivityItem, CommentItem, DocumentDetail, DocumentSummary


# ---------------------------------------------------------------------------
# Protocol  (structural interface — no ABC inheritance required)
# ---------------------------------------------------------------------------

@runtime_checkable
class DocumentRepository(Protocol):
    """
    Minimal persistence contract for LuminaClause documents.

    All method signatures mirror the public API of ``store.py``.  Adding or
    removing a method here is a breaking change for all implementations.
    """

    def list_documents(self) -> list[DocumentDetail]:
        """Return every document currently in the store."""
        ...

    def get_document(self, doc_id: str) -> DocumentDetail | None:
        """Return one document by id, or ``None`` if not found."""
        ...

    def create_document(
        self,
        filename: str,
        page_texts: list[str],
        summary: DocumentSummary,
        *,
        version_group_id: str | None = None,
        extraction_method: str = "text",
        owner: str = "",
    ) -> DocumentDetail:
        """Persist a new document and return it."""
        ...

    def create_document_version(
        self,
        source_doc_id: str,
        filename: str,
        page_texts: list[str],
        summary: DocumentSummary,
        extraction_method: str = "text",
    ) -> DocumentDetail | None:
        """
        Create a new version of an existing document's version group.

        Returns ``None`` when *source_doc_id* does not exist.
        """
        ...

    def list_document_versions(self, doc_id: str) -> list[DocumentDetail]:
        """Return all versions for *doc_id*'s version group, newest first."""
        ...

    def delete_document(self, doc_id: str) -> bool:
        """Delete a document; return ``True`` if found and deleted."""
        ...

    def add_activity(
        self, doc_id: str, item: ActivityItem
    ) -> DocumentDetail | None:
        """Prepend an activity event; return the updated document or ``None``."""
        ...

    def share_document(
        self, doc_id: str, email: str
    ) -> DocumentDetail | None:
        """Add *email* to shared_with; return the updated document or ``None``."""
        ...

    def add_comment(
        self, doc_id: str, comment: CommentItem
    ) -> DocumentDetail | None:
        """Prepend a comment; return the updated document or ``None``."""
        ...

    def update_review_status(
        self, doc_id: str, status: str
    ) -> DocumentDetail | None:
        """Set review_status; return the updated document or ``None``."""
        ...

    def update_metadata(
        self,
        doc_id: str,
        *,
        owner: str,
        counterparty: str,
        contract_type: str,
        effective_date: str,
        expiry_date: str,
        renewal_date: str,
    ) -> DocumentDetail | None:
        """Update contract metadata fields; return the updated document or ``None``."""
        ...


# ---------------------------------------------------------------------------
# JSON implementation
# ---------------------------------------------------------------------------

class JsonDocumentRepository:
    """
    Document repository backed by ``data/documents.json``.

    Every method delegates to the corresponding ``store.*`` function.  The
    delegation happens at call time, so monkeypatching ``store.INDEX_FILE``
    (as existing tests do) takes effect correctly — the store functions read
    that attribute when they are called, not when this class is instantiated.
    """

    def list_documents(self) -> list[DocumentDetail]:
        return _store.list_documents()

    def get_document(self, doc_id: str) -> DocumentDetail | None:
        return _store.get_document(doc_id)

    def create_document(
        self,
        filename: str,
        page_texts: list[str],
        summary: DocumentSummary,
        *,
        version_group_id: str | None = None,
        extraction_method: str = "text",
        owner: str = "",
    ) -> DocumentDetail:
        return _store.create_document(
            filename,
            page_texts,
            summary,
            version_group_id=version_group_id,
            extraction_method=extraction_method,
            owner=owner,
        )

    def create_document_version(
        self,
        source_doc_id: str,
        filename: str,
        page_texts: list[str],
        summary: DocumentSummary,
        extraction_method: str = "text",
    ) -> DocumentDetail | None:
        return _store.create_document_version(
            source_doc_id,
            filename,
            page_texts,
            summary,
            extraction_method=extraction_method,
        )

    def list_document_versions(self, doc_id: str) -> list[DocumentDetail]:
        return _store.list_document_versions(doc_id)

    def delete_document(self, doc_id: str) -> bool:
        return _store.delete_document(doc_id)

    def add_activity(
        self, doc_id: str, item: ActivityItem
    ) -> DocumentDetail | None:
        return _store.add_activity(doc_id, item)

    def share_document(
        self, doc_id: str, email: str
    ) -> DocumentDetail | None:
        return _store.share_document(doc_id, email)

    def add_comment(
        self, doc_id: str, comment: CommentItem
    ) -> DocumentDetail | None:
        return _store.add_comment(doc_id, comment)

    def update_review_status(
        self, doc_id: str, status: str
    ) -> DocumentDetail | None:
        return _store.update_review_status(doc_id, status)

    def update_metadata(
        self,
        doc_id: str,
        *,
        owner: str,
        counterparty: str,
        contract_type: str,
        effective_date: str,
        expiry_date: str,
        renewal_date: str,
    ) -> DocumentDetail | None:
        return _store.update_metadata(
            doc_id,
            owner=owner,
            counterparty=counterparty,
            contract_type=contract_type,
            effective_date=effective_date,
            expiry_date=expiry_date,
            renewal_date=renewal_date,
        )


# ---------------------------------------------------------------------------
# PostgreSQL placeholder
# ---------------------------------------------------------------------------

class PostgresDocumentRepository:
    """
    Placeholder for the PostgreSQL-backed document repository.

    **Not yet implemented.**  Raises ``NotImplementedError`` at construction
    time so selecting this backend before it is ready fails immediately and
    loudly — at startup, not mid-request.

    Migration path
    --------------
    1. Add asyncpg or SQLAlchemy to ``backend/requirements.txt``.
    2. Implement each method using the schema in ``db/schema.sql`` and the
       interface contract in ``docs/database-schema.md``.
    3. Delete the ``__init__`` override below.
    4. Run the existing test suite — no test changes required.
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "PostgresDocumentRepository is not yet implemented. "
            "See docs/database-schema.md for the interface contract and "
            "db/schema.sql for the target schema. "
            "Set STORAGE_BACKEND=json to use the default local JSON store."
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_repository() -> DocumentRepository:
    """
    Return the active document repository based on ``STORAGE_BACKEND``.

    +-------------------+------------------------------------------------------+
    | STORAGE_BACKEND   | Result                                               |
    +===================+======================================================+
    | ``json`` (default)| ``JsonDocumentRepository``                           |
    | ``postgres``      | raises ``ValueError`` (not yet implemented)          |
    | anything else     | raises ``ValueError`` with the unrecognised value    |
    +-------------------+------------------------------------------------------+

    Raises ``ValueError`` on unknown or unimplemented backends so that
    misconfiguration is detected at startup, not during the first request.
    """
    backend = os.getenv("STORAGE_BACKEND", "json").strip().lower()

    if backend == "json":
        return JsonDocumentRepository()

    if backend == "postgres":
        raise ValueError(
            "STORAGE_BACKEND=postgres is not yet implemented. "
            "Implement PostgresDocumentRepository in repository.py first. "
            "Set STORAGE_BACKEND=json to use the default local JSON store."
        )

    raise ValueError(
        f"Unknown STORAGE_BACKEND={backend!r}. "
        "Supported values: json"
    )
