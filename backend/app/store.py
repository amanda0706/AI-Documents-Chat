from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .models import DocumentDetail, DocumentFragment, DocumentSummary


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
    INDEX_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def create_document(filename: str, page_texts: list[str], summary: DocumentSummary) -> DocumentDetail:
    documents = load_all()
    doc_id = str(uuid4())
    fragments = [
        DocumentFragment(id=f"{doc_id}-{index}", page=index + 1, text=text)
        for index, text in enumerate(page_texts)
        if text.strip()
    ]
    detail = DocumentDetail(
        id=doc_id,
        filename=filename,
        page_count=len(page_texts),
        shared_with=[],
        summary=summary,
        fragments=fragments,
    )
    documents[doc_id] = detail.model_dump()
    save_all(documents)
    return detail


def list_documents() -> list[DocumentDetail]:
    return [DocumentDetail(**payload) for payload in load_all().values()]


def get_document(doc_id: str) -> DocumentDetail | None:
    payload = load_all().get(doc_id)
    return DocumentDetail(**payload) if payload else None


def share_document(doc_id: str, email: str) -> DocumentDetail | None:
    documents = load_all()
    payload = documents.get(doc_id)
    if not payload:
        return None
    shared = set(payload.get("shared_with", []))
    shared.add(email)
    payload["shared_with"] = sorted(shared)
    documents[doc_id] = payload
    save_all(documents)
    return DocumentDetail(**payload)
