from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .models import ActivityItem, CommentItem, DocumentDetail, DocumentFragment, DocumentSummary


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
INDEX_FILE = DATA_DIR / "documents.json"


def ensure_store() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text("{}", encoding="utf-8")


def load_all() -> dict[str, dict]:
    ensure_store()
    return json.loads(INDEX_FILE.read_text(encoding="utf-8"))


def save_all(payload: dict[str, dict]) -> None:
    ensure_store()
    temp_file = INDEX_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(INDEX_FILE)


def create_document(
    filename: str,
    page_texts: list[str],
    summary: DocumentSummary,
    *,
    version_group_id: str | None = None,
    extraction_method: str = "text",
    owner: str = "",
) -> DocumentDetail:
    documents = load_all()
    doc_id = str(uuid4())
    group_id = version_group_id or doc_id
    previous_versions = [
        payload
        for payload in documents.values()
        if payload.get("version_group_id", payload["id"]) == group_id
    ]
    version_number = len(previous_versions) + 1
    for payload in previous_versions:
        payload["is_latest_version"] = False
    fragments = [
        DocumentFragment(id=f"{doc_id}-{index}", page=index + 1, text=text)
        for index, text in enumerate(page_texts)
        if text.strip()
    ]
    detail = DocumentDetail(
        id=doc_id,
        filename=filename,
        version_group_id=group_id,
        version_number=version_number,
        is_latest_version=True,
        extraction_method=extraction_method,
        ocr_applied=extraction_method == "ocr",
        page_count=len(page_texts),
        shared_with=[],
        owner=owner,
        counterparty="",
        contract_type="",
        effective_date="",
        expiry_date="",
        renewal_date="",
        review_status="draft",
        activity=[
            ActivityItem(
                type="upload",
                label="Document uploaded",
                detail="File added and analyzed locally.",
            )
        ],
        comments=[],
        summary=summary,
        fragments=fragments,
    )
    documents[doc_id] = detail.model_dump()
    save_all(documents)
    return detail


def create_document_version(
    source_doc_id: str,
    filename: str,
    page_texts: list[str],
    summary: DocumentSummary,
    extraction_method: str = "text",
) -> DocumentDetail | None:
    source = get_document(source_doc_id)
    if not source:
        return None
    return create_document(
        filename,
        page_texts,
        summary,
        version_group_id=source.version_group_id or source.id,
        extraction_method=extraction_method,
        owner=source.owner,
    )


def list_document_versions(doc_id: str) -> list[DocumentDetail]:
    source = get_document(doc_id)
    if not source:
        return []
    group_id = source.version_group_id or source.id
    versions = [
        DocumentDetail(**payload)
        for payload in load_all().values()
        if payload.get("version_group_id", payload["id"]) == group_id
    ]
    return sorted(versions, key=lambda item: item.version_number, reverse=True)


def list_documents() -> list[DocumentDetail]:
    return [DocumentDetail(**payload) for payload in load_all().values()]


def get_document(doc_id: str) -> DocumentDetail | None:
    payload = load_all().get(doc_id)
    return DocumentDetail(**payload) if payload else None


def delete_document(doc_id: str) -> bool:
    documents = load_all()
    if doc_id not in documents:
        return False
    documents.pop(doc_id)
    save_all(documents)
    return True


def add_activity(doc_id: str, item: ActivityItem) -> DocumentDetail | None:
    documents = load_all()
    payload = documents.get(doc_id)
    if not payload:
        return None
    payload.setdefault("activity", [])
    payload["activity"].insert(0, item.model_dump())
    documents[doc_id] = payload
    save_all(documents)
    return DocumentDetail(**payload)


def share_document(doc_id: str, email: str) -> DocumentDetail | None:
    documents = load_all()
    payload = documents.get(doc_id)
    if not payload:
        return None
    shared = set(payload.get("shared_with", []))
    shared.add(email)
    payload["shared_with"] = sorted(shared)
    payload.setdefault("activity", [])
    payload["activity"].insert(
        0,
        ActivityItem(
            type="share",
            label="Document shared",
            detail=f"Shared with {email}.",
        ).model_dump(),
    )
    documents[doc_id] = payload
    save_all(documents)
    return DocumentDetail(**payload)


def add_comment(doc_id: str, comment: CommentItem) -> DocumentDetail | None:
    documents = load_all()
    payload = documents.get(doc_id)
    if not payload:
        return None
    payload.setdefault("comments", [])
    payload["comments"].insert(0, comment.model_dump())
    payload.setdefault("activity", [])
    payload["activity"].insert(
        0,
        ActivityItem(
            type="comment",
            label="Comment added",
            detail=comment.body,
        ).model_dump(),
    )
    documents[doc_id] = payload
    save_all(documents)
    return DocumentDetail(**payload)


def update_review_status(doc_id: str, status: str) -> DocumentDetail | None:
    documents = load_all()
    payload = documents.get(doc_id)
    if not payload:
        return None
    payload["review_status"] = str(status)
    payload.setdefault("activity", [])
    payload["activity"].insert(
        0,
        ActivityItem(
            type="status",
            label="Review status updated",
            detail=f"Status changed to {status}.",
        ).model_dump(),
    )
    documents[doc_id] = payload
    save_all(documents)
    return DocumentDetail(**payload)


def update_metadata(
    doc_id: str,
    *,
    owner: str,
    counterparty: str,
    contract_type: str,
    effective_date: str,
    expiry_date: str,
    renewal_date: str,
) -> DocumentDetail | None:
    documents = load_all()
    payload = documents.get(doc_id)
    if not payload:
        return None
    payload.update(
        {
            "owner": owner,
            "counterparty": counterparty,
            "contract_type": contract_type,
            "effective_date": effective_date,
            "expiry_date": expiry_date,
            "renewal_date": renewal_date,
        }
    )
    payload.setdefault("activity", [])
    payload["activity"].insert(
        0,
        ActivityItem(
            type="metadata",
            label="Metadata updated",
            detail="Contract profile updated.",
        ).model_dump(),
    )
    documents[doc_id] = payload
    save_all(documents)
    return DocumentDetail(**payload)
