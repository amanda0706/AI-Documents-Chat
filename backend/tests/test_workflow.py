from pathlib import Path

import pytest

from backend.app.models import CommentItem, DocumentSummary
from backend.app import store
from backend.app.store import (
    add_comment,
    create_document,
    create_document_version,
    get_document,
    list_document_versions,
    update_metadata,
    update_review_status,
)


@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(store, "INDEX_FILE", tmp_path / "documents.json")


def build_summary() -> DocumentSummary:
    return DocumentSummary(
        title="agreement.txt",
        summary="Short summary.",
        highlights=[],
        risks=[],
        suggestions=[],
        missing_clauses=[],
        language="en",
        overall_score=100,
    )


def test_new_documents_start_in_draft() -> None:
    document = create_document("agreement.txt", ["Payment terms are net 30 days."], build_summary())
    assert document.review_status == "draft"


def test_comment_is_saved_and_recorded_in_activity() -> None:
    document = create_document("agreement.txt", ["Payment terms are net 30 days."], build_summary())
    updated = add_comment(document.id, CommentItem(author="anna@example.com", body="Check liability cap."))

    assert updated is not None
    assert updated.comments[0].author == "anna@example.com"
    assert updated.comments[0].body == "Check liability cap."
    assert updated.activity[0].type == "comment"


def test_review_status_is_updated_and_recorded() -> None:
    document = create_document("agreement.txt", ["Payment terms are net 30 days."], build_summary())
    updated = update_review_status(document.id, "approved")

    assert updated is not None
    assert updated.review_status == "approved"
    assert updated.activity[0].type == "status"


def test_saved_document_can_be_reloaded_with_workflow_state() -> None:
    document = create_document("agreement.txt", ["Payment terms are net 30 days."], build_summary())
    add_comment(document.id, CommentItem(author="anna@example.com", body="Looks good."))
    update_review_status(document.id, "in_review")

    reloaded = get_document(document.id)

    assert reloaded is not None
    assert reloaded.review_status == "in_review"
    assert reloaded.comments[0].body == "Looks good."


def test_metadata_can_be_updated() -> None:
    document = create_document("agreement.txt", ["Payment terms are net 30 days."], build_summary())
    updated = update_metadata(
        document.id,
        owner="anna@example.com",
        counterparty="Northwind Labs",
        contract_type="MSA",
        effective_date="2026-01-01",
        expiry_date="2026-12-31",
        renewal_date="2026-11-30",
    )

    assert updated is not None
    assert updated.owner == "anna@example.com"
    assert updated.counterparty == "Northwind Labs"
    assert updated.contract_type == "MSA"
    assert updated.renewal_date == "2026-11-30"
    assert updated.activity[0].type == "metadata"


def test_new_document_versions_share_group_and_track_latest() -> None:
    first = create_document("agreement-v1.txt", ["Payment terms are net 60 days."], build_summary())
    second = create_document_version(first.id, "agreement-v2.txt", ["Payment terms are net 30 days."], build_summary())

    assert second is not None
    assert second.version_group_id == first.id
    assert second.version_number == 2
    assert second.is_latest_version is True

    versions = list_document_versions(first.id)
    assert [item.version_number for item in versions] == [2, 1]
    assert versions[1].is_latest_version is False
