import type {
  ComparisonResult,
  DashboardStats,
  DeadlineItem,
  DocumentItem,
  MetadataDraft,
  QuestionResult,
  ReportResult,
  ReviewStatus,
} from "./types";

const API_URL =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL ?? "http://127.0.0.1:8000"
    : process.env.NEXT_PUBLIC_API_URL ?? "/api";

export async function fetchDocuments(): Promise<DocumentItem[]> {
  const response = await fetch(`${API_URL}/documents`, { cache: "no-store" });
  if (!response.ok) return [];
  return response.json();
}

export async function fetchDashboard(): Promise<DashboardStats> {
  const response = await fetch(`${API_URL}/dashboard`, { cache: "no-store" });
  if (!response.ok) {
    return {
      total_documents: 0,
      high_risk_documents: 0,
      average_score: 0,
      shared_documents: 0,
      pending_review_documents: 0,
      approved_documents: 0,
      expiring_soon_documents: 0,
      renewal_due_documents: 0,
    };
  }
  return response.json();
}

export async function compareDocuments(leftId: string, rightId: string): Promise<ComparisonResult | null> {
  const response = await fetch(`${API_URL}/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ left_id: leftId, right_id: rightId }),
  });
  if (!response.ok) return null;
  return response.json();
}

export async function fetchReport(documentId: string): Promise<ReportResult | null> {
  const response = await fetch(`${API_URL}/documents/${documentId}/report`, { cache: "no-store" });
  if (!response.ok) return null;
  return response.json();
}

export async function fetchDeadlines(): Promise<DeadlineItem[]> {
  const response = await fetch(`${API_URL}/deadlines`, { cache: "no-store" });
  if (!response.ok) return [];
  return response.json();
}

export async function askDocumentQuestion(documentId: string, question: string): Promise<QuestionResult | null> {
  const response = await fetch(`${API_URL}/documents/${documentId}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!response.ok) return null;
  return response.json();
}

export async function uploadDocument(file: File): Promise<DocumentItem | null> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_URL}/documents/upload`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) return null;
  return response.json();
}

export async function uploadDocuments(files: File[]): Promise<DocumentItem[]> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  const response = await fetch(`${API_URL}/documents/bulk-upload`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) return [];
  return response.json();
}

export async function uploadDocumentVersion(documentId: string, file: File): Promise<DocumentItem | null> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_URL}/documents/${documentId}/versions`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) return null;
  return response.json();
}

export async function shareDocument(documentId: string, email: string): Promise<DocumentItem | null> {
  const response = await fetch(`${API_URL}/documents/${documentId}/share`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!response.ok) return null;
  return response.json();
}

export async function addDocumentComment(
  documentId: string,
  author: string,
  body: string,
): Promise<DocumentItem | null> {
  const response = await fetch(`${API_URL}/documents/${documentId}/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ author, body }),
  });
  if (!response.ok) return null;
  return response.json();
}

export async function updateDocumentStatus(
  documentId: string,
  status: ReviewStatus,
): Promise<DocumentItem | null> {
  const response = await fetch(`${API_URL}/documents/${documentId}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!response.ok) return null;
  return response.json();
}

export async function saveDocumentMetadata(
  documentId: string,
  metadata: MetadataDraft,
): Promise<DocumentItem | null> {
  const response = await fetch(`${API_URL}/documents/${documentId}/metadata`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(metadata),
  });
  if (!response.ok) return null;
  return response.json();
}
