from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# Load backend/.env before any provider or settings are read.
# override=True so local .env values win over stale empty system env vars.
# Safe in Docker/CI because backend/.env is gitignored and never deployed —
# load_dotenv is a no-op when the file does not exist.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
from .analyzer import similarity_score
from .extraction import extract_pdf_pages
from .models import (
    ActivityItem,
    CommentItem,
    CommentRequest,
    CompareRequest,
    ComparisonResponse,
    DashboardStats,
    DeadlineItem,
    EmbeddingMeta,
    MetadataRequest,
    MetricsResponse,
    ProviderStatus,
    QuestionRequest,
    QuestionResponse,
    ReindexRequest,
    ReindexResponse,
    ReportResponse,
    RetrievalResult,
    ReviewStatusRequest,
    SearchResult,
    ShareRequest,
    VectorSearchResponse,
    VectorSearchResult,
)
from .embeddings import (
    EMBED_DIM,
    delete_document_embeddings,
    get_document_embeddings,
    reindex_document,
    vector_search,
)
from .deadlines import build_deadlines
from .store import (
    UPLOADS_DIR,
    add_activity,
    add_comment,
    create_document,
    delete_document,
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


app = FastAPI(title="LuminaClause API")
provider = get_provider()
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".txt"}
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/provider", response_model=ProviderStatus)
def provider_status() -> ProviderStatus:
    """Return the active AI provider name and model.

    Never exposes API keys or secret values — only the provider name,
    the model identifier, and whether a cloud provider is active.
    """
    name = provider.name
    model: str = getattr(provider, "model", "local")
    return ProviderStatus(
        provider=name,
        model=model if name != "local" else "local",
        cloud_enabled=name != "local",
    )


@app.get("/dashboard", response_model=DashboardStats)
def dashboard():
    return build_dashboard_stats(list_documents())


@app.get("/metrics", response_model=MetricsResponse)
def metrics():
    documents = list_documents()
    stats = build_dashboard_stats(documents)
    latest_upload = ""
    if documents:
        latest_upload = documents[-1].filename
    return MetricsResponse(
        service="luminaclause-api",
        total_documents=len(documents),
        total_fragments=sum(len(document.fragments) for document in documents),
        total_risks=sum(len(document.summary.risks) for document in documents),
        high_risk_documents=stats.high_risk_documents,
        average_score=stats.average_score,
        shared_documents=stats.shared_documents,
        comments_count=sum(len(document.comments) for document in documents),
        activity_events=sum(len(document.activity) for document in documents),
        latest_upload_filename=latest_upload,
    )

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


@app.delete("/documents/{doc_id}")
def remove_document(doc_id: str):
    deleted = delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    delete_document_embeddings(doc_id)
    return {"status": "deleted", "document_id": doc_id}


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), owner: str = Form("")):
    return await process_upload(file, owner=owner)


@app.post("/documents/bulk-upload")
async def bulk_upload_documents(files: list[UploadFile] = File(...), owner: str = Form("")):
    return [await process_upload(file, owner=owner) for file in files]


async def process_upload(file: UploadFile, owner: str = ""):
    original_filename = sanitize_upload_filename(file.filename or "document.txt")
    page_texts, extraction_method = await read_upload_pages(file, original_filename)
    all_text = "\n".join(page_texts)
    summary = provider.summarize_document(original_filename, all_text)
    return create_document(original_filename, page_texts, summary, extraction_method=extraction_method, owner=owner)


def sanitize_upload_filename(filename: str) -> str:
    name = Path(filename).name.strip().replace(" ", "-")
    safe = "".join(character for character in name if character.isalnum() or character in {"-", "_", "."})
    if not safe or safe in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if Path(safe).suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported")
    return safe[:120]


async def read_upload_pages(file: UploadFile, safe_filename: str) -> tuple[list[str], str]:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large for the local demo limit")

    temp_path = UPLOADS_DIR / f"{uuid4().hex}-{safe_filename}"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_bytes(raw)

    if Path(safe_filename).suffix.lower() == ".pdf":
        extraction = extract_pdf_pages(temp_path)
        page_texts = [page.strip() for page in extraction.page_texts if page.strip()]
        extraction_method = extraction.method
    else:
        raw_text = temp_path.read_text(encoding="utf-8").strip()
        # Split TXT files into paragraph-level fragments (blank-line delimited).
        # Each section with at least 40 characters becomes its own fragment,
        # giving the local similarity search and Claude meaningful units to rank.
        paragraphs = [p.strip() for p in raw_text.split("\n\n") if len(p.strip()) >= 40]
        page_texts = paragraphs if paragraphs else [raw_text]
        extraction_method = "text"
    if not any(page_texts):
        raise HTTPException(status_code=400, detail="No readable text found in uploaded document")
    return page_texts, extraction_method


@app.post("/documents/{doc_id}/versions")
async def upload_document_version(doc_id: str, file: UploadFile = File(...)):
    if not get_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    original_filename = sanitize_upload_filename(file.filename or "document.txt")
    page_texts, extraction_method = await read_upload_pages(file, original_filename)
    all_text = "\n".join(page_texts)
    summary = provider.summarize_document(original_filename, all_text)
    created = create_document_version(doc_id, original_filename, page_texts, summary, extraction_method=extraction_method)
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


@app.get("/documents/{doc_id}/retrieval", response_model=RetrievalResult)
def retrieve_document_context(doc_id: str, query: str, top_k: int = 3):
    item = get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    safe_top_k = max(1, min(top_k, 8))
    scored = [
        SearchResult(fragment=fragment, score=similarity_score(query, fragment.text))
        for fragment in item.fragments
    ]
    matches = sorted(
        [result for result in scored if result.score > 0],
        key=lambda result: result.score,
        reverse=True,
    )[:safe_top_k]
    context = "\n\n".join(
        f"Source page {match.fragment.page}: {match.fragment.text}"
        for match in matches
    )
    add_activity(
        doc_id,
        ActivityItem(
            type="retrieval",
            label="Semantic retrieval run",
            detail=f"Query: {query}",
        ),
    )
    return RetrievalResult(query=query, top_k=safe_top_k, matches=matches, context=context)


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


# ---------------------------------------------------------------------------
# Embeddings / vector retrieval
# ---------------------------------------------------------------------------

@app.post("/embeddings/reindex", response_model=ReindexResponse)
def reindex_embeddings(payload: ReindexRequest):
    """
    Compute and store vector embeddings for document fragments.

    Pass ``{"doc_id": "<id>"}`` to reindex a single document, or omit
    ``doc_id`` (or pass ``null``) to reindex every document in the store.

    Embeddings are stored in ``data/embeddings.json`` keyed by fragment ID.
    Existing records for the same fragment are overwritten (idempotent).

    Current provider: **local** — deterministic hash-projection (128 dims),
    no API key required.  Swap ``local_embed`` in ``embeddings.py`` for a
    real embeddings API to upgrade without changing these endpoints.
    """
    if payload.doc_id:
        doc = get_document(payload.doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        docs = [doc]
    else:
        docs = list_documents()

    total_fragments = 0
    for doc in docs:
        records = reindex_document(doc)
        total_fragments += len(records)

    return ReindexResponse(
        indexed_documents=len(docs),
        total_fragments=total_fragments,
        provider="local",
        dim=EMBED_DIM,
    )


@app.get("/documents/{doc_id}/embeddings", response_model=list[EmbeddingMeta], response_model_exclude_none=True)
def document_embeddings(doc_id: str, include_vectors: bool = False):
    """
    Return embedding metadata for every indexed fragment of the document.

    Vectors are omitted by default (128 floats × many fragments can be
    large).  Add ``?include_vectors=true`` to receive the raw float arrays,
    e.g. for client-side t-SNE / UMAP visualisation.

    Returns ``404`` when no embeddings exist — run
    ``POST /embeddings/reindex`` first.
    """
    item = get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    records = get_document_embeddings(doc_id, include_vectors=include_vectors)
    if not records:
        raise HTTPException(
            status_code=404,
            detail="No embeddings found for this document — run POST /embeddings/reindex first",
        )
    return records


@app.get("/documents/{doc_id}/vector-search", response_model=VectorSearchResponse)
def vector_search_document(doc_id: str, query: str, top_k: int = 3):
    """
    Retrieve the top-*k* fragments most similar to *query* by cosine
    similarity over stored embeddings.

    This is the RAG retrieval step: feed the returned ``context`` field
    (assembled from the top-k texts) as grounding to a language model.

    ``top_k`` is clamped to [1, 8].  Returns ``404`` when no embeddings
    exist — run ``POST /embeddings/reindex`` first.

    Compared with ``GET /documents/{id}/retrieval`` (keyword overlap),
    this endpoint uses dense vector similarity and will improve
    significantly once ``local_embed`` is replaced with a real sentence
    embedding model.
    """
    item = get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    if not query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")
    safe_k = max(1, min(top_k, 8))
    results = vector_search(query, doc_id, top_k=safe_k)
    if not results:
        raise HTTPException(
            status_code=404,
            detail="No embeddings found for this document — run POST /embeddings/reindex first",
        )
    return VectorSearchResponse(
        query=query,
        top_k=safe_k,
        provider="local",
        dim=EMBED_DIM,
        results=[
            VectorSearchResult(
                rank=i + 1,
                fragment_id=meta["fragment_id"],
                page=meta["page"],
                text=meta["text"],
                score=round(score, 4),
            )
            for i, (meta, score) in enumerate(results)
        ],
    )

