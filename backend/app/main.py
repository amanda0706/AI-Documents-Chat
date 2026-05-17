from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader

from .analyzer import similarity_score
from .models import (
    ActivityItem,
    CommentItem,
    CommentRequest,
    CompareRequest,
    ComparisonResponse,
    DashboardStats,
    DeadlineItem,
    MetadataRequest,
    QuestionRequest,
    QuestionResponse,
    ReportResponse,
    ReviewStatusRequest,
    SearchResult,
    ShareRequest,
)
from .deadlines import build_deadlines
from .store import (
    UPLOADS_DIR,
    add_activity,
    add_comment,
    create_document,
    create_document_version,
    get_document,
    list_document_versions,
    list_documents,
    share_document,
    update_review_status,
    update_metadata,
)
from .providers import get_provider
from .services import build_dashboard_stats, build_report, compare_contracts


app = FastAPI(title="ClausePilot API")
provider = get_provider()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/dashboard", response_model=DashboardStats)
def dashboard():
    return build_dashboard_stats(list_documents())

@app.get("/deadlines", response_model=list[DeadlineItem])
def deadlines():
    return build_deadlines(list_documents())


@app.get("/documents")
def documents():
    return list_documents()


@app.get("/documents/{doc_id}")
def document(doc_id: str):
    item = get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    return item


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    return await process_upload(file)


@app.post("/documents/bulk-upload")
async def bulk_upload_documents(files: list[UploadFile] = File(...)):
    return [await process_upload(file) for file in files]


async def process_upload(file: UploadFile):
    if not file.filename.lower().endswith((".pdf", ".txt")):
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported")

    raw = await file.read()
    temp_path = UPLOADS_DIR / file.filename
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_bytes(raw)

    if file.filename.lower().endswith(".pdf"):
        reader = PdfReader(temp_path)
        page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    else:
        page_texts = [temp_path.read_text(encoding="utf-8").strip()]
    all_text = "\n".join(page_texts)
    summary = provider.summarize_document(file.filename, all_text)
    return create_document(file.filename, page_texts, summary)


@app.post("/documents/{doc_id}/versions")
async def upload_document_version(doc_id: str, file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".pdf", ".txt")):
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported")

    raw = await file.read()
    temp_path = UPLOADS_DIR / file.filename
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_bytes(raw)

    if file.filename.lower().endswith(".pdf"):
        reader = PdfReader(temp_path)
        page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    else:
        page_texts = [temp_path.read_text(encoding="utf-8").strip()]
    all_text = "\n".join(page_texts)
    summary = provider.summarize_document(file.filename, all_text)
    created = create_document_version(doc_id, file.filename, page_texts, summary)
    if not created:
        raise HTTPException(status_code=404, detail="Document not found")
    return created


@app.get("/documents/{doc_id}/versions")
def document_versions(doc_id: str):
    versions = list_document_versions(doc_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Document not found")
    return versions


@app.get("/documents/{doc_id}/search")
def search_document(doc_id: str, query: str):
    item = get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    results = [
        SearchResult(fragment=fragment, score=similarity_score(query, fragment.text))
        for fragment in item.fragments
    ]
    return sorted([result for result in results if result.score > 0], key=lambda result: result.score, reverse=True)


@app.post("/documents/{doc_id}/ask", response_model=QuestionResponse)
def ask_document(doc_id: str, payload: QuestionRequest):
    item = get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    answer, relevant = provider.answer(payload.question, [fragment.text for fragment in item.fragments])
    citations = [fragment for fragment in item.fragments if fragment.text in relevant]
    add_activity(
        doc_id,
        ActivityItem(
            type="question",
            label="Question asked",
            detail=payload.question,
        ),
    )
    return QuestionResponse(answer=answer, citations=citations)


@app.post("/documents/{doc_id}/share")
def share(doc_id: str, payload: ShareRequest):
    updated = share_document(doc_id, payload.email)
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found")
    return updated


@app.post("/documents/{doc_id}/comments")
def comment(doc_id: str, payload: CommentRequest):
    updated = add_comment(doc_id, CommentItem(author=payload.author, body=payload.body))
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found")
    return updated


@app.post("/documents/{doc_id}/status")
def update_status(doc_id: str, payload: ReviewStatusRequest):
    updated = update_review_status(doc_id, payload.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found")
    return updated


@app.post("/documents/{doc_id}/metadata")
def update_document_metadata(doc_id: str, payload: MetadataRequest):
    updated = update_metadata(
        doc_id,
        owner=payload.owner,
        counterparty=payload.counterparty,
        contract_type=payload.contract_type,
        effective_date=payload.effective_date,
        expiry_date=payload.expiry_date,
        renewal_date=payload.renewal_date,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found")
    return updated


@app.get("/documents/{doc_id}/report", response_model=ReportResponse)
def document_report(doc_id: str):
    item = get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    return build_report(item)

@app.post("/compare", response_model=ComparisonResponse)
def compare(payload: CompareRequest):
    left = get_document(payload.left_id)
    right = get_document(payload.right_id)
    if not left or not right:
        raise HTTPException(status_code=404, detail="Document not found")

    comparison = compare_contracts(left, right, provider)
    add_activity(
        left.id,
        ActivityItem(
            type="compare",
            label="Compared with another contract",
            detail=f"Compared with {right.filename}.",
        ),
    )
    return comparison
