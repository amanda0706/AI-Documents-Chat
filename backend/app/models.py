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
