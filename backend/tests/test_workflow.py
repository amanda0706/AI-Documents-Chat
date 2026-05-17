from pathlib import Path

import pytest

from backend.app.models import CommentItem, DocumentSummary
from backend.app import store
from backend.app.store import (
    add_comment,
    create_document,
    get_document,
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
