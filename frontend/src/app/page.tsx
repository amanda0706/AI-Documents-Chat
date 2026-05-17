import { Dashboard } from "@/components/dashboard";
import { fetchDashboard, fetchDeadlines, fetchDocuments } from "@/lib/api";

const demoDocuments = [
  {
    id: "demo-1",
    filename: "Master Services Agreement.pdf",
    version_group_id: "demo-1",
    version_number: 2,
    is_latest_version: true,
    extraction_method: "text",
    ocr_applied: false,
    page_count: 3,
    shared_with: ["anna@firma.pl"],
    owner: "anna@firma.pl",
    counterparty: "Northwind Labs",
    contract_type: "MSA",
    effective_date: "2026-01-01",
    expiry_date: "2026-06-30",
    renewal_date: "2026-06-10",
    review_status: "in_review",
    activity: [
      {
        type: "upload",
        label: "Document uploaded",
        detail: "File added and analyzed locally.",
      },
    ],
    comments: [
      {
        author: "anna@firma.pl",
        body: "Sprawdźmy jeszcze limit odpowiedzialności przed podpisem.",
      },
    ],
    summary: {
      title: "Master Services Agreement.pdf",
      summary:
        "Umowa reguluje zakres usług, płatności oraz zasady rozwiązania współpracy. Szczególną uwagę zwracają długi termin płatności i rozbudowane ograniczenia odpowiedzialności.",
      highlights: [],
      language: "en",
      overall_score: 41,
      risks: [
        {
          category: "payment",
          severity: "medium",
          title: "Długi termin płatności",
          explanation: "Płatność po 60 dniach może obciążać cash flow.",
          recommendation: "Skróć termin do 30 dni.",
          score: 18,
        },
        {
          category: "termination",
          severity: "medium",
          title: "Długi okres wypowiedzenia",
          explanation: "90 dni ogranicza elastyczność operacyjną.",
          recommendation: "Rozważ 30 dni.",
          score: 16,
        },
        {
          category: "liability",
          severity: "high",
          title: "Ograniczona odpowiedzialność",
          explanation: "Wyłączenia mogą utrudnić dochodzenie roszczeń.",
          recommendation: "Dodaj wyjątki dla poufności i winy umyślnej.",
          score: 25,
        },
      ],
      missing_clauses: [
        {
          category: "governing_law",
          title: "Governing law",
          why_it_matters: "Brak tej klauzuli utrudnia ustalenie w?a?ciwego prawa.",
          expected_signal: "governing law / jurisdiction",
        },
      ],
      suggestions: [
        {
          title: "Skróć termin płatności",
          rationale: "Poprawia płynność.",
          proposed_text: "Payment terms shall be net 30 days from receipt of a valid invoice.",
        },
      ],
    },
    fragments: [
      { id: "f1", page: 1, text: "Payment terms are net 60 days from the date of a correctly issued invoice." },
      { id: "f2", page: 2, text: "Either party may terminate this agreement with 90 days written notice." },
      { id: "f3", page: 3, text: "Liability for indirect damages is excluded unless caused by wilful misconduct." },
    ],
  },
  {
    id: "demo-2",
    filename: "Supplier Agreement.pdf",
    version_group_id: "demo-2",
    version_number: 1,
    is_latest_version: true,
    extraction_method: "text",
    ocr_applied: false,
    page_count: 2,
    shared_with: [],
    owner: "marta@firma.pl",
    counterparty: "Contoso Supply",
    contract_type: "Supplier Agreement",
    effective_date: "2026-02-15",
    expiry_date: "2027-02-14",
    renewal_date: "2027-01-15",
    review_status: "approved",
    activity: [
      {
        type: "upload",
        label: "Document uploaded",
        detail: "File added and analyzed locally.",
      },
    ],
    comments: [],
    summary: {
      title: "Supplier Agreement.pdf",
      summary: "Alternatywna wersja umowy z krótszym terminem płatności i mniejszym ryzykiem.",
      highlights: [],
      language: "en",
      overall_score: 82,
      risks: [],
      missing_clauses: [],
      suggestions: [],
    },
    fragments: [
      { id: "g1", page: 1, text: "Payment terms are net 30 days from invoice receipt." },
      { id: "g2", page: 2, text: "Either party may terminate this agreement with 30 days written notice." },
    ],
  },
];

const demoStats = {
  total_documents: 2,
  high_risk_documents: 1,
  average_score: 62,
  shared_documents: 1,
  pending_review_documents: 1,
  approved_documents: 1,
  expiring_soon_documents: 1,
  renewal_due_documents: 1,
};

const demoDeadlines = [
  {
    document_id: "demo-1",
    filename: "Master Services Agreement.pdf",
    kind: "renewal" as const,
    due_date: "2026-06-10",
    days_remaining: 24,
  },
  {
    document_id: "demo-1",
    filename: "Master Services Agreement.pdf",
    kind: "expiry" as const,
    due_date: "2026-06-30",
    days_remaining: 44,
  },
];

export default async function Home() {
  const [documents, stats, deadlines] = await Promise.all([fetchDocuments(), fetchDashboard(), fetchDeadlines()]);
  return (
    <Dashboard
      documents={documents}
      stats={documents.length ? stats : demoStats}
      demoDocuments={demoDocuments}
      deadlines={documents.length ? deadlines : demoDeadlines}
    />
  );
}
