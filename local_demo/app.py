from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.analyzer import (  # noqa: E402
    analyze_risks,
    answer_question,
    build_suggestions,
    compare_documents,
    detect_language,
    overall_score,
    summarize,
)
from app.models import ActivityItem, DocumentSummary  # noqa: E402
from app.store import add_activity, create_document, get_document, list_documents, share_document  # noqa: E402


app = Flask(__name__)


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
    return jsonify(
        total_documents=total,
        high_risk_documents=high_risk,
        average_score=average,
        shared_documents=shared,
    )


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
    risks = analyze_risks(all_text)
    summary_lines = summarize(all_text)
    summary = DocumentSummary(
        title=file.filename,
        summary=" ".join(summary_lines) if summary_lines else "Nie udało się wygenerować streszczenia.",
        highlights=summary_lines,
        risks=risks,
        suggestions=build_suggestions(risks),
        language=detect_language(all_text),
        overall_score=overall_score(risks),
    )
    return jsonify(create_document(file.filename, page_texts, summary).model_dump())


@app.post("/api/documents/<doc_id>/ask")
def ask(doc_id: str):
    document = get_document(doc_id)
    if not document:
        return jsonify(error="Document not found"), 404
    payload = request.get_json(force=True)
    answer, relevant = answer_question(payload["question"], [fragment.text for fragment in document.fragments])
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


@app.post("/api/compare")
def compare():
    payload = request.get_json(force=True)
    left = get_document(payload["left_id"])
    right = get_document(payload["right_id"])
    if not left or not right:
        return jsonify(error="Document not found"), 404
    differences = compare_documents(
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
