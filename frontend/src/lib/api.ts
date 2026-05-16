import type { ComparisonResult, DashboardStats, DocumentItem } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
