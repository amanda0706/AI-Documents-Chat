from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# Load backend/.env before any provider or settings are read.
# override=True so local .env values win over stale empty system env vars.
# Safe in Docker/CI because backend/.env is gitignored and never deployed —
# load_dotenv is a no-op when the file does not exist.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
from .analyzer import similarity_score
from .chunker import chunk_pages as _chunk_pages
from .extraction import extract_pdf_pages
from .models import (
    ActivityItem,
    AuthResponse,
    CommentItem,
    CommentRequest,
    CompareRequest,
    ComparisonResponse,
    DashboardStats,
    DeadlineItem,
    EmbeddingMeta,
    LoginRequest,
    MetadataRequest,
    MetricsResponse,
    ProcessingInfo,
    ProviderStatus,
    StorageStatus,
    QuestionRequest,
    QuestionResponse,
    ReindexRequest,
    ReindexResponse,
    RegisterRequest,
    ReportResponse,
    RetrievalResult,
    ReviewStatusRequest,
    SearchResult,
    ShareRequest,
    UserPublic,
    VectorSearchResponse,
    VectorSearchResult,
)
from .auth import create_token, decode_token
from .auth_store import authenticate_user, get_user_by_id, register_user
from .embeddings import (
    EMBED_DIM,
    delete_document_embeddings,
    get_document_embeddings,
    reindex_document,
    vector_search,
)
from .deadlines import build_deadlines
# UPLOADS_DIR is needed for temp file handling during upload; all other
# document persistence goes through repo (see get_repository() below).
from .store import UPLOADS_DIR
from .repository import get_repository
from .providers import get_provider
from .services import build_dashboard_stats, build_report, compare_contracts


app = FastAPI(title="LuminaClause API")
provider = get_provider()
# Active document repository — driven by STORAGE_BACKEND env var.
# Default: JsonDocumentRepository (data/documents.json).
# Override: STORAGE_BACKEND=postgres (raises ValueError until implemented).
repo = get_repository()
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


@app.get("/runtime", response_model=StorageStatus)
def runtime_status() -> StorageStatus:
    """Return the active storage backend and its readiness.

    Never exposes DATABASE_URL, credentials, or secrets — only whether
    the storage layer is reachable.
    """
    import os as _os
    backend = _os.getenv("STORAGE_BACKEND", "json").strip().lower()
    if backend != "postgres":
        return StorageStatus(storage_backend="json", storage_ready=True, database_connected=None)
    # Lightweight connectivity check — a single SELECT 1 on a fresh connection.
    try:
        import psycopg2  # noqa: PLC0415
        url = _os.getenv("DATABASE_URL", "").strip()
        if not url:
            return StorageStatus(storage_backend="postgres", storage_ready=False, database_connected=False)
        conn = psycopg2.connect(url)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        finally:
            conn.close()
        return StorageStatus(storage_backend="postgres", storage_ready=True, database_connected=True)
    except Exception:
        return StorageStatus(storage_backend="postgres", storage_ready=False, database_connected=False)


@app.get("/dashboard", response_model=DashboardStats)
def dashboard():
    return build_dashboard_stats(repo.list_documents())


@app.get("/metrics", response_model=MetricsResponse)
def metrics():
    documents = repo.list_documents()
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
    return build_deadlines(repo.list_documents())


@app.get("/documents")
def documents():
    return repo.list_documents()


@app.get("/documents/{doc_id}")
def document(doc_id: str):
    item = repo.get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    return item


@app.get("/documents/{doc_id}/processing", response_model=ProcessingInfo)
def document_processing_info(doc_id: str) -> ProcessingInfo:
    """Return safe ingestion metadata computed from stored fragments.

    Never exposes file paths, env values, credentials, or runtime internals —
    only statistics derived from the document's fragment list.
    """
    item = repo.get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    lengths = [len(f.text) for f in item.fragments]
    fragment_count = len(lengths)
    avg_len = round(sum(lengths) / fragment_count) if lengths else 0
    max_len = max(lengths) if lengths else 0
    if fragment_count <= 1:
        strategy = "single fragment"
    elif fragment_count > item.page_count:
        strategy = "paragraph-aware"
    else:
        strategy = "per-page"
    return ProcessingInfo(
        extraction_method=item.extraction_method,
        ocr_applied=item.ocr_applied,
        page_count=item.page_count,
        fragment_count=fragment_count,
        avg_fragment_length=avg_len,
        max_fragment_length=max_len,
        cleaning_applied=True,
        chunking_strategy=strategy,
    )


@app.delete("/documents/{doc_id}")
def remove_document(doc_id: str):
    deleted = repo.delete_document(doc_id)
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
    page_texts, chunk_page_nums, extraction_method = await read_upload_pages(file, original_filename)
    all_text = "\n".join(page_texts)
    summary = provider.summarize_document(original_filename, all_text)
    return repo.create_document(
        original_filename, page_texts, summary,
        chunk_pages=chunk_page_nums,
        extraction_method=extraction_method, owner=owner,
    )


def sanitize_upload_filename(filename: str) -> str:
    name = Path(filename).name.strip().replace(" ", "-")
    safe = "".join(character for character in name if character.isalnum() or character in {"-", "_", "."})
    if not safe or safe in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if Path(safe).suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported")
    return safe[:120]


async def read_upload_pages(
    file: UploadFile, safe_filename: str
) -> tuple[list[str], list[int], str]:
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
        raw_pages = [page.strip() for page in extraction.page_texts if page.strip()]
        extraction_method = extraction.method
    else:
        # Read with errors="replace" so mojibake bytes never crash ingestion.
        raw_text = temp_path.read_text(encoding="utf-8", errors="replace").strip()
        raw_pages = [raw_text] if raw_text else []
        extraction_method = "text"

    if not any(raw_pages):
        raise HTTPException(status_code=400, detail="No readable text found in uploaded document")

    # Clean, de-duplicate headers/footers, and split into bounded chunks.
    chunk_texts, chunk_page_nums = _chunk_pages(raw_pages)

    if not chunk_texts:
        raise HTTPException(status_code=400, detail="No readable text found in uploaded document")

    return chunk_texts, chunk_page_nums, extraction_method


@app.post("/documents/{doc_id}/versions")
async def upload_document_version(doc_id: str, file: UploadFile = File(...)):
    if not repo.get_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    original_filename = sanitize_upload_filename(file.filename or "document.txt")
    page_texts, chunk_page_nums, extraction_method = await read_upload_pages(file, original_filename)
    all_text = "\n".join(page_texts)
    summary = provider.summarize_document(original_filename, all_text)
    created = repo.create_document_version(
        doc_id, original_filename, page_texts, summary,
        extraction_method=extraction_method,
        chunk_pages=chunk_page_nums,
    )
    if not created:
        raise HTTPException(status_code=404, detail="Document not found")
    return created


@app.get("/documents/{doc_id}/versions")
def document_versions(doc_id: str):
    versions = repo.list_document_versions(doc_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Document not found")
    return versions


@app.get("/documents/{doc_id}/search")
def search_document(doc_id: str, query: str):
    item = repo.get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    results = [
        SearchResult(fragment=fragment, score=similarity_score(query, fragment.text))
        for fragment in item.fragments
    ]
    return sorted([result for result in results if result.score > 0], key=lambda result: result.score, reverse=True)


@app.get("/documents/{doc_id}/retrieval", response_model=RetrievalResult)
def retrieve_document_context(doc_id: str, query: str, top_k: int = 3):
    item = repo.get_document(doc_id)
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
    repo.add_activity(
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
    item = repo.get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    answer, relevant = provider.answer(payload.question, [fragment.text for fragment in item.fragments])
    citations = [fragment for fragment in item.fragments if fragment.text in relevant]
    repo.add_activity(
        doc_id,
        ActivityItem(
            type="question",
            label="Question asked",
            detail=payload.question,
        ),
    )
    return QuestionResponse(answer=answer, citations=citations)


@app.post("/documents/{doc_id}/ask/stream")
async def stream_ask_document(doc_id: str, payload: QuestionRequest):
    """
    Stream a document-grounded answer as Server-Sent Events (SSE).

    Event sequence
    --------------
    ::

        data: {"type": "delta",     "text": "Payment "}
        data: {"type": "delta",     "text": "terms "}
        ...
        data: {"type": "citations", "citations": [{...}, ...]}
        data: {"type": "done"}

    The complete answer is computed first (via ``provider.answer``), then
    delivered word-by-word so the browser can render incrementally.  Replace
    the ``provider.answer`` call with a native SDK streaming call
    (e.g. ``anthropic.messages.stream()``) to achieve true token-level
    streaming without changing the SSE contract.

    Falls back gracefully: the non-streaming ``POST /documents/{id}/ask``
    endpoint remains fully functional alongside this one.
    """
    item = repo.get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")

    # Resolve the complete answer first so citations are known before streaming
    # begins.  The streaming is purely in the delivery to the client.
    answer_text, used_fragments = provider.answer(
        payload.question, [frag.text for frag in item.fragments]
    )
    citations = [frag for frag in item.fragments if frag.text in used_fragments]

    repo.add_activity(
        doc_id,
        ActivityItem(
            type="question",
            label="Question asked",
            detail=payload.question,
        ),
    )

    async def event_stream():
        # Stream the answer word by word so the client sees incremental output.
        words = answer_text.split()
        for i, word in enumerate(words):
            chunk = word if i == 0 else f" {word}"
            yield f"data: {json.dumps({'type': 'delta', 'text': chunk})}\n\n"

        # Send all citations in a single event after the answer is complete.
        yield f"data: {json.dumps({'type': 'citations', 'citations': [c.model_dump() for c in citations]})}\n\n"

        # Terminal event — client closes the reader on receipt.
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx/proxy buffering
        },
    )


@app.post("/documents/{doc_id}/share")
def share(doc_id: str, payload: ShareRequest):
    updated = repo.share_document(doc_id, payload.email)
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found")
    return updated


@app.post("/documents/{doc_id}/comments")
def comment(doc_id: str, payload: CommentRequest):
    updated = repo.add_comment(doc_id, CommentItem(author=payload.author, body=payload.body))
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found")
    return updated


@app.post("/documents/{doc_id}/status")
def update_status(doc_id: str, payload: ReviewStatusRequest):
    updated = repo.update_review_status(doc_id, payload.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found")
    return updated


@app.post("/documents/{doc_id}/metadata")
def update_document_metadata(doc_id: str, payload: MetadataRequest):
    updated = repo.update_metadata(
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
    item = repo.get_document(doc_id)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    return build_report(item)


@app.post("/compare", response_model=ComparisonResponse)
def compare(payload: CompareRequest):
    left = repo.get_document(payload.left_id)
    right = repo.get_document(payload.right_id)
    if not left or not right:
        raise HTTPException(status_code=404, detail="Document not found")

    comparison = compare_contracts(left, right, provider)
    repo.add_activity(
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
        doc = repo.get_document(payload.doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        docs = [doc]
    else:
        docs = repo.list_documents()

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
    item = repo.get_document(doc_id)
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
    item = repo.get_document(doc_id)
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


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@app.post("/auth/register", response_model=AuthResponse)
def auth_register(payload: RegisterRequest):
    """
    Register a new local user and return a signed JWT.

    Passwords are hashed with PBKDF2-SHA256 (100 000 iterations, 32-byte
    random salt) before storage.  The raw password and hash are never
    returned in any response.

    Returns **409** when the email is already registered.

    Migration note: swap ``auth_store.register_user`` for a call that
    INSERTs into the PostgreSQL ``users`` table — no endpoint changes needed.
    """
    try:
        user = register_user(payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    token = create_token(user["id"], user["email"])
    return AuthResponse(access_token=token, user=UserPublic(**user))


@app.post("/auth/login", response_model=AuthResponse)
def auth_login(payload: LoginRequest):
    """
    Verify credentials and return a signed JWT.

    Always returns **401** for both wrong password *and* unknown email so
    that the response does not leak whether an email is registered.
    """
    user = authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user["id"], user["email"])
    return AuthResponse(access_token=token, user=UserPublic(**user))


@app.get("/auth/me", response_model=UserPublic)
def auth_me(authorization: str = Header(default="")):
    """
    Return the authenticated user's public profile.

    Expects an ``Authorization: Bearer <token>`` header.
    Returns **401** for missing, malformed, expired, or tampered tokens.

    Use this on page load to validate a stored JWT before showing the
    authenticated dashboard — fall back to the local email mock if this
    endpoint returns non-200.
    """
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header — expected: Bearer <token>",
        )
    token = authorization[7:].strip()
    try:
        claims = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    user = get_user_by_id(claims["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return UserPublic(**user)
