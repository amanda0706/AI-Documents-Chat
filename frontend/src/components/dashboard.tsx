"use client";

import { useMemo, useState } from "react";
import { compareDocuments } from "@/lib/api";
import type { ComparisonResult, DashboardStats, DocumentItem, RiskItem } from "@/lib/types";

type DashboardProps = {
  documents: DocumentItem[];
  stats: DashboardStats;
};

type View = "overview" | "document" | "compare" | "suggestions";

const severityStyles = {
  low: "bg-emerald-50 text-emerald-700",
  medium: "bg-amber-50 text-amber-700",
  high: "bg-rose-50 text-rose-700",
};

export function Dashboard({ documents, stats }: DashboardProps) {
  const [email, setEmail] = useState("");
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [items, setItems] = useState(documents);
  const [selectedId, setSelectedId] = useState(documents[0]?.id ?? "");
  const [view, setView] = useState<View>("overview");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("Zadaj pytanie o termin wypowiedzenia, płatności albo odpowiedzialność.");
  const [citations, setCitations] = useState<DocumentItem["fragments"]>([]);
  const [query, setQuery] = useState("");
  const [shareEmail, setShareEmail] = useState("");
  const [compareId, setCompareId] = useState(documents[1]?.id ?? documents[0]?.id ?? "");
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);

  const selected = useMemo(
    () => items.find((document) => document.id === selectedId) ?? items[0],
    [items, selectedId],
  );

  const filteredFragments = useMemo(() => {
    if (!selected) return [];
    if (!query.trim()) return selected.fragments.slice(0, 6);
    return selected.fragments.filter((fragment) =>
      fragment.text.toLowerCase().includes(query.toLowerCase()),
    );
  }, [query, selected]);

  async function askQuestion() {
    if (!question.trim() || !selected) return;
    if (!selected.id.startsWith("demo-")) {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/documents/${selected.id}/ask`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
        },
      );
      if (response.ok) {
        const payload = await response.json();
        setAnswer(payload.answer);
        setCitations(payload.citations ?? []);
        return;
      }
    }
    const hit =
      selected.fragments.find((fragment) =>
        question
          .toLowerCase()
          .split(/\s+/)
          .some((word) => word.length > 3 && fragment.text.toLowerCase().includes(word)),
      ) ?? selected.fragments[0];
    setAnswer(hit ? `Najbardziej pasujący fragment jest na stronie ${hit.page}: ${hit.text}` : "Brak trafienia.");
    setCitations(hit ? [hit] : []);
  }

  async function uploadDocument(file?: File) {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/documents/upload`,
      { method: "POST", body: formData },
    );
    if (!response.ok) return;
    const created = await response.json();
    setItems((current) => [created, ...current]);
    setSelectedId(created.id);
    setView("document");
  }

  async function shareDocument() {
    if (!selected || !shareEmail.trim()) return;
    if (!selected.id.startsWith("demo-")) {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/documents/${selected.id}/share`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: shareEmail }),
        },
      );
      if (response.ok) {
        const updated = await response.json();
        setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      }
    } else {
      setItems((current) =>
        current.map((item) =>
          item.id === selected.id ? { ...item, shared_with: [...item.shared_with, shareEmail] } : item,
        ),
      );
    }
    setShareEmail("");
  }

  async function runComparison() {
    if (!selected || !compareId) return;
    if (!selected.id.startsWith("demo-") && !compareId.startsWith("demo-")) {
      setComparison(await compareDocuments(selected.id, compareId));
      return;
    }
    const other = items.find((item) => item.id === compareId);
    setComparison({
      left_filename: selected.filename,
      right_filename: other?.filename ?? "Unknown",
      summary: "Znaleziono różnice w terminie płatności i wypowiedzenia.",
      differences: [
        {
          category: "payment",
          left_text: "net 60",
          right_text: "net 30",
          impact: "Wpływ na cash flow.",
        },
        {
          category: "termination",
          left_text: "90 days",
          right_text: "30 days",
          impact: "Wpływ na elastyczność zakończenia umowy.",
        },
      ],
    });
  }

  if (!isLoggedIn) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-mist p-5">
        <section className="w-full max-w-md rounded-[28px] bg-white p-8 shadow-panel">
          <h1 className="text-3xl font-semibold tracking-tight">ClausePilot</h1>
          <p className="mt-3 leading-7 text-slate-600">
            Zaloguj się, aby analizować umowy, porównywać wersje i wracać do historii.
          </p>
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="adres e-mail"
            className="mt-6 w-full rounded-2xl border border-line px-4 py-3 outline-none"
          />
          <button
            onClick={() => setIsLoggedIn(Boolean(email.trim()))}
            className="mt-3 w-full rounded-2xl bg-slate-900 px-4 py-3 font-medium text-white"
          >
            Continue
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-mist p-5">
      <div className="mx-auto grid max-w-[1440px] grid-cols-[250px_minmax(0,1fr)] gap-5">
        <aside className="rounded-[28px] bg-white p-5 shadow-panel">
          <div className="mb-8 text-2xl font-semibold tracking-tight">ClausePilot</div>
          <div className="mb-5 rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">{email}</div>
          <label className="mb-6 block cursor-pointer rounded-2xl bg-accent px-4 py-3 text-center text-sm font-medium text-white">
            Upload document
            <input type="file" accept=".pdf" className="hidden" onChange={(event) => uploadDocument(event.target.files?.[0])} />
          </label>
          <nav className="mb-8 space-y-2">
            {[
              ["overview", "Dashboard"],
              ["document", "Document"],
              ["compare", "Compare"],
              ["suggestions", "Suggestions"],
            ].map(([key, label]) => (
              <button
                key={key}
                onClick={() => setView(key as View)}
                className={`w-full rounded-2xl px-4 py-3 text-left text-sm ${
                  view === key ? "bg-slate-900 text-white" : "bg-slate-50 text-slate-700"
                }`}
              >
                {label}
              </button>
            ))}
          </nav>
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Documents</p>
          <div className="space-y-2">
            {items.map((document) => (
              <button
                key={document.id}
                onClick={() => setSelectedId(document.id)}
                className={`w-full rounded-2xl px-4 py-3 text-left text-sm ${
                  document.id === selected?.id ? "bg-blue-50 text-slate-900" : "bg-slate-50 text-slate-700"
                }`}
              >
                <div className="font-medium">{document.filename}</div>
                <div className="mt-1 text-xs opacity-70">{document.page_count} pages</div>
              </button>
            ))}
          </div>
        </aside>

        <section className="space-y-5">
          {view === "overview" && <Overview stats={stats} documents={items} />}
          {view === "document" && selected && (
            <DocumentWorkspace
              selected={selected}
              query={query}
              setQuery={setQuery}
              fragments={filteredFragments}
              question={question}
              setQuestion={setQuestion}
              answer={answer}
              citations={citations}
              askQuestion={askQuestion}
              shareEmail={shareEmail}
              setShareEmail={setShareEmail}
              shareDocument={shareDocument}
            />
          )}
          {view === "compare" && selected && (
            <CompareView
              items={items}
              selected={selected}
              compareId={compareId}
              setCompareId={setCompareId}
              runComparison={runComparison}
              comparison={comparison}
            />
          )}
          {view === "suggestions" && selected && <SuggestionsView selected={selected} />}
        </section>
      </div>
    </main>
  );
}

function Overview({ stats, documents }: { stats: DashboardStats; documents: DocumentItem[] }) {
  return (
    <>
      <div className="grid grid-cols-4 gap-5">
        {[
          ["Documents", stats.total_documents],
          ["High risk", stats.high_risk_documents],
          ["Average score", stats.average_score],
          ["Shared", stats.shared_documents],
        ].map(([label, value]) => (
          <div key={label} className="rounded-[28px] bg-white p-5 shadow-panel">
            <p className="text-sm text-slate-400">{label}</p>
            <p className="mt-3 text-3xl font-semibold">{value}</p>
          </div>
        ))}
      </div>
      <div className="rounded-[28px] bg-white p-6 shadow-panel">
        <h2 className="text-xl font-semibold">Portfolio-ready product dashboard</h2>
        <div className="mt-5 space-y-3">
          {documents.map((document) => (
            <div key={document.id} className="flex items-center justify-between rounded-2xl bg-slate-50 p-4">
              <div>
                <div className="font-medium">{document.filename}</div>
                <div className="text-sm text-slate-500">{document.summary.language.toUpperCase()} · {document.page_count} pages</div>
              </div>
              <div className="text-right">
                <div className="text-sm text-slate-400">Score</div>
                <div className="text-2xl font-semibold">{document.summary.overall_score}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

function DocumentWorkspace(props: {
  selected: DocumentItem;
  query: string;
  setQuery: (value: string) => void;
  fragments: DocumentItem["fragments"];
  question: string;
  setQuestion: (value: string) => void;
  answer: string;
  citations: DocumentItem["fragments"];
  askQuestion: () => void;
  shareEmail: string;
  setShareEmail: (value: string) => void;
  shareDocument: () => void;
}) {
  const { selected } = props;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_360px] gap-5">
      <section className="rounded-[28px] bg-white p-6 shadow-panel">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <p className="text-sm text-slate-400">Current document</p>
            <h1 className="text-2xl font-semibold tracking-tight">{selected.filename}</h1>
          </div>
          <input value={props.query} onChange={(event) => props.setQuery(event.target.value)} placeholder="Search fragments" className="w-64 rounded-2xl border border-line px-4 py-3 text-sm outline-none" />
        </div>
        <div className="space-y-4">
          {props.fragments.map((fragment) => (
            <article key={fragment.id} className="rounded-3xl border border-line bg-slate-50 p-5 leading-7">
              <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Page {fragment.page}</div>
              {fragment.text}
            </article>
          ))}
        </div>
      </section>
      <aside className="space-y-5">
        <Panel title="AI Summary">
          <p className="leading-7 text-slate-700">{selected.summary.summary}</p>
        </Panel>
        <Panel title={`Risk score · ${selected.summary.overall_score}/100`}>
          <div className="space-y-3">
            {selected.summary.risks.map((risk) => <RiskRow key={risk.category} risk={risk} />)}
          </div>
        </Panel>
        <Panel title="Ask this contract">
          <textarea value={props.question} onChange={(event) => props.setQuestion(event.target.value)} placeholder="Np. jaki jest termin wypowiedzenia?" className="min-h-24 w-full rounded-2xl border border-line p-4 text-sm outline-none" />
          <button onClick={props.askQuestion} className="mt-3 w-full rounded-2xl bg-slate-900 px-4 py-3 text-sm font-medium text-white">Ask</button>
          <div className="mt-4 rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-700">{props.answer}</div>
          {props.citations.length > 0 && (
            <div className="mt-4 space-y-3">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                Supporting passages
              </p>
              {props.citations.map((citation) => (
                <article key={citation.id} className="rounded-2xl border border-line p-4 text-sm leading-6">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                    Page {citation.page}
                  </div>
                  {citation.text}
                </article>
              ))}
            </div>
          )}
        </Panel>
        <Panel title="Share document">
          <input value={props.shareEmail} onChange={(event) => props.setShareEmail(event.target.value)} placeholder="email współpracownika" className="w-full rounded-2xl border border-line px-4 py-3 text-sm outline-none" />
          <button onClick={props.shareDocument} className="mt-3 w-full rounded-2xl border border-line px-4 py-3 text-sm font-medium">Share</button>
          <p className="mt-3 text-sm text-slate-500">{selected.shared_with.join(", ") || "Jeszcze nikomu nie udostępniono."}</p>
        </Panel>
      </aside>
    </div>
  );
}

function CompareView(props: {
  items: DocumentItem[];
  selected: DocumentItem;
  compareId: string;
  setCompareId: (value: string) => void;
  runComparison: () => void;
  comparison: ComparisonResult | null;
}) {
  return (
    <div className="rounded-[28px] bg-white p-6 shadow-panel">
      <h2 className="text-2xl font-semibold">Compare contracts</h2>
      <div className="mt-5 flex gap-3">
        <div className="rounded-2xl bg-slate-50 px-4 py-3">{props.selected.filename}</div>
        <select value={props.compareId} onChange={(event) => props.setCompareId(event.target.value)} className="rounded-2xl border border-line px-4 py-3">
          {props.items.map((item) => <option key={item.id} value={item.id}>{item.filename}</option>)}
        </select>
        <button onClick={props.runComparison} className="rounded-2xl bg-slate-900 px-5 py-3 text-white">Compare</button>
      </div>
      {props.comparison && (
        <div className="mt-6">
          <p className="mb-4 text-slate-600">{props.comparison.summary}</p>
          <div className="space-y-3">
            {props.comparison.differences.map((difference) => (
              <div key={difference.category} className="rounded-2xl bg-slate-50 p-4">
                <div className="font-medium">{difference.category}</div>
                <div className="mt-2 grid grid-cols-2 gap-3 text-sm">
                  <div>{difference.left_text}</div>
                  <div>{difference.right_text}</div>
                </div>
                <p className="mt-2 text-sm text-slate-500">{difference.impact}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SuggestionsView({ selected }: { selected: DocumentItem }) {
  return (
    <div className="rounded-[28px] bg-white p-6 shadow-panel">
      <h2 className="text-2xl font-semibold">AI suggestions</h2>
      <div className="mt-5 space-y-4">
        {selected.summary.suggestions.length ? selected.summary.suggestions.map((suggestion) => (
          <article key={suggestion.title} className="rounded-3xl bg-slate-50 p-5">
            <h3 className="font-semibold">{suggestion.title}</h3>
            <p className="mt-2 text-slate-600">{suggestion.rationale}</p>
            <pre className="mt-3 whitespace-pre-wrap rounded-2xl bg-white p-4 text-sm text-slate-700">{suggestion.proposed_text}</pre>
          </article>
        )) : <p className="text-slate-500">Brak sugestii wymagających zmiany.</p>}
      </div>
    </div>
  );
}

function RiskRow({ risk }: { risk: RiskItem }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="font-medium">{risk.title}</div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${severityStyles[risk.severity]}`}>{risk.severity}</span>
      </div>
      <p className="mt-2 text-sm text-slate-600">{risk.explanation}</p>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-[28px] bg-white p-5 shadow-panel">
      <p className="mb-3 text-sm text-slate-400">{title}</p>
      {children}
    </section>
  );
}
