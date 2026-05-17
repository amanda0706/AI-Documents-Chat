from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader

from .analyzer import (
    analyze_risks,
    answer_question,
    build_suggestions,
    compare_documents,
    detect_language,
    overall_score,
    similarity_score,
    summarize,
)
from .models import (
    ActivityItem,
    CommentItem,
    CommentRequest,
    CompareRequest,
    ComparisonResponse,
    DashboardStats,
    DocumentSummary,
    QuestionRequest,
    QuestionResponse,
    ReportResponse,
    ReviewStatusRequest,
    SearchResult,
    ShareRequest,
)
from .store import (
    UPLOADS_DIR,
    add_activity,
    add_comment,
    create_document,
    get_document,
    list_documents,
    share_document,
    update_review_status,
)


app = FastAPI(title="ClausePilot API")
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
    documents = list_documents()
    total = len(documents)
    high_risk = sum(
        1 for document in documents if any(risk.severity == "high" for risk in document.summary.risks)
    )
    average = round(sum(document.summary.overall_score for document in documents) / total) if total else 0
    shared = sum(1 for document in documents if document.shared_with)
    pending_review = sum(1 for document in documents if document.review_status == "in_review")
    approved = sum(1 for document in documents if document.review_status == "approved")
    return DashboardStats(
        total_documents=total,
        high_risk_documents=high_risk,
        average_score=average,
        shared_documents=shared,
        pending_review_documents=pending_review,
        approved_documents=approved,
    )


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
    summary_lines = summarize(all_text)
    risks = analyze_risks(all_text)
    summary = DocumentSummary(
        title=file.filename,
        summary=" ".join(summary_lines) if summary_lines else "Nie udało się wygenerować streszczenia.",
        highlights=summary_lines,
        risks=risks,
        suggestions=build_suggestions(risks),
        language=detect_language(all_text),
        overall_score=overall_score(risks),
    )
    return create_document(file.filename, page_texts, summary)


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
    answer, relevant = answer_question(payload.question, [fragment.text for fragment in item.fragments])
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
    if payload.status not in {"draft", "in_review", "approved"}:
        raise HTTPException(status_code=400, detail="Invalid review status")
    updated = update_review_status(doc_id, payload.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found")
    return updated


@app.get("/documents/{doc_id}/report", response_model=ReportResponse)
def document_report(doc_id: str):
    item = get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    risk_lines = "\n".join(
        f"- **{risk.title}** ({risk.severity}) — {risk.explanation}"
        for risk in item.summary.risks
    ) or "- No material risks detected."
    suggestion_lines = "\n".join(
        f"- **{suggestion.title}** — {suggestion.rationale}\n  - Suggested text: `{suggestion.proposed_text}`"
        for suggestion in item.summary.suggestions
    ) or "- No suggested edits."
    passage_lines = "\n".join(
        f"- Page {fragment.page}: {fragment.text}"
        for fragment in item.fragments[:3]
    ) or "- No passages available."
    markdown = f"""# Contract Review Report

## Document
{item.filename}

## Executive summary
{item.summary.summary}

## Risk score
{item.summary.overall_score}/100

## Key risks
{risk_lines}

## Suggested edits
{suggestion_lines}

## Supporting passages
{passage_lines}
"""
    return ReportResponse(filename=item.filename, markdown=markdown)


@app.post("/compare", response_model=ComparisonResponse)
def compare(payload: CompareRequest):
    left = get_document(payload.left_id)
    right = get_document(payload.right_id)
    if not left or not right:
        raise HTTPException(status_code=404, detail="Document not found")

    left_text = "\n".join(fragment.text for fragment in left.fragments)
    right_text = "\n".join(fragment.text for fragment in right.fragments)
    differences = compare_documents(left_text, right_text)
    summary = (
        f"Znaleziono {len(differences)} istotne różnice między dokumentami."
        if differences
        else "Nie wykryto istotnych różnic na podstawie lokalnych reguł."
    )
    add_activity(
        left.id,
        ActivityItem(
            type="compare",
            label="Compared with another contract",
            detail=f"Compared with {right.filename}.",
        ),
    )
    return ComparisonResponse(
        left_filename=left.filename,
        right_filename=right.filename,
        summary=summary,
        differences=differences,
    )
