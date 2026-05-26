import type {
  ComparisonResult,
  DashboardStats,
  DeadlineItem,
  DocumentItem,
  MetadataDraft,
  QuestionResult,
  ReportResult,
  RetrievalResult,
  ReviewStatus,
} from "./types";

const API_URL =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL ?? "http://127.0.0.1:8000"
    : process.env.NEXT_PUBLIC_API_URL ?? "/api";

async function requestJson<T>(request: () => Promise<Response>, fallback: T): Promise<T> {
  try {
    const response = await request();
    if (!response.ok) return fallback;
    return response.json();
  } catch {
    return fallback;
  }
}

export async function fetchDocuments(): Promise<DocumentItem[]> {
  return requestJson(() => fetch(`${API_URL}/documents`, { cache: "no-store" }), []);
}

export async function fetchDashboard(): Promise<DashboardStats> {
  return requestJson(() => fetch(`${API_URL}/dashboard`, { cache: "no-store" }), {
    total_documents: 0,
    high_risk_documents: 0,
    average_score: 0,
    shared_documents: 0,
    pending_review_documents: 0,
    approved_documents: 0,
    expiring_soon_documents: 0,
    renewal_due_documents: 0,
  });
}

export async function compareDocuments(leftId: string, rightId: string): Promise<ComparisonResult | null> {
  return requestJson(
    () => fetch(`${API_URL}/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ left_id: leftId, right_id: rightId }),
    }),
    null,
  );
}

export async function fetchReport(documentId: string): Promise<ReportResult | null> {
  return requestJson(() => fetch(`${API_URL}/documents/${documentId}/report`, { cache: "no-store" }), null);
}

export async function retrieveDocumentContext(
  documentId: string,
  query: string,
  topK = 3,
): Promise<RetrievalResult | null> {
  const params = new URLSearchParams({ query, top_k: String(topK) });
  return requestJson(
    () => fetch(`${API_URL}/documents/${documentId}/retrieval?${params.toString()}`, { cache: "no-store" }),
    null,
  );
}

export async function fetchDeadlines(): Promise<DeadlineItem[]> {
  return requestJson(() => fetch(`${API_URL}/deadlines`, { cache: "no-store" }), []);
}

export async function askDocumentQuestion(documentId: string, question: string): Promise<QuestionResult | null> {
  return requestJson(
    () => fetch(`${API_URL}/documents/${documentId}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }),
    null,
  );
}

export async function uploadDocument(file: File, owner = ""): Promise<DocumentItem | null> {
  const formData = new FormData();
  formData.append("file", file);
  if (owner) formData.append("owner", owner);
  return requestJson(
    () => fetch(`${API_URL}/documents/upload`, {
      method: "POST",
      body: formData,
    }),
    null,
  );
}

export async function uploadDocuments(files: File[], owner = ""): Promise<DocumentItem[]> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  if (owner) formData.append("owner", owner);
  return requestJson(
    () => fetch(`${API_URL}/documents/bulk-upload`, {
      method: "POST",
      body: formData,
    }),
    [],
  );
}

export async function uploadDocumentVersion(documentId: string, file: File): Promise<DocumentItem | null> {
  const formData = new FormData();
  formData.append("file", file);
  return requestJson(
    () => fetch(`${API_URL}/documents/${documentId}/versions`, {
      method: "POST",
      body: formData,
    }),
    null,
  );
}

export async function shareDocument(documentId: string, email: string): Promise<DocumentItem | null> {
  return requestJson(
    () => fetch(`${API_URL}/documents/${documentId}/share`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    }),
    null,
  );
}

export async function addDocumentComment(
  documentId: string,
  author: string,
  body: string,
): Promise<DocumentItem | null> {
  return requestJson(
    () => fetch(`${API_URL}/documents/${documentId}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ author, body }),
    }),
    null,
  );
}

export async function updateDocumentStatus(
  documentId: string,
  status: ReviewStatus,
): Promise<DocumentItem | null> {
  return requestJson(
    () => fetch(`${API_URL}/documents/${documentId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }),
    null,
  );
}

export async function saveDocumentMetadata(
  documentId: string,
  metadata: MetadataDraft,
): Promise<DocumentItem | null> {
  return requestJson(
    () => fetch(`${API_URL}/documents/${documentId}/metadata`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(metadata),
    }),
    null,
  );
}

export async function deleteDocument(documentId: string): Promise<boolean> {
  return requestJson(
    () => fetch(`${API_URL}/documents/${documentId}`, {
      method: "DELETE",
    }),
    null,
  ).then((result) => Boolean(result));
}
