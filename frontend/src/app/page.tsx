import { Dashboard } from "@/components/dashboard";
import { fetchDashboard, fetchDocuments } from "@/lib/api";

const demoDocuments = [
  {
    id: "demo-1",
    filename: "Master Services Agreement.pdf",
    page_count: 3,
    shared_with: ["anna@firma.pl"],
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
    page_count: 2,
    shared_with: [],
    summary: {
      title: "Supplier Agreement.pdf",
      summary: "Alternatywna wersja umowy z krótszym terminem płatności i mniejszym ryzykiem.",
      highlights: [],
      language: "en",
      overall_score: 82,
      risks: [],
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
};

export default async function Home() {
  const [documents, stats] = await Promise.all([fetchDocuments(), fetchDashboard()]);
  return (
    <Dashboard
      documents={documents.length ? documents : demoDocuments}
      stats={documents.length ? stats : demoStats}
    />
  );
}
