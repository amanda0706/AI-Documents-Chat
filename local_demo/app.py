from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.models import ActivityItem, CommentItem  # noqa: E402
from app.deadlines import build_deadlines  # noqa: E402
from app.providers import get_provider  # noqa: E402
from app.services import build_report  # noqa: E402
from app.store import add_activity, add_comment, create_document, get_document, list_documents, share_document, update_metadata as store_update_metadata, update_review_status  # noqa: E402


app = Flask(__name__)
provider = get_provider()


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/dashboard")
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
    deadlines = build_deadlines(documents)
    return jsonify(
        total_documents=total,
        high_risk_documents=high_risk,
        average_score=average,
        shared_documents=shared,
        pending_review_documents=pending_review,
        approved_documents=approved,
        expiring_soon_documents=sum(1 for item in deadlines if item.kind == "expiry"),
        renewal_due_documents=sum(1 for item in deadlines if item.kind == "renewal"),
    )


@app.get("/api/deadlines")
def deadlines():
    return jsonify([item.model_dump() for item in build_deadlines(list_documents())])


@app.get("/api/documents")
def documents():
    return jsonify([document.model_dump() for document in list_documents()])


@app.post("/api/documents/upload")
def upload():
    file = request.files["file"]
    if not file.filename.lower().endswith((".pdf", ".txt")):
        return jsonify(error="Only PDF and TXT files are supported"), 400

    temp_path = ROOT / "backend" / "data" / "uploads" / file.filename
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    file.save(temp_path)
    if file.filename.lower().endswith(".pdf"):
        reader = PdfReader(temp_path)
        page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    else:
        page_texts = [temp_path.read_text(encoding="utf-8").strip()]
    all_text = "\n".join(page_texts)
    summary = provider.summarize_document(file.filename, all_text)
    return jsonify(create_document(file.filename, page_texts, summary).model_dump())


@app.post("/api/documents/<doc_id>/ask")
def ask(doc_id: str):
    document = get_document(doc_id)
    if not document:
        return jsonify(error="Document not found"), 404
    payload = request.get_json(force=True)
    answer, relevant = provider.answer(payload["question"], [fragment.text for fragment in document.fragments])
    citations = [fragment.model_dump() for fragment in document.fragments if fragment.text in relevant]
    add_activity(
        doc_id,
        ActivityItem(type="question", label="Question asked", detail=payload["question"]),
    )
    return jsonify(answer=answer, citations=citations)


@app.post("/api/documents/<doc_id>/share")
def share(doc_id: str):
    payload = request.get_json(force=True)
    updated = share_document(doc_id, payload["email"])
    if not updated:
        return jsonify(error="Document not found"), 404
    return jsonify(updated.model_dump())


@app.post("/api/documents/<doc_id>/comments")
def comment(doc_id: str):
    payload = request.get_json(force=True)
    updated = add_comment(doc_id, CommentItem(author=payload["author"], body=payload["body"]))
    if not updated:
        return jsonify(error="Document not found"), 404
    return jsonify(updated.model_dump())


@app.post("/api/documents/<doc_id>/status")
def update_status(doc_id: str):
    payload = request.get_json(force=True)
    if payload["status"] not in {"draft", "in_review", "approved"}:
        return jsonify(error="Invalid review status"), 400
    updated = update_review_status(doc_id, payload["status"])
    if not updated:
        return jsonify(error="Document not found"), 404
    return jsonify(updated.model_dump())


@app.post("/api/documents/<doc_id>/metadata")
def update_metadata(doc_id: str):
    payload = request.get_json(force=True)
    updated = store_update_metadata(
        doc_id,
        owner=payload.get("owner", ""),
        counterparty=payload.get("counterparty", ""),
        contract_type=payload.get("contract_type", ""),
        effective_date=payload.get("effective_date", ""),
        expiry_date=payload.get("expiry_date", ""),
        renewal_date=payload.get("renewal_date", ""),
    )
    if not updated:
        return jsonify(error="Document not found"), 404
    return jsonify(updated.model_dump())


@app.get("/api/documents/<doc_id>/report")
def report(doc_id: str):
    document = get_document(doc_id)
    if not document:
        return jsonify(error="Document not found"), 404
    return jsonify(build_report(document).model_dump())

@app.post("/api/compare")
def compare():
    payload = request.get_json(force=True)
    left = get_document(payload["left_id"])
    right = get_document(payload["right_id"])
    if not left or not right:
        return jsonify(error="Document not found"), 404
    differences = provider.compare(
        "\n".join(fragment.text for fragment in left.fragments),
        "\n".join(fragment.text for fragment in right.fragments),
    )
    add_activity(
        left.id,
        ActivityItem(
            type="compare",
            label="Compared with another contract",
            detail=f"Compared with {right.filename}.",
        ),
    )
    return jsonify(
        left_filename=left.filename,
        right_filename=right.filename,
        summary=f"Znaleziono {len(differences)} istotne różnice między dokumentami.",
        differences=[difference.model_dump() for difference in differences],
    )
if __name__ == "__main__":
    app.run(debug=True, port=5050)
