export type RiskSeverity = "low" | "medium" | "high";
export type ReviewStatus = "draft" | "in_review" | "approved";

export type Fragment = {
  id: string;
  page: number;
  text: string;
};

export type RiskItem = {
  category: string;
  severity: RiskSeverity;
  title: string;
  explanation: string;
  recommendation: string;
  score: number;
};

export type SuggestionItem = {
  title: string;
  rationale: string;
  proposed_text: string;
};

export type MissingClauseItem = {
  category: string;
  title: string;
  why_it_matters: string;
  expected_signal: string;
};

export type DocumentSummary = {
  title: string;
  summary: string;
  highlights: string[];
  risks: RiskItem[];
  suggestions: SuggestionItem[];
  missing_clauses: MissingClauseItem[];
  language: string;
  overall_score: number;
};

export type DocumentItem = {
  id: string;
  filename: string;
  version_group_id: string;
  version_number: number;
  is_latest_version: boolean;
  extraction_method: string;
  ocr_applied: boolean;
  page_count: number;
  shared_with: string[];
  owner: string;
  counterparty: string;
  contract_type: string;
  effective_date: string;
  expiry_date: string;
  renewal_date: string;
  review_status: ReviewStatus;
  activity: {
    type: string;
    label: string;
    detail: string;
  }[];
  comments: {
    author: string;
    body: string;
  }[];
  summary: DocumentSummary;
  fragments: Fragment[];
};

export type MetadataDraft = Pick<
  DocumentItem,
  "owner" | "counterparty" | "contract_type" | "effective_date" | "expiry_date" | "renewal_date"
>;

export type SearchResult = {
  fragment: Fragment;
  score: number;
};

export type RetrievalResult = {
  query: string;
  top_k: number;
  matches: SearchResult[];
  context: string;
};

export type QuestionResult = {
  answer: string;
  citations: Fragment[];
};

export type DashboardStats = {
  total_documents: number;
  high_risk_documents: number;
  average_score: number;
  shared_documents: number;
  pending_review_documents: number;
  approved_documents: number;
  expiring_soon_documents: number;
  renewal_due_documents: number;
};

export type ComparisonResult = {
  left_filename: string;
  right_filename: string;
  summary: string;
  differences: {
    category: string;
    left_text: string;
    right_text: string;
    impact: string;
  }[];
};

export type ReportResult = {
  filename: string;
  markdown: string;
};

export type DeadlineItem = {
  document_id: string;
  filename: string;
  kind: "expiry" | "renewal";
  due_date: string;
  days_remaining: number;
};
