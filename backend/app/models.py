from pydantic import BaseModel, Field


class DocumentFragment(BaseModel):
    id: str
    page: int
    text: str


class RiskItem(BaseModel):
    category: str
    severity: str
    title: str
    explanation: str
    recommendation: str
    score: int


class SuggestionItem(BaseModel):
    title: str
    rationale: str
    proposed_text: str


class DocumentSummary(BaseModel):
    title: str
    summary: str
    highlights: list[str]
    risks: list[RiskItem]
    suggestions: list[SuggestionItem]
    language: str
    overall_score: int


class DocumentDetail(BaseModel):
    id: str
    filename: str
    page_count: int
    shared_with: list[str]
    activity: list["ActivityItem"] = Field(default_factory=list)
    comments: list["CommentItem"] = Field(default_factory=list)
    summary: DocumentSummary
    fragments: list[DocumentFragment]


class SearchResult(BaseModel):
    fragment: DocumentFragment
    score: float


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


class DashboardStats(BaseModel):
    total_documents: int
    high_risk_documents: int
    average_score: int
    shared_documents: int
