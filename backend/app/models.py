from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class RiskSeverity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class ReviewStatus(StrEnum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"


class DocumentFragment(BaseModel):
    id: str
    page: int
    text: str


class RiskItem(BaseModel):
    category: str
    severity: RiskSeverity
    title: str
    explanation: str
    recommendation: str
    score: int


class SuggestionItem(BaseModel):
    title: str
    rationale: str
    proposed_text: str


class MissingClauseItem(BaseModel):
    category: str
    title: str
    why_it_matters: str
    expected_signal: str


class DocumentSummary(BaseModel):
    title: str
    summary: str
    highlights: list[str]
    risks: list[RiskItem]
    suggestions: list[SuggestionItem]
    missing_clauses: list[MissingClauseItem]
    language: str
    overall_score: int


class DocumentDetail(BaseModel):
    id: str
    filename: str
    version_group_id: str = ""
    version_number: int = 1
    is_latest_version: bool = True
    extraction_method: str = "text"
    ocr_applied: bool = False
    page_count: int
    shared_with: list[str]
    owner: str = ""
    counterparty: str = ""
    contract_type: str = ""
    effective_date: str = ""
    expiry_date: str = ""
    renewal_date: str = ""
    review_status: ReviewStatus = ReviewStatus.draft
    activity: list["ActivityItem"] = Field(default_factory=list)
    comments: list["CommentItem"] = Field(default_factory=list)
    summary: DocumentSummary
    fragments: list[DocumentFragment]


class SearchResult(BaseModel):
    fragment: DocumentFragment
    score: float


class RetrievalResult(BaseModel):
    query: str
    top_k: int
    matches: list[SearchResult]
    context: str


class QuestionRequest(BaseModel):
    question: str


class QuestionResponse(BaseModel):
    answer: str
    citations: list[DocumentFragment]


class ActivityItem(BaseModel):
    type: str
    label: str
    detail: str


class CommentItem(BaseModel):
    author: str
    body: str


class CompareRequest(BaseModel):
    left_id: str
    right_id: str


class DifferenceItem(BaseModel):
    category: str
    left_text: str
    right_text: str
    impact: str


class ComparisonResponse(BaseModel):
    left_filename: str
    right_filename: str
    summary: str
    differences: list[DifferenceItem]


class ReportResponse(BaseModel):
    filename: str
    markdown: str


class ShareRequest(BaseModel):
    email: str


class CommentRequest(BaseModel):
    author: str
    body: str


class ReviewStatusRequest(BaseModel):
    status: ReviewStatus


class MetadataRequest(BaseModel):
    owner: str = ""
    counterparty: str = ""
    contract_type: str = ""
    effective_date: str = ""
    expiry_date: str = ""
    renewal_date: str = ""

    @field_validator("effective_date", "expiry_date", "renewal_date")
    @classmethod
    def validate_iso_dates(cls, value: str) -> str:
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("Dates must use YYYY-MM-DD format") from exc
        return value


class DashboardStats(BaseModel):
    total_documents: int
    high_risk_documents: int
    average_score: int
    shared_documents: int
    pending_review_documents: int
    approved_documents: int
    expiring_soon_documents: int
    renewal_due_documents: int


class DeadlineItem(BaseModel):
    document_id: str
    filename: str
    kind: str
    due_date: str
    days_remaining: int


class MetricsResponse(BaseModel):
    service: str
    total_documents: int
    total_fragments: int
    total_risks: int
    high_risk_documents: int
    average_score: int
    shared_documents: int
    comments_count: int
    activity_events: int
    latest_upload_filename: str = ""


class ProviderStatus(BaseModel):
    provider: str
    model: str
    cloud_enabled: bool


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    """Body for POST /auth/register."""

    email: str = Field(..., min_length=3, description="User email address")
    password: str = Field(..., min_length=6, description="Password (min 6 chars)")


class LoginRequest(BaseModel):
    """Body for POST /auth/login."""

    email: str
    password: str


class UserPublic(BaseModel):
    """Safe subset of a user record — never includes password_hash or salt."""

    id: str
    email: str
    created_at: str


class AuthResponse(BaseModel):
    """Returned by /auth/register and /auth/login on success."""

    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# ---------------------------------------------------------------------------
# Embeddings / vector retrieval
# ---------------------------------------------------------------------------

class EmbeddingMeta(BaseModel):
    """
    Embedding record without the raw vector — safe to return in list responses.

    The ``vector`` field is intentionally excluded here to keep payloads
    small.  Use ``include_vectors=true`` on ``GET /documents/{id}/embeddings``
    to receive the raw floats when needed (e.g. for client-side visualisation).

    Migration note: in a production pgvector setup this record maps directly
    to a row in the ``fragment_embeddings`` table::

        CREATE TABLE fragment_embeddings (
            fragment_id  TEXT PRIMARY KEY,
            document_id  TEXT NOT NULL,
            page         INT,
            text         TEXT,
            provider     TEXT,
            dim          INT,
            embedding    vector(1536)   -- or vector(128) for local demo
        );
    """

    document_id: str
    fragment_id: str
    page: int
    text: str
    provider: str
    dim: int
    vector: list[float] | None = None
    """Raw embedding floats. ``None`` unless ``include_vectors=true`` is passed."""


class VectorSearchResult(BaseModel):
    """One ranked fragment returned by a vector similarity search."""

    rank: int
    fragment_id: str
    page: int
    text: str
    score: float


class VectorSearchResponse(BaseModel):
    """Full response from ``GET /documents/{id}/vector-search``."""

    query: str
    top_k: int
    provider: str
    dim: int
    results: list[VectorSearchResult]


class ReindexRequest(BaseModel):
    """
    Request body for ``POST /embeddings/reindex``.

    Omit ``doc_id`` (or pass ``null``) to reindex every document in the store.
    """

    doc_id: str | None = None


class ReindexResponse(BaseModel):
    """Summary of a completed reindex operation."""

    indexed_documents: int
    total_fragments: int
    provider: str
    dim: int
