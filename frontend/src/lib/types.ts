export type Fragment = {
  id: string;
  page: number;
  text: string;
};

export type RiskItem = {
  category: string;
  severity: "low" | "medium" | "high";
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

export type DocumentSummary = {
  title: string;
  summary: string;
  highlights: string[];
  risks: RiskItem[];
  suggestions: SuggestionItem[];
  language: string;
  overall_score: number;
};

export type DocumentItem = {
  id: string;
  filename: string;
  page_count: number;
  shared_with: string[];
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

export type DashboardStats = {
  total_documents: number;
  high_risk_documents: number;
  average_score: number;
  shared_documents: number;
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
