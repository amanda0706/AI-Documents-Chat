"""
test_postgres_repository.py — Tests for the PostgreSQL document repository.

Unit tests
----------
All unit tests mock ``backend.app.store_pg._connection`` so they run without
Docker, a real PostgreSQL instance, or DATABASE_URL being set.  The mock
cursor is configured to return pre-built dict-like values that match what
psycopg2.extras.RealDictCursor returns in production.

Integration tests
-----------------
Marked with ``pytest.mark.integration``.  Skipped automatically unless
``TEST_DATABASE_URL`` is set in the environment.  When running integration
tests, the suite:

  1. Connects to the database at TEST_DATABASE_URL (NOT DATABASE_URL).
  2. Applies the schema from db/schema.sql to a fresh test schema.
  3. Runs real CRUD operations.
  4. Drops the test schema in a finally block.

Accidental production-database guard
-------------------------------------
Integration tests read exclusively from ``TEST_DATABASE_URL``.  They never
read ``DATABASE_URL``, so a misconfigured environment cannot silently point
tests at a production database.

SQL injection
-------------
All parameterised queries in store_pg.py use %s placeholders.  Unit tests
verify that ``cur.execute`` is called with a tuple of values (never with
f-strings or %-formatted SQL strings).

Secret leakage
--------------
``TEST_DATABASE_URL`` is read from the environment but never printed,
logged, or asserted against in any test output.
"""
from __future__ import annotations

import contextlib
import json
import os
import uuid
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from backend.app import store_pg
from backend.app.models import (
    ActivityItem,
    DocumentDetail,
    DocumentSummary,
    MissingClauseItem,
    RiskItem,
    SuggestionItem,
)
from backend.app.repository import PostgresDocumentRepository


# ---------------------------------------------------------------------------
# Constants / guards
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
_INTEGRATION_REASON = (
    "Integration tests require TEST_DATABASE_URL to be set. "
    "Example: TEST_DATABASE_URL=postgresql://luminaclause:secret@localhost:5432/luminaclause_test "
    "pytest backend/tests/test_postgres_repository.py -m integration"
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _sample_summary() -> DocumentSummary:
    return DocumentSummary(
        title="Test Contract",
        summary="A test contract with standard terms.",
        highlights=["Net-60 payment"],
        risks=[
            RiskItem(
                category="Payment",
                severity="medium",
                title="Net-60 payment window",
                explanation="Extended window increases cash-flow risk.",
                recommendation="Negotiate to Net-30.",
                score=55,
            )
        ],
        suggestions=[
            SuggestionItem(
                title="Shorten payment window",
                rationale="Reduces exposure.",
                proposed_text="Payment due within 30 days of invoice.",
            )
        ],
        missing_clauses=[],
        language="English",
        overall_score=60,
    )


def _sample_doc_row(doc_id: str, group_id: str | None = None) -> dict:
    """Return a dict that mimics a RealDictCursor document row."""
    gid = group_id or doc_id
    return {
        "id": uuid.UUID(doc_id),
        "filename": "contract.txt",
        "version_group_id": uuid.UUID(gid),
        "version_number": 1,
        "is_latest_version": True,
        "extraction_method": "text",
        "ocr_applied": False,
        "page_count": 2,
        "owner_email": "alice@example.com",
        "counterparty": "Acme Corp",
        "contract_type": "MSA",
        "effective_date": None,
        "expiry_date": None,
        "renewal_date": None,
        "review_status": "draft",
        "summary_title": "Test Contract",
        "summary_text": "A test contract with standard terms.",
        "summary_language": "English",
        "overall_score": 60,
        "summary_highlights": ["Net-60 payment"],
        "summary_risks": [
            {
                "category": "Payment",
                "severity": "medium",
                "title": "Net-60 payment window",
                "explanation": "Extended window increases cash-flow risk.",
                "recommendation": "Negotiate to Net-30.",
                "score": 55,
            }
        ],
        "summary_suggestions": [
            {
                "title": "Shorten payment window",
                "rationale": "Reduces exposure.",
                "proposed_text": "Payment due within 30 days of invoice.",
            }
        ],
        "summary_missing": [],
        "created_at": None,
        "updated_at": None,
    }


# ---------------------------------------------------------------------------
# Mock connection helpers
# ---------------------------------------------------------------------------

def _make_cursor(fetchone_seq: list = (), fetchall_seq: list = ()) -> MagicMock:
    """
    Build a mock cursor that behaves as a context manager.

    ``fetchone_seq`` — ordered list of values returned by successive fetchone() calls.
    ``fetchall_seq`` — ordered list of values returned by successive fetchall() calls.
    Values may be dicts (simulating RealDictRow) or None.
    """
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    if fetchone_seq:
        cur.fetchone.side_effect = list(fetchone_seq)
    if fetchall_seq:
        cur.fetchall.side_effect = list(fetchall_seq)
    return cur


def _make_conn(cur: MagicMock) -> MagicMock:
    """Build a mock connection whose cursor() returns the given mock cursor."""
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


@contextmanager
def _patch_connection(conn: MagicMock):
    """
    Context manager that patches store_pg._connection to yield the given mock
    while honouring the same commit/rollback contract as the real _connection:

      - conn.commit() is called on clean exit
      - conn.rollback() is called if an exception escapes
      - conn.close() is always called

    This lets tests assert that commit/rollback/close were invoked correctly.

    Usage::

        conn, cur = _make_conn(cur)
        with _patch_connection(conn):
            result = store_pg.get_document("some-id")
    """
    @contextmanager
    def _fake_ctx():
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    with patch("backend.app.store_pg._connection", _fake_ctx):
        yield


# ---------------------------------------------------------------------------
# Unit — missing DATABASE_URL guard
# ---------------------------------------------------------------------------

class TestConnectionGuard:
    def test_missing_database_url_raises_runtime_error(self, monkeypatch):
        """RuntimeError fires immediately when DATABASE_URL is not set."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
            with store_pg._connection():
                pass  # pragma: no cover

    def test_empty_database_url_raises_runtime_error(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "   ")
        with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
            with store_pg._connection():
                pass  # pragma: no cover

    def test_error_message_contains_example_url(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError, match="postgresql://"):
            with store_pg._connection():
                pass  # pragma: no cover


# ---------------------------------------------------------------------------
# Unit — get_document
# ---------------------------------------------------------------------------

class TestGetDocumentUnit:
    def test_returns_none_when_not_found(self):
        cur = _make_cursor(fetchone_seq=[None])
        conn = _make_conn(cur)
        with _patch_connection(conn):
            result = store_pg.get_document("nonexistent-id")
        assert result is None

    def test_uses_parameterised_query(self):
        """SELECT must use %s placeholder, not string interpolation."""
        doc_id = str(uuid.uuid4())
        cur = _make_cursor(fetchone_seq=[None])
        conn = _make_conn(cur)
        with _patch_connection(conn):
            store_pg.get_document(doc_id)
        # The first execute call's args[1] must be a tuple containing doc_id
        first_call = cur.execute.call_args_list[0]
        sql, params = first_call[0]
        assert "%s" in sql
        assert doc_id in params

    def test_returns_document_detail_on_hit(self):
        doc_id = str(uuid.uuid4())
        row = _sample_doc_row(doc_id)
        # fetchone for the document row; fetchall x4 for related tables
        cur = _make_cursor(
            fetchone_seq=[row],
            fetchall_seq=[
                [{"id": f"{doc_id}-0", "page": 1, "text": "Page one text."}],
                [],  # shares
                [],  # comments
                [{"type": "upload", "label": "Document uploaded", "detail": ""}],
            ],
        )
        conn = _make_conn(cur)
        with _patch_connection(conn):
            result = store_pg.get_document(doc_id)

        assert isinstance(result, DocumentDetail)
        assert result.id == doc_id
        assert result.filename == "contract.txt"
        assert result.owner == "alice@example.com"
        assert len(result.fragments) == 1
        assert result.fragments[0].page == 1

    def test_connection_committed(self):
        cur = _make_cursor(fetchone_seq=[None])
        conn = _make_conn(cur)
        with _patch_connection(conn):
            store_pg.get_document("x")
        conn.commit.assert_called_once()

    def test_related_queries_use_parameterised_placeholders(self):
        """All four _fetch_related queries must use %s, not string formatting."""
        doc_id = str(uuid.uuid4())
        row = _sample_doc_row(doc_id)
        cur = _make_cursor(
            fetchone_seq=[row],
            fetchall_seq=[[], [], [], []],
        )
        conn = _make_conn(cur)
        with _patch_connection(conn):
            store_pg.get_document(doc_id)

        for call_args in cur.execute.call_args_list[1:]:  # skip the main SELECT
            sql, params = call_args[0]
            assert "%s" in sql, f"Query missing %s placeholder: {sql!r}"
            assert isinstance(params, tuple)


# ---------------------------------------------------------------------------
# Unit — list_documents
# ---------------------------------------------------------------------------

class TestListDocumentsUnit:
    def test_returns_empty_list_when_no_documents(self):
        cur = _make_cursor(fetchall_seq=[[]])
        conn = _make_conn(cur)
        with _patch_connection(conn):
            result = store_pg.list_documents()
        assert result == []

    def test_returns_one_document(self):
        doc_id = str(uuid.uuid4())
        row = _sample_doc_row(doc_id)
        cur = _make_cursor(
            fetchall_seq=[
                [row],   # main SELECT
                [],      # fragments
                [],      # shares
                [],      # comments
                [],      # activity
            ]
        )
        conn = _make_conn(cur)
        with _patch_connection(conn):
            result = store_pg.list_documents()

        assert len(result) == 1
        assert result[0].id == doc_id
        assert result[0].filename == "contract.txt"

    def test_returns_multiple_documents(self):
        id1 = str(uuid.uuid4())
        id2 = str(uuid.uuid4())
        rows = [_sample_doc_row(id1), _sample_doc_row(id2)]
        # main SELECT + 4 related queries per document = 9 fetchall calls
        cur = _make_cursor(
            fetchall_seq=[
                rows,  # main SELECT
                [], [], [], [],  # related for doc 1
                [], [], [], [],  # related for doc 2
            ]
        )
        conn = _make_conn(cur)
        with _patch_connection(conn):
            result = store_pg.list_documents()

        assert len(result) == 2

    def test_connection_committed(self):
        cur = _make_cursor(fetchall_seq=[[]])
        conn = _make_conn(cur)
        with _patch_connection(conn):
            store_pg.list_documents()
        conn.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Unit — delete_document
# ---------------------------------------------------------------------------

class TestDeleteDocumentUnit:
    def test_returns_false_when_not_found(self):
        cur = _make_cursor(fetchone_seq=[None])
        conn = _make_conn(cur)
        with _patch_connection(conn):
            result = store_pg.delete_document("nonexistent")
        assert result is False

    def test_returns_true_when_found(self):
        doc_id = str(uuid.uuid4())
        cur = _make_cursor(fetchone_seq=[{"id": uuid.UUID(doc_id)}])
        conn = _make_conn(cur)
        with _patch_connection(conn):
            result = store_pg.delete_document(doc_id)
        assert result is True

    def test_delete_uses_parameterised_sql(self):
        doc_id = str(uuid.uuid4())
        cur = _make_cursor(fetchone_seq=[{"id": uuid.UUID(doc_id)}])
        conn = _make_conn(cur)
        with _patch_connection(conn):
            store_pg.delete_document(doc_id)

        calls = cur.execute.call_args_list
        # Second call must be the DELETE with a tuple param
        delete_sql, delete_params = calls[1][0]
        assert "DELETE" in delete_sql
        assert "%s" in delete_sql
        assert doc_id in delete_params

    def test_no_delete_executed_when_not_found(self):
        """When the existence check fails no DELETE should be issued."""
        cur = _make_cursor(fetchone_seq=[None])
        conn = _make_conn(cur)
        with _patch_connection(conn):
            store_pg.delete_document("missing")

        executed_sqls = [c[0][0] for c in cur.execute.call_args_list]
        assert not any("DELETE" in sql for sql in executed_sqls)

    def test_connection_committed(self):
        doc_id = str(uuid.uuid4())
        cur = _make_cursor(fetchone_seq=[{"id": uuid.UUID(doc_id)}])
        conn = _make_conn(cur)
        with _patch_connection(conn):
            store_pg.delete_document(doc_id)
        conn.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Unit — create_document
# ---------------------------------------------------------------------------

class TestCreateDocumentUnit:
    def _make_create_cursor(self, version_count: int = 0) -> MagicMock:
        """Cursor whose first fetchone returns the version COUNT result."""
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = {"cnt": version_count}
        return cur

    def test_returns_document_detail(self):
        cur = self._make_create_cursor()
        conn = _make_conn(cur)
        with _patch_connection(conn):
            result = store_pg.create_document(
                "test.txt", ["Page one text."], _sample_summary()
            )
        assert isinstance(result, DocumentDetail)
        assert result.filename == "test.txt"
        assert result.version_number == 1

    def test_id_is_string_uuid(self):
        cur = self._make_create_cursor()
        conn = _make_conn(cur)
        with _patch_connection(conn):
            result = store_pg.create_document("f.txt", ["text"], _sample_summary())
        uuid.UUID(result.id)  # raises ValueError if not a valid UUID

    def test_fragment_inserted_for_nonempty_page(self):
        cur = self._make_create_cursor()
        conn = _make_conn(cur)
        with _patch_connection(conn):
            result = store_pg.create_document(
                "f.txt", ["non-empty page"], _sample_summary()
            )
        assert len(result.fragments) == 1
        assert result.fragments[0].page == 1

    def test_blank_pages_produce_no_fragments(self):
        cur = self._make_create_cursor()
        conn = _make_conn(cur)
        with _patch_connection(conn):
            result = store_pg.create_document(
                "f.txt", ["   ", "\n", "real content"], _sample_summary()
            )
        assert len(result.fragments) == 1
        assert result.fragments[0].page == 3

    def test_version_number_increments(self):
        """When two docs share a version_group_id the second gets version 2."""
        cur = self._make_create_cursor(version_count=1)
        conn = _make_conn(cur)
        group_id = str(uuid.uuid4())
        with _patch_connection(conn):
            result = store_pg.create_document(
                "v2.txt", ["content"], _sample_summary(),
                version_group_id=group_id,
            )
        assert result.version_number == 2

    def test_previous_version_demoted(self):
        """When version > 1, an UPDATE must set is_latest_version = FALSE."""
        cur = self._make_create_cursor(version_count=1)
        conn = _make_conn(cur)
        group_id = str(uuid.uuid4())
        with _patch_connection(conn):
            store_pg.create_document(
                "v2.txt", ["content"], _sample_summary(),
                version_group_id=group_id,
            )
        executed_sqls = [c[0][0] for c in cur.execute.call_args_list]
        assert any("UPDATE" in sql and "is_latest_version" in sql for sql in executed_sqls)

    def test_insert_uses_parameterised_sql(self):
        cur = self._make_create_cursor()
        conn = _make_conn(cur)
        with _patch_connection(conn):
            store_pg.create_document("f.txt", ["text"], _sample_summary())

        for call_args in cur.execute.call_args_list:
            sql = call_args[0][0]
            # Every call must carry params as a tuple (not inline string format)
            if "INSERT" in sql or "UPDATE" in sql or "SELECT" in sql:
                assert len(call_args[0]) == 2, f"Missing params for: {sql!r}"
                assert isinstance(call_args[0][1], tuple), (
                    f"Params not a tuple for: {sql!r}"
                )

    def test_upload_activity_in_returned_detail(self):
        cur = self._make_create_cursor()
        conn = _make_conn(cur)
        with _patch_connection(conn):
            result = store_pg.create_document("f.txt", ["text"], _sample_summary())
        assert any(a.type == "upload" for a in result.activity)

    def test_connection_committed(self):
        cur = self._make_create_cursor()
        conn = _make_conn(cur)
        with _patch_connection(conn):
            store_pg.create_document("f.txt", ["text"], _sample_summary())
        conn.commit.assert_called_once()

    def test_connection_rolled_back_on_error(self):
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.side_effect = Exception("DB error")
        conn = _make_conn(cur)
        with _patch_connection(conn):
            with pytest.raises(Exception, match="DB error"):
                store_pg.create_document("f.txt", ["text"], _sample_summary())
        conn.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# Unit — unimplemented stubs in store_pg
# ---------------------------------------------------------------------------

class TestStorePgStubs:
    @pytest.mark.parametrize("fn_name", [
        "create_document_version",
        "list_document_versions",
        "add_activity",
        "share_document",
        "add_comment",
        "update_review_status",
        "update_metadata",
    ])
    def test_stub_raises_not_implemented(self, fn_name):
        fn = getattr(store_pg, fn_name)
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            fn()

    def test_stub_error_mentions_json_fallback(self):
        with pytest.raises(NotImplementedError, match="STORAGE_BACKEND=json"):
            store_pg.add_comment()

    def test_stub_error_mentions_roadmap_docs(self):
        with pytest.raises(NotImplementedError, match="docs/architecture.md"):
            store_pg.share_document()


# ---------------------------------------------------------------------------
# Unit — PostgresDocumentRepository delegates to store_pg
# ---------------------------------------------------------------------------

class TestPostgresRepositoryDelegation:
    """Verify that the repository methods delegate to store_pg correctly."""

    def test_get_document_delegates(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(store_pg, "get_document", lambda doc_id: sentinel)
        repo = PostgresDocumentRepository()
        result = repo.get_document("any-id")
        assert result is sentinel

    def test_list_documents_delegates(self, monkeypatch):
        sentinel = [object()]
        monkeypatch.setattr(store_pg, "list_documents", lambda: sentinel)
        repo = PostgresDocumentRepository()
        result = repo.list_documents()
        assert result is sentinel

    def test_create_document_delegates(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(
            store_pg, "create_document",
            lambda *a, **kw: sentinel,
        )
        repo = PostgresDocumentRepository()
        result = repo.create_document("f.txt", [], _sample_summary())
        assert result is sentinel

    def test_delete_document_delegates(self, monkeypatch):
        monkeypatch.setattr(store_pg, "delete_document", lambda doc_id: True)
        repo = PostgresDocumentRepository()
        assert repo.delete_document("any-id") is True

    @pytest.mark.parametrize("method,args", [
        ("create_document_version", ("src", "f.txt", [], None)),
        ("list_document_versions", ("id",)),
        ("add_activity", ("id", None)),
        ("share_document", ("id", "x@x.com")),
        ("add_comment", ("id", None)),
        ("update_review_status", ("id", "approved")),
        ("update_metadata", ("id",)),
    ])
    def test_stub_methods_raise_not_implemented(self, method, args):
        repo = PostgresDocumentRepository()
        with pytest.raises(NotImplementedError):
            getattr(repo, method)(*args)


# ---------------------------------------------------------------------------
# Integration tests — skipped unless TEST_DATABASE_URL is set
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason=_INTEGRATION_REASON,
)
class TestPostgresIntegration:
    """
    Real round-trip tests against a live PostgreSQL instance.

    These tests run exclusively against TEST_DATABASE_URL — never DATABASE_URL —
    to prevent accidental modification of a production database.

    Each test class uses a fresh temporary schema that is dropped in teardown.
    The schema is created from db/schema.sql so the test database always
    reflects the current production schema definition.
    """

    SCHEMA_FILE = (
        __file__
        .__class__(  # pathlib.Path-compatible trick; actual path below
            os.path.join(
                os.path.dirname(__file__),
                "..", "..", "db", "schema.sql",
            )
        )
    )

    @pytest.fixture(autouse=True)
    def pg_env(self, monkeypatch):
        """
        Point DATABASE_URL at the test database (TEST_DATABASE_URL).
        Never reads the production DATABASE_URL variable.
        """
        monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)

    @pytest.fixture(autouse=True)
    def test_schema(self, pg_env):
        """
        Create a temporary schema, apply db/schema.sql, run the test, then DROP.

        Using a separate schema (namespace) isolates the integration tests from
        any existing data without requiring a dedicated empty database.
        """
        import psycopg2
        import psycopg2.extras

        schema_name = f"test_{uuid.uuid4().hex[:12]}"
        schema_sql_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "db", "schema.sql"
        )
        schema_ddl = open(schema_sql_path, encoding="utf-8").read()

        conn = psycopg2.connect(TEST_DATABASE_URL)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(f'CREATE SCHEMA "{schema_name}"')
                cur.execute(f'SET search_path TO "{schema_name}", public')
                # Apply the full schema DDL inside the test schema
                cur.execute(schema_ddl)
        finally:
            conn.close()

        # Make store_pg use the test schema for the duration of this test
        original_connect = store_pg.psycopg2.connect

        def _patched_connect(url, **kw):
            c = original_connect(url, **kw)
            with c.cursor() as cur:
                cur.execute(f'SET search_path TO "{schema_name}", public')
            c.commit()
            return c

        store_pg.psycopg2.connect = _patched_connect  # type: ignore[attr-defined]

        yield schema_name

        store_pg.psycopg2.connect = original_connect  # type: ignore[attr-defined]

        # Teardown: drop the entire test schema
        conn2 = psycopg2.connect(TEST_DATABASE_URL)
        conn2.autocommit = True
        try:
            with conn2.cursor() as cur:
                cur.execute(f'DROP SCHEMA "{schema_name}" CASCADE')
        finally:
            conn2.close()

    def test_create_and_get_document(self):
        doc = store_pg.create_document(
            "integration.txt", ["Contract text page 1.", "Page two."],
            _sample_summary(),
        )
        assert doc.id
        fetched = store_pg.get_document(doc.id)
        assert fetched is not None
        assert fetched.filename == "integration.txt"
        assert fetched.version_number == 1
        assert len(fetched.fragments) == 2

    def test_list_documents_includes_created(self):
        doc = store_pg.create_document(
            "listed.txt", ["content"], _sample_summary()
        )
        all_docs = store_pg.list_documents()
        ids = [d.id for d in all_docs]
        assert doc.id in ids

    def test_delete_document_removes_row(self):
        doc = store_pg.create_document(
            "deleteme.txt", ["some text"], _sample_summary()
        )
        assert store_pg.delete_document(doc.id) is True
        assert store_pg.get_document(doc.id) is None

    def test_delete_nonexistent_returns_false(self):
        assert store_pg.delete_document(str(uuid.uuid4())) is False

    def test_delete_cascades_to_fragments(self):
        """Deleting a document must remove its fragments via CASCADE."""
        import psycopg2
        import psycopg2.extras

        doc = store_pg.create_document(
            "cascade.txt", ["fragment text"], _sample_summary()
        )
        store_pg.delete_document(doc.id)

        conn = psycopg2.connect(
            TEST_DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM document_fragments WHERE document_id = %s",
                    (doc.id,),
                )
                row = cur.fetchone()
                assert row["cnt"] == 0, "Fragments not removed by CASCADE"
        finally:
            conn.close()

    def test_get_document_returns_none_for_missing(self):
        assert store_pg.get_document(str(uuid.uuid4())) is None

    def test_owner_round_trips(self):
        doc = store_pg.create_document(
            "owner.txt", ["text"], _sample_summary(), owner="bob@example.com"
        )
        fetched = store_pg.get_document(doc.id)
        assert fetched is not None
        assert fetched.owner == "bob@example.com"

    def test_summary_round_trips(self):
        summary = _sample_summary()
        doc = store_pg.create_document("summary.txt", ["text"], summary)
        fetched = store_pg.get_document(doc.id)
        assert fetched is not None
        assert fetched.summary.title == summary.title
        assert fetched.summary.overall_score == summary.overall_score
        assert len(fetched.summary.risks) == len(summary.risks)

    def test_upload_activity_persisted(self):
        doc = store_pg.create_document("activity.txt", ["text"], _sample_summary())
        fetched = store_pg.get_document(doc.id)
        assert fetched is not None
        assert any(a.type == "upload" for a in fetched.activity)
