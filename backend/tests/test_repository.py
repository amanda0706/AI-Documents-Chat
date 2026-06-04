"""
test_repository.py — Tests for the document repository abstraction.

Covers:
- Factory selection via STORAGE_BACKEND env var
- Protocol conformance
- JsonDocumentRepository full CRUD round-trip
- PostgresDocumentRepository fails clearly at construction
"""
from __future__ import annotations

import pytest

from backend.app import store as store_module
from backend.app.repository import (
    DocumentRepository,
    JsonDocumentRepository,
    PostgresDocumentRepository,
    get_repository,
)
from backend.app.models import (
    ActivityItem,
    CommentItem,
    DocumentSummary,
    RiskItem,
    SuggestionItem,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Redirect JSON store to a throwaway temp directory for every test."""
    monkeypatch.setattr(store_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(store_module, "INDEX_FILE", tmp_path / "documents.json")


@pytest.fixture(autouse=True)
def clear_storage_backend(monkeypatch):
    """Remove STORAGE_BACKEND so tests start from the default state."""
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)


def _sample_summary() -> DocumentSummary:
    return DocumentSummary(
        title="Test Contract",
        summary="A test contract.",
        highlights=["Clause A"],
        risks=[
            RiskItem(
                category="Payment",
                severity="low",
                title="Net-60 terms",
                explanation="Long payment window.",
                recommendation="Shorten to Net-30.",
                score=20,
            )
        ],
        suggestions=[
            SuggestionItem(
                title="Shorten payment window",
                rationale="Reduces cash-flow risk.",
                proposed_text="Payment due within 30 days.",
            )
        ],
        missing_clauses=[],
        language="English",
        overall_score=42,
    )


# ---------------------------------------------------------------------------
# TestGetRepository — factory and protocol
# ---------------------------------------------------------------------------

class TestGetRepository:
    def test_default_returns_json_repository(self):
        """When STORAGE_BACKEND is unset the factory returns JSON impl."""
        repo = get_repository()
        assert isinstance(repo, JsonDocumentRepository)

    def test_explicit_json_returns_json_repository(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "json")
        repo = get_repository()
        assert isinstance(repo, JsonDocumentRepository)

    def test_json_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "JSON")
        repo = get_repository()
        assert isinstance(repo, JsonDocumentRepository)

    def test_postgres_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "postgres")
        with pytest.raises(ValueError, match="not yet implemented"):
            get_repository()

    def test_postgres_error_mentions_json_fallback(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "postgres")
        with pytest.raises(ValueError, match="STORAGE_BACKEND=json"):
            get_repository()

    def test_unknown_backend_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "sqlite")
        with pytest.raises(ValueError, match="Unknown STORAGE_BACKEND"):
            get_repository()

    def test_json_repository_satisfies_protocol(self):
        """JsonDocumentRepository must be recognized as a DocumentRepository."""
        repo = get_repository()
        assert isinstance(repo, DocumentRepository)

    def test_postgres_raises_not_implemented_on_construction(self):
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            PostgresDocumentRepository()


# ---------------------------------------------------------------------------
# TestJsonRepositoryCrud — full domain round-trip via the repository
# ---------------------------------------------------------------------------

class TestJsonRepositoryCrud:
    def test_empty_on_start(self):
        repo = JsonDocumentRepository()
        assert repo.list_documents() == []

    def test_create_and_get(self):
        repo = JsonDocumentRepository()
        doc = repo.create_document("contract.txt", ["page one"], _sample_summary())
        assert doc.id is not None
        fetched = repo.get_document(doc.id)
        assert fetched is not None
        assert fetched.filename == "contract.txt"

    def test_list_documents(self):
        repo = JsonDocumentRepository()
        repo.create_document("a.txt", ["a"], _sample_summary())
        repo.create_document("b.txt", ["b"], _sample_summary())
        docs = repo.list_documents()
        assert len(docs) == 2

    def test_delete_document(self):
        repo = JsonDocumentRepository()
        doc = repo.create_document("to_delete.txt", ["content"], _sample_summary())
        assert repo.delete_document(doc.id) is True
        assert repo.get_document(doc.id) is None

    def test_delete_nonexistent_returns_false(self):
        repo = JsonDocumentRepository()
        assert repo.delete_document("nonexistent-id") is False

    def test_get_nonexistent_returns_none(self):
        repo = JsonDocumentRepository()
        assert repo.get_document("no-such-id") is None

    def test_share_document(self):
        repo = JsonDocumentRepository()
        doc = repo.create_document("shared.txt", ["content"], _sample_summary())
        updated = repo.share_document(doc.id, "alice@example.com")
        assert updated is not None
        assert "alice@example.com" in updated.shared_with

    def test_share_missing_doc_returns_none(self):
        repo = JsonDocumentRepository()
        assert repo.share_document("no-id", "x@x.com") is None

    def test_add_comment(self):
        repo = JsonDocumentRepository()
        doc = repo.create_document("commented.txt", ["content"], _sample_summary())
        comment = CommentItem(author="bob@example.com", body="Looks good.")
        updated = repo.add_comment(doc.id, comment)
        assert updated is not None
        assert any(c.body == "Looks good." for c in updated.comments)

    def test_add_comment_missing_doc_returns_none(self):
        repo = JsonDocumentRepository()
        comment = CommentItem(author="x@x.com", body="hi")
        assert repo.add_comment("no-id", comment) is None

    def test_update_review_status(self):
        repo = JsonDocumentRepository()
        doc = repo.create_document("status.txt", ["content"], _sample_summary())
        updated = repo.update_review_status(doc.id, "approved")
        assert updated is not None
        assert updated.review_status == "approved"

    def test_update_review_status_missing_doc_returns_none(self):
        repo = JsonDocumentRepository()
        assert repo.update_review_status("no-id", "approved") is None

    def test_update_metadata(self):
        repo = JsonDocumentRepository()
        doc = repo.create_document("meta.txt", ["content"], _sample_summary())
        updated = repo.update_metadata(
            doc.id,
            owner="alice@example.com",
            counterparty="Acme Corp",
            contract_type="MSA",
            effective_date="2025-01-01",
            expiry_date="2026-01-01",
            renewal_date="2025-12-01",
        )
        assert updated is not None
        assert updated.owner == "alice@example.com"
        assert updated.counterparty == "Acme Corp"
        assert updated.contract_type == "MSA"

    def test_update_metadata_missing_doc_returns_none(self):
        repo = JsonDocumentRepository()
        assert repo.update_metadata(
            "no-id",
            owner="x",
            counterparty="y",
            contract_type="z",
            effective_date="",
            expiry_date="",
            renewal_date="",
        ) is None

    def test_add_activity(self):
        repo = JsonDocumentRepository()
        doc = repo.create_document("activity.txt", ["content"], _sample_summary())
        item = ActivityItem(type="viewed", label="Document viewed", detail="opened")
        updated = repo.add_activity(doc.id, item)
        assert updated is not None
        assert any(a.type == "viewed" for a in updated.activity)

    def test_add_activity_missing_doc_returns_none(self):
        repo = JsonDocumentRepository()
        item = ActivityItem(type="viewed", label="Document viewed", detail="")
        assert repo.add_activity("no-id", item) is None

    def test_create_document_version(self):
        repo = JsonDocumentRepository()
        original = repo.create_document("v1.txt", ["v1 content"], _sample_summary())
        version = repo.create_document_version(
            original.id, "v2.txt", ["v2 content"], _sample_summary()
        )
        assert version is not None
        assert version.filename == "v2.txt"
        assert version.version_group_id == original.version_group_id

    def test_create_document_version_missing_source_returns_none(self):
        repo = JsonDocumentRepository()
        result = repo.create_document_version(
            "no-id", "v2.txt", ["content"], _sample_summary()
        )
        assert result is None

    def test_list_document_versions_newest_first(self):
        repo = JsonDocumentRepository()
        original = repo.create_document("v1.txt", ["v1"], _sample_summary())
        repo.create_document_version(original.id, "v2.txt", ["v2"], _sample_summary())
        versions = repo.list_document_versions(original.id)
        assert len(versions) == 2
        # newest first — v2 was created after v1
        assert versions[0].filename == "v2.txt"
        assert versions[1].filename == "v1.txt"
