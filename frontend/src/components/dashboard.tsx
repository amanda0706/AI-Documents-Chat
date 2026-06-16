"use client";

import { type DragEvent, useEffect, useMemo, useState } from "react";
import {
  addDocumentComment,
  askDocumentQuestion,
  authLogin,
  authMe,
  authRegister,
  compareDocuments,
  deleteDocument,
  fetchProcessingInfo,
  fetchReport,
  retrieveDocumentContext,
  saveDocumentMetadata,
  shareDocument as shareDocumentRequest,
  streamDocumentQuestion,
  updateDocumentStatus,
  uploadDocument as uploadDocumentRequest,
  uploadDocuments,
  uploadDocumentVersion,
} from "@/lib/api";
import type {
  ComparisonResult,
  DashboardStats,
  DeadlineItem,
  DocumentItem,
  MetadataDraft,
  ProcessingInfo,
  ProviderStatus,
  ReportResult,
  RetrievalResult,
  ReviewStatus,
  RiskItem,
  RiskSeverity,
  StorageStatus,
} from "@/lib/types";

type DashboardProps = {
  documents: DocumentItem[];
  stats: DashboardStats;
  demoDocuments: DocumentItem[];
  deadlines: DeadlineItem[];
  providerStatus: ProviderStatus;
  storageStatus: StorageStatus;
};

type View = "overview" | "document" | "compare" | "suggestions";
type AuthMode = "login" | "register";
type RiskFilter = "all" | RiskSeverity;
type StatusFilter = "all" | ReviewStatus;
type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations?: DocumentItem["fragments"];
  timestamp: string;
};
type Notice = {
  tone: "success" | "error";
  message: string;
};
type UploadProgress = {
  label: string;
  detail: string;
  percent: number;
};

const severityStyles = {
  low: "bg-emerald-50 text-emerald-700",
  medium: "bg-amber-50 text-amber-700",
  high: "bg-rose-50 text-rose-700",
};

const reviewStatusLabels = {
  draft: "Draft",
  in_review: "In review",
  approved: "Approved",
};

const riskMarkers: Record<string, string[]> = {
  payment: ["net 60", "net 90", "within sixty", "within ninety"],
  termination: ["90 days", "terminate for convenience"],
  liability: ["limitation of liability", "indirect damages", "consequential"],
  renewal: ["automatic renewal", "auto-renew"],
  confidentiality: ["confidentiality", "confidential information", "non-disclosure"],
};

export function Dashboard({ documents, stats, demoDocuments, deadlines, providerStatus, storageStatus }: DashboardProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [items, setItems] = useState(documents);
  const [selectedId, setSelectedId] = useState(documents[0]?.id ?? "");
  const [view, setView] = useState<View>("overview");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("Zadaj pytanie o termin wypowiedzenia, płatności albo odpowiedzialność.");
  const [citations, setCitations] = useState<DocumentItem["fragments"]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [query, setQuery] = useState("");
  const [retrieval, setRetrieval] = useState<RetrievalResult | null>(null);
  const [shareEmail, setShareEmail] = useState("");
  const [commentBody, setCommentBody] = useState("");
  const [metadataDraft, setMetadataDraft] = useState<MetadataDraft>({
    owner: documents[0]?.owner ?? "",
    counterparty: documents[0]?.counterparty ?? "",
    contract_type: documents[0]?.contract_type ?? "",
    effective_date: documents[0]?.effective_date ?? "",
    expiry_date: documents[0]?.expiry_date ?? "",
    renewal_date: documents[0]?.renewal_date ?? "",
  });
  const [compareId, setCompareId] = useState(documents[1]?.id ?? documents[0]?.id ?? "");
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [report, setReport] = useState<ReportResult | null>(null);
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [documentSearch, setDocumentSearch] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
  const [isDraggingUpload, setIsDraggingUpload] = useState(false);
  const [processingInfo, setProcessingInfo] = useState<ProcessingInfo | null>(null);

  useEffect(() => {
    if (selectedId) {
      fetchProcessingInfo(selectedId).then(setProcessingInfo);
    } else {
      setProcessingInfo(null);
    }
  }, [selectedId]);

  useEffect(() => {
    // On load: try to restore session from a stored JWT first.
    // If the JWT is valid, /auth/me returns the user profile.
    // If the backend is unavailable or the token is expired, fall back
    // to the local email-only session (stored separately in localStorage).
    const storedToken = window.localStorage.getItem("luminaclause:token");
    if (storedToken) {
      authMe(storedToken).then((user) => {
        if (user) {
          setEmail(user.email);
          setIsLoggedIn(true);
        } else {
          // Token invalid/expired — clear it and check for legacy email session
          window.localStorage.removeItem("luminaclause:token");
          const savedEmail = window.localStorage.getItem("luminaclause:userEmail");
          if (savedEmail) { setEmail(savedEmail); setIsLoggedIn(true); }
        }
      });
    } else {
      const savedEmail = window.localStorage.getItem("luminaclause:userEmail");
      if (savedEmail) { setEmail(savedEmail); setIsLoggedIn(true); }
    }
  }, []);

  const userEmail = email.trim().toLowerCase();
  const scopedItems = useMemo(() => {
    if (!userEmail) return items;
    return items.filter((document) => {
      const owner = document.owner.trim().toLowerCase();
      const sharedWith = document.shared_with.map((value) => value.toLowerCase());
      return !owner || owner === userEmail || sharedWith.includes(userEmail) || document.id.startsWith("demo-");
    });
  }, [items, userEmail]);

  const scopedStats = useMemo(() => ({
    ...stats,
    total_documents: scopedItems.length,
    high_risk_documents: scopedItems.filter((document) => document.summary.risks.some((risk) => risk.severity === "high")).length,
    average_score: scopedItems.length
      ? Math.round(scopedItems.reduce((sum, document) => sum + document.summary.overall_score, 0) / scopedItems.length)
      : 0,
    shared_documents: scopedItems.filter((document) => document.shared_with.length > 0).length,
    pending_review_documents: scopedItems.filter((document) => document.review_status === "in_review").length,
    approved_documents: scopedItems.filter((document) => document.review_status === "approved").length,
  }), [scopedItems, stats]);

  async function completeAuth() {
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail.includes("@")) {
      setNotice({ tone: "error", message: "Enter a valid email address to continue." });
      return;
    }

    // authRegister / authLogin return null on network error (backend down) and
    // throw an Error with a human-readable message on credential/validation
    // errors (401, 409, 422).  Only the null / network-error path falls back to
    // the local email-only demo session.
    const authFn = authMode === "register" ? authRegister : authLogin;
    let result: Awaited<ReturnType<typeof authFn>> = null;
    try {
      result = await authFn(normalizedEmail, password);
    } catch (err) {
      // Credential or validation error from the backend — show it; do NOT log in.
      setNotice({
        tone: "error",
        message: err instanceof Error ? err.message : "Authentication failed.",
      });
      return;
    }

    if (result) {
      // Backend auth succeeded — store the JWT and restore from the user profile.
      window.localStorage.setItem("luminaclause:token", result.access_token);
      window.localStorage.setItem("luminaclause:userEmail", result.user.email);
      setEmail(result.user.email);
      setIsLoggedIn(true);
      setPassword("");
      setNotice({
        tone: "success",
        message: authMode === "register" ? "Account created." : "Signed in.",
      });
    } else {
      // null = network error — backend is unavailable; fall back to local demo session.
      window.localStorage.setItem("luminaclause:userEmail", normalizedEmail);
      setEmail(normalizedEmail);
      setIsLoggedIn(true);
      setPassword("");
      setNotice({
        tone: "success",
        message: authMode === "register" ? "Local workspace created." : "Signed in locally.",
      });
    }
  }

  function signOut() {
    window.localStorage.removeItem("luminaclause:token");
    window.localStorage.removeItem("luminaclause:userEmail");
    setIsLoggedIn(false);
    setEmail("");
    setPassword("");
    setMessages([]);
    setCitations([]);
    setAnswer("Ask a question to generate a grounded answer with source passages.");
  }

  const visibleDocuments = useMemo(() => {
    return items.filter((document) => {
      const matchesRisk =
        riskFilter === "all" ||
        document.summary.risks.some((risk) => risk.severity === riskFilter);
      const matchesStatus =
        statusFilter === "all" || document.review_status === statusFilter;
      const search = documentSearch.trim().toLowerCase();
      const matchesSearch =
        !search ||
        [document.filename, document.counterparty, document.owner, document.contract_type]
          .some((value) => value.toLowerCase().includes(search));
      return matchesRisk && matchesStatus && matchesSearch;
    });
  }, [documentSearch, scopedItems, riskFilter, statusFilter]);

  const selected = useMemo(
    () => visibleDocuments.find((document) => document.id === selectedId) ?? visibleDocuments[0],
    [selectedId, visibleDocuments],
  );

  const filteredFragments = useMemo(() => {
    if (!selected) return [];
    if (!query.trim()) return selected.fragments.slice(0, 6);
    return selected.fragments.filter((fragment) =>
      fragment.text.toLowerCase().includes(query.toLowerCase()),
    );
  }, [query, selected]);
  const uploadInProgress = busyAction === "upload" || busyAction === "bulk-upload";

  function normalizeUploadFiles(files?: FileList | File[] | null) {
    return Array.from(files ?? []).filter((file) => /\.(pdf|txt)$/i.test(file.name));
  }

  function handleUploadDragOver(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setIsDraggingUpload(true);
  }

  function handleUploadDragLeave(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setIsDraggingUpload(false);
  }

  function handleUploadDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setIsDraggingUpload(false);
    uploadMany(event.dataTransfer.files);
  }


  function syncMetadataDraft(document: DocumentItem | undefined) {
    if (!document) return;
    setMetadataDraft({
      owner: document.owner,
      counterparty: document.counterparty,
      contract_type: document.contract_type,
      effective_date: document.effective_date,
      expiry_date: document.expiry_date,
      renewal_date: document.renewal_date,
    });
  }

  async function runRetrieval() {
    if (!selected || !query.trim()) return;
    const result = selected.id.startsWith("demo-")
      ? {
          query,
          top_k: 3,
          matches: selected.fragments
            .filter((fragment) => fragment.text.toLowerCase().includes(query.toLowerCase().split(/\s+/)[0] ?? ""))
            .slice(0, 3)
            .map((fragment) => ({ fragment, score: 0.82 })),
          context: "Demo retrieval context generated locally.",
        }
      : await retrieveDocumentContext(selected.id, query, 3);
    setRetrieval(result);
  }

  async function askQuestion() {
    if (!question.trim() || !selected) return;
    const currentQuestion = question.trim();
    setBusyAction("question");
    setNotice(null);
    const askedAt = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    // Append the user turn immediately so the history feels responsive.
    setMessages((current) => [...current, { role: "user", content: currentQuestion, timestamp: askedAt }]);

    if (!selected.id.startsWith("demo-")) {
      const replyAt = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

      // Add an empty assistant placeholder that will fill in word-by-word.
      setAnswer("");
      setMessages((current) => [
        ...current,
        { role: "assistant", content: "", citations: [], timestamp: replyAt },
      ]);

      const streamed = await streamDocumentQuestion(
        selected.id,
        currentQuestion,
        // onDelta: append each word chunk to both the live preview and the history entry
        (text) => {
          setAnswer((prev) => prev + text);
          setMessages((current) => {
            const updated = [...current];
            const last = { ...updated[updated.length - 1] };
            last.content = (last.content ?? "") + text;
            updated[updated.length - 1] = last;
            return updated;
          });
        },
        // onCitations: attach source fragments to the history entry once streaming ends
        (streamCitations) => {
          setCitations(streamCitations);
          setMessages((current) => {
            const updated = [...current];
            const last = { ...updated[updated.length - 1] };
            last.citations = streamCitations;
            updated[updated.length - 1] = last;
            return updated;
          });
        },
      );

      if (streamed) {
        addLocalActivity(selected.id, { type: "question", label: "Question asked", detail: currentQuestion });
        setQuestion("");
        setBusyAction(null);
        return;
      }

      // Streaming failed (network error / backend unavailable).
      // Remove the empty placeholder and fall back to the non-streaming /ask endpoint.
      setMessages((current) => current.slice(0, -1));
      setAnswer("Zadaj pytanie o termin wypowiedzenia, płatności albo odpowiedzialność.");

      const payload = await askDocumentQuestion(selected.id, currentQuestion);
      if (payload) {
        setAnswer(payload.answer);
        setCitations(payload.citations ?? []);
        setMessages((current) => [
          ...current,
          { role: "assistant", content: payload.answer, citations: payload.citations ?? [], timestamp: replyAt },
        ]);
        addLocalActivity(selected.id, { type: "question", label: "Question asked", detail: currentQuestion });
        setQuestion("");
        setBusyAction(null);
        return;
      }
    }

    // Demo mode — keyword match against local fragment data (no backend call).
    const hit =
      selected.fragments.find((fragment) =>
        question
          .toLowerCase()
          .split(/\s+/)
          .some((word) => word.length > 3 && fragment.text.toLowerCase().includes(word)),
      ) ?? selected.fragments[0];
    setAnswer(hit ? `Najbardziej pasujący fragment jest na stronie ${hit.page}: ${hit.text}` : "Brak trafienia.");
    setCitations(hit ? [hit] : []);
    setMessages((current) => [
      ...current,
      {
        role: "assistant",
        content: hit ? `Najbardziej pasujący fragment jest na stronie ${hit.page}: ${hit.text}` : "Brak trafienia.",
        citations: hit ? [hit] : [],
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
    addLocalActivity(selected.id, { type: "question", label: "Question asked", detail: currentQuestion });
    setQuestion("");
    setBusyAction(null);
  }

  async function uploadDocument(file?: File) {
    if (!file) return;
    setBusyAction("upload");
    setNotice(null);
    const created = await uploadDocumentRequest(file, userEmail);
    if (!created) {
      setBusyAction(null);
      setNotice({ tone: "error", message: "Upload failed. Try again." });
      return;
    }
    setItems((current) => [created, ...current]);
    setSelectedId(created.id);
    syncMetadataDraft(created);
    setView("document");
    setBusyAction(null);
    setNotice({ tone: "success", message: "Document uploaded." });
  }

  async function uploadMany(files?: FileList | File[] | null) {
    const uploadFiles = normalizeUploadFiles(files);
    if (!uploadFiles.length) {
      setNotice({ tone: "error", message: "Choose PDF or TXT files only." });
      return;
    }
    setBusyAction(uploadFiles.length > 1 ? "bulk-upload" : "upload");
    setNotice(null);
    setUploadProgress({ label: "Preparing upload", detail: `${uploadFiles.length} file(s) selected`, percent: 18 });
    const created = await uploadDocuments(uploadFiles, userEmail);
    setUploadProgress({ label: "Processing documents", detail: "Extracting text, risks and summary", percent: 72 });
    if (!created.length) {
      setBusyAction(null);
      setUploadProgress(null);
      setNotice({ tone: "error", message: "Upload failed. Check that the backend is running and try again." });
      return;
    }
    setItems((current) => [...created, ...current]);
    setSelectedId(created[0].id);
    syncMetadataDraft(created[0]);
    setView("document");
    setBusyAction(null);
    setUploadProgress({ label: "Upload complete", detail: `${created.length} document(s) added`, percent: 100 });
    setNotice({ tone: "success", message: `${created.length} document(s) uploaded.` });
    window.setTimeout(() => setUploadProgress(null), 1200);
  }

  async function uploadVersion(file?: File) {
    if (!file || !selected) return;
    setBusyAction("version");
    setNotice(null);
    if (!selected.id.startsWith("demo-")) {
      const created = await uploadDocumentVersion(selected.id, file);
      if (!created) {
        setBusyAction(null);
        setNotice({ tone: "error", message: "Version upload failed." });
        return;
      }
      setItems((current) => [
        created,
        ...current.map((item) =>
          item.version_group_id === created.version_group_id ? { ...item, is_latest_version: false } : item,
        ),
      ]);
      setSelectedId(created.id);
      syncMetadataDraft(created);
      setBusyAction(null);
      setNotice({ tone: "success", message: "New version uploaded." });
      return;
    }
    const created = {
      ...selected,
      id: `${selected.version_group_id}-v${selected.version_number + 1}`,
      filename: file.name,
      version_number: selected.version_number + 1,
      is_latest_version: true,
      activity: [
        { type: "version", label: "New version uploaded", detail: `Version ${selected.version_number + 1} created.` },
        ...selected.activity,
      ],
    };
    setItems((current) => [
      created,
      ...current.map((item) =>
        item.version_group_id === selected.version_group_id ? { ...item, is_latest_version: false } : item,
      ),
    ]);
    setSelectedId(created.id);
    setBusyAction(null);
    setNotice({ tone: "success", message: "New version uploaded." });
  }

  async function shareDocument() {
    if (!selected || !shareEmail.trim()) return;
    setBusyAction("share");
    setNotice(null);
    if (!selected.id.startsWith("demo-")) {
      const updated = await shareDocumentRequest(selected.id, shareEmail);
      if (updated) {
        setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      } else {
        setNotice({ tone: "error", message: "Sharing failed." });
        setBusyAction(null);
        return;
      }
    } else {
      setItems((current) =>
        current.map((item) =>
          item.id === selected.id
            ? {
                ...item,
                shared_with: [...item.shared_with, shareEmail],
                activity: [
                  { type: "share", label: "Document shared", detail: `Shared with ${shareEmail}.` },
                  ...item.activity,
                ],
              }
            : item,
        ),
      );
    }
    setShareEmail("");
    setBusyAction(null);
    setNotice({ tone: "success", message: "Document shared." });
  }

  async function runComparison() {
    if (!selected || !compareId) return;
    setBusyAction("compare");
    setNotice(null);
    if (!selected.id.startsWith("demo-") && !compareId.startsWith("demo-")) {
      setComparison(await compareDocuments(selected.id, compareId));
      addLocalActivity(selected.id, {
        type: "compare",
        label: "Compared with another contract",
        detail: `Compared with ${items.find((item) => item.id === compareId)?.filename ?? "another document"}.`,
      });
      setBusyAction(null);
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
    addLocalActivity(selected.id, {
      type: "compare",
      label: "Compared with another contract",
      detail: `Compared with ${other?.filename ?? "another document"}.`,
    });
    setBusyAction(null);
  }

  async function generateReport() {
    if (!selected) return;
    setBusyAction("report");
    setNotice(null);
    if (!selected.id.startsWith("demo-")) {
      const nextReport = await fetchReport(selected.id);
      setReport(nextReport);
      setBusyAction(null);
      setNotice(nextReport ? { tone: "success", message: "Report generated." } : { tone: "error", message: "Report generation failed." });
      return;
    }
    const riskLines = selected.summary.risks.length
      ? selected.summary.risks
          .map((risk) => `- **${risk.title}** (${risk.severity}) — ${risk.explanation}`)
          .join("\n")
      : "- No material risks detected.";
    const suggestionLines = selected.summary.suggestions.length
      ? selected.summary.suggestions
          .map(
            (suggestion) =>
              `- **${suggestion.title}** — ${suggestion.rationale}\n  - Suggested text: \`${suggestion.proposed_text}\``,
          )
          .join("\n")
      : "- No suggested edits.";
    const missingClauseLines = selected.summary.missing_clauses.length
      ? selected.summary.missing_clauses
          .map((clause) => `- **${clause.title}** ? ${clause.why_it_matters}`)
          .join("\n")
      : "- No expected clauses missing.";
    const passageLines = selected.fragments
      .slice(0, 3)
      .map((fragment) => `- Page ${fragment.page}: ${fragment.text}`)
      .join("\n");
    setReport({
      filename: selected.filename,
      markdown: `# Contract Review Report

## Document
${selected.filename}

## Executive summary
${selected.summary.summary}

## Risk score
${selected.summary.overall_score}/100

## Key risks
${riskLines}

## Suggested edits
${suggestionLines}

## Missing clauses
${missingClauseLines}

## Supporting passages
${passageLines}`,
    });
    setBusyAction(null);
    setNotice({ tone: "success", message: "Report generated." });
  }

  async function addComment() {
    if (!selected || !commentBody.trim()) return;
    setBusyAction("comment");
    setNotice(null);
    if (!selected.id.startsWith("demo-")) {
      const updated = await addDocumentComment(selected.id, email || "reviewer@local", commentBody);
      if (updated) {
        setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      } else {
        setNotice({ tone: "error", message: "Comment could not be saved." });
        setBusyAction(null);
        return;
      }
    } else {
      setItems((current) =>
        current.map((item) =>
          item.id === selected.id
            ? {
                ...item,
                comments: [{ author: email || "reviewer@local", body: commentBody }, ...item.comments],
                activity: [
                  { type: "comment", label: "Comment added", detail: commentBody },
                  ...item.activity,
                ],
              }
            : item,
        ),
      );
    }
    setCommentBody("");
    setBusyAction(null);
    setNotice({ tone: "success", message: "Comment added." });
  }

  async function updateReviewStatus(status: ReviewStatus) {
    if (!selected) return;
    setBusyAction("status");
    setNotice(null);
    if (!selected.id.startsWith("demo-")) {
      const updated = await updateDocumentStatus(selected.id, status);
      if (updated) {
        setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      } else {
        setNotice({ tone: "error", message: "Status update failed." });
      }
      setBusyAction(null);
      return;
    }
    setItems((current) =>
      current.map((item) =>
        item.id === selected.id
          ? {
              ...item,
              review_status: status,
              activity: [
                { type: "status", label: "Review status updated", detail: `Status changed to ${status}.` },
                ...item.activity,
              ],
            }
          : item,
      ),
    );
    setBusyAction(null);
    setNotice({ tone: "success", message: "Review status updated." });
  }

  async function saveMetadata() {
    if (!selected) return;
    setBusyAction("metadata");
    setNotice(null);
    if (!selected.id.startsWith("demo-")) {
      const updated = await saveDocumentMetadata(selected.id, metadataDraft);
      if (updated) {
        setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      } else {
        setNotice({ tone: "error", message: "Metadata save failed." });
      }
      setBusyAction(null);
      return;
    }
    setItems((current) =>
      current.map((item) =>
        item.id === selected.id
          ? {
              ...item,
              ...metadataDraft,
              activity: [
                { type: "metadata", label: "Metadata updated", detail: "Contract profile updated." },
                ...item.activity,
              ],
            }
          : item,
      ),
    );
    setBusyAction(null);
    setNotice({ tone: "success", message: "Metadata saved." });
  }

  function downloadReport() {
    if (!report) return;
    const blob = new Blob([report.markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${report.filename.replace(/\.[^.]+$/, "")}-report.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function addLocalActivity(documentId: string, activity: DocumentItem["activity"][number]) {
    setItems((current) =>
      current.map((item) =>
        item.id === documentId ? { ...item, activity: [activity, ...item.activity] } : item,
      ),
    );
  }

  async function archiveDocument() {
    if (!selected) return;
    setBusyAction("delete");
    setNotice(null);
    const deleted = selected.id.startsWith("demo-") ? true : await deleteDocument(selected.id);
    if (!deleted) {
      setBusyAction(null);
      setNotice({ tone: "error", message: "Document could not be archived." });
      return;
    }
    setItems((current) => {
      const next = current.filter((item) => item.id !== selected.id);
      setSelectedId(next[0]?.id ?? "");
      if (next[0]) syncMetadataDraft(next[0]);
      return next;
    });
    setMessages([]);
    setCitations([]);
    setAnswer("Ask a question to generate a grounded answer with source passages.");
    setBusyAction(null);
    setNotice({ tone: "success", message: "Document archived." });
  }

  if (!isLoggedIn) {
    return (
      <main className="min-h-screen bg-mist px-5 py-8">
        <section className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl items-center gap-8 lg:grid-cols-[1.05fr_0.95fr]">
          <div>
            <div className="mb-5 inline-flex rounded-full bg-white px-4 py-2 text-sm font-medium text-slate-600 shadow-sm">
              AI contract review workspace - local-first RAG-ready architecture
            </div>
            <h1 className="max-w-3xl text-5xl font-semibold tracking-[-0.04em] text-slate-950 md:text-6xl">
              Review contracts faster with traceable AI assistance.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600">
              LuminaClause helps teams upload agreements, find risky clauses, ask document-grounded questions,
              compare revisions, and keep review decisions visible before human approval.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a href="#signin" className="rounded-2xl bg-slate-900 px-5 py-3 font-medium text-white shadow-panel">
                Try local demo
              </a>
              <a href="https://github.com/amanda0706/AI-Documents-Chat" className="rounded-2xl border border-line bg-white px-5 py-3 font-medium text-slate-800">
                View GitHub
              </a>
            </div>
            <div className="mt-8 grid max-w-2xl gap-3 sm:grid-cols-3">
              {[
                ["Risk scoring", "Clause-level risk signals and suggested safer wording."],
                ["Grounded Q&A", "Answers stay tied to extracted source fragments."],
                ["Version compare", "See commercial changes between contract versions."],
              ].map(([title, body]) => (
                <div key={title} className="rounded-3xl bg-white p-4 shadow-sm">
                  <p className="font-semibold text-slate-950">{title}</p>
                  <p className="mt-2 text-sm leading-6 text-slate-500">{body}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-5">
            <div className="overflow-hidden rounded-[30px] border border-white bg-white p-3 shadow-panel">
              <img
                src="/screenshots/dashboard.png"
                alt="LuminaClause dashboard preview"
                className="h-auto w-full rounded-[22px] border border-line object-cover"
              />
            </div>
            <section id="signin" className="rounded-[28px] bg-white p-6 shadow-panel">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-400">Local auth demo</p>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight">Sign in or create a local workspace</h2>
              <p className="mt-2 leading-7 text-slate-600">
                This portfolio build uses local email sessions to simulate authentication, document ownership, and the future auth provider seam.
              </p>
              <div className="mt-5 grid grid-cols-2 gap-2 rounded-2xl bg-slate-50 p-1 text-sm font-medium">
                {(["login", "register"] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setAuthMode(mode)}
                    className={`rounded-xl px-3 py-2 ${authMode === mode ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}
                  >
                    {mode === "login" ? "Login" : "Register"}
                  </button>
                ))}
              </div>
              <input
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                onKeyDown={(e) => e.key === "Enter" && completeAuth()}
                placeholder="anna@firma.pl"
                type="email"
                autoComplete="email"
                className="mt-5 w-full rounded-2xl border border-line px-4 py-3 outline-none"
              />
              <input
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                onKeyDown={(e) => e.key === "Enter" && completeAuth()}
                placeholder="Password (min 6 chars)"
                type="password"
                autoComplete={authMode === "register" ? "new-password" : "current-password"}
                className="mt-2 w-full rounded-2xl border border-line px-4 py-3 outline-none"
              />
              <button
                onClick={completeAuth}
                className="mt-3 w-full rounded-2xl bg-slate-900 px-4 py-3 font-medium text-white"
              >
                {authMode === "register" ? "Create workspace" : "Continue to dashboard"}
              </button>
              <p className="mt-3 text-center text-xs text-slate-400">
                Local demo — credentials stored on this device only.
              </p>
            </section>
          </div>
        </section>
      </main>
    );
  }

  if (!items.length) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-mist p-5">
        <section className="max-w-2xl rounded-[28px] bg-white p-8 shadow-panel">
          <h1 className="text-3xl font-semibold tracking-tight">Start with your first contract</h1>
          <p className="mt-4 leading-7 text-slate-600">
            Upload a PDF or TXT file to generate a summary, inspect risks, ask questions, and compare revisions.
            Cloud AI is only called when you have explicitly set <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">ANALYSIS_PROVIDER=claude</code> in <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">backend/.env</code>.
          </p>

          {/* Upload zone */}
          <div
            onDragOver={handleUploadDragOver}
            onDragLeave={handleUploadDragLeave}
            onDrop={handleUploadDrop}
            className={`mt-6 rounded-[24px] border border-dashed p-5 transition ${
              isDraggingUpload ? "border-blue-500 bg-blue-50" : "border-line bg-slate-50"
            }`}
          >
            <p className="font-medium text-slate-900">Drag & drop PDF/TXT files here</p>
            <p className="mt-1 text-sm text-slate-500">or use the upload button below. Multiple files are supported.</p>
            {uploadProgress && (
              <div className="mt-4">
                <div className="flex justify-between text-xs font-medium text-slate-500">
                  <span>{uploadProgress.label}</span>
                  <span>{uploadProgress.percent}%</span>
                </div>
                <div className="mt-2 h-2 rounded-full bg-white">
                  <div className="h-2 rounded-full bg-accent transition-all" style={{ width: `${uploadProgress.percent}%` }} />
                </div>
                <p className="mt-2 text-xs text-slate-500">{uploadProgress.detail}</p>
              </div>
            )}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <label className="cursor-pointer rounded-2xl bg-accent px-5 py-3 font-medium text-white">
              {uploadInProgress ? "Uploading..." : "Upload document"}
              <input type="file" accept=".pdf,.txt" multiple className="hidden" onChange={(event) => uploadMany(event.target.files)} />
            </label>
            <button
              onClick={() => {
                setItems(demoDocuments);
                setSelectedId(demoDocuments[0]?.id ?? "");
              }}
              className="rounded-2xl bg-slate-900 px-5 py-3 font-medium text-white"
            >
              Load demo data
            </button>
          </div>

          {/* Safe sample files guide */}
          <div className="mt-6 rounded-2xl border border-line bg-slate-50 p-5">
            <div className="mb-3 flex items-center gap-2">
              <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
                Synthetic · safe for demo
              </span>
              <span className="text-xs text-slate-500">No real contracts. No data sent to cloud unless you choose.</span>
            </div>
            <p className="mb-3 text-sm font-medium text-slate-700">
              Ready-to-upload sample contracts in <code className="rounded bg-white px-1 py-0.5 text-xs">samples/</code>:
            </p>
            <ul className="space-y-2 text-sm text-slate-600">
              {[
                ["master-services-agreement.txt", "MSA — net-60 payment, 90-day termination, liability cap, auto-renewal. High risk score."],
                ["supplier-agreement.txt",        "Supplier agreement — net-30 payment, capped liability with exceptions, 30-day notice."],
                ["nda-mutual.txt",                "Mutual NDA — confidentiality obligations, 3-year survival, governing law, arbitration."],
              ].map(([file, desc]) => (
                <li key={file} className="flex gap-2">
                  <code className="mt-0.5 shrink-0 rounded bg-white px-1.5 py-0.5 text-xs text-slate-700">{file}</code>
                  <span>{desc}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-slate-400">
              Upload all three to try comparison, risk scoring, and grounded Q&A in one go.
            </p>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-mist p-5">
      {notice && (
        <div className={`mx-auto mb-5 max-w-[1440px] rounded-2xl px-4 py-3 text-sm font-medium ${
          notice.tone === "success" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
        }`}>
          {notice.message}
        </div>
      )}
      <div className="mx-auto grid max-w-[1440px] grid-cols-[250px_minmax(0,1fr)] gap-5">
        <aside className="rounded-[28px] bg-white p-5 shadow-panel">
          <div className="mb-3 text-2xl font-semibold tracking-tight">LuminaClause</div>
          <AiProviderBadge status={providerStatus} />
          <div className="mt-1.5" />
          <StorageBackendBadge status={storageStatus} />
          <div className="mb-5" />
          <div className="mb-3 rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">{email}</div>
          <button onClick={signOut} className="mb-5 w-full rounded-2xl border border-line px-4 py-3 text-sm font-medium text-slate-600">Sign out</button>
          <div
            onDragOver={handleUploadDragOver}
            onDragLeave={handleUploadDragLeave}
            onDrop={handleUploadDrop}
            className={`mb-4 rounded-2xl border border-dashed p-3 text-center text-xs transition ${
              isDraggingUpload ? "border-blue-500 bg-blue-50 text-blue-700" : "border-line bg-slate-50 text-slate-500"
            }`}
          >
            Drop PDF/TXT here
          </div>
          <label className="mb-3 block cursor-pointer rounded-2xl bg-accent px-4 py-3 text-center text-sm font-medium text-white">
            {uploadInProgress ? "Uploading..." : "Upload document"}
            <input type="file" accept=".pdf,.txt" multiple className="hidden" onChange={(event) => uploadMany(event.target.files)} />
          </label>
          {uploadProgress && (
            <div className="mb-6 rounded-2xl bg-slate-50 p-3 text-xs text-slate-600">
              <div className="flex justify-between font-medium">
                <span>{uploadProgress.label}</span>
                <span>{uploadProgress.percent}%</span>
              </div>
              <div className="mt-2 h-2 rounded-full bg-white">
                <div className="h-2 rounded-full bg-accent transition-all" style={{ width: `${uploadProgress.percent}%` }} />
              </div>
              <p className="mt-2">{uploadProgress.detail}</p>
            </div>
          )}
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
          <input
            value={documentSearch}
            onChange={(event) => setDocumentSearch(event.target.value)}
            placeholder="Search contracts"
            className="mb-4 w-full rounded-2xl border border-line px-4 py-3 text-sm outline-none"
          />
          <div className="mb-4 flex flex-wrap gap-2">
            {[
              ["all", "All"],
              ["high", "High"],
              ["medium", "Medium"],
              ["low", "Low"],
            ].map(([key, label]) => (
              <button
                key={key}
                onClick={() => setRiskFilter(key as RiskFilter)}
                className={`rounded-full px-3 py-1 text-xs font-medium ${
                  riskFilter === key ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="space-y-2">
            {visibleDocuments.map((document) => (
              <button
                key={document.id}
                onClick={() => {
                  setSelectedId(document.id);
                  syncMetadataDraft(document);
                }}
                className={`w-full rounded-2xl px-4 py-3 text-left text-sm ${
                  document.id === selected?.id ? "bg-blue-50 text-slate-900" : "bg-slate-50 text-slate-700"
                }`}
              >
                <div className="font-medium">{document.filename}</div>
                <div className="mt-1 text-xs opacity-70">{document.page_count} pages</div>
              </button>
            ))}
            {!visibleDocuments.length && (
              <p className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-500">
                No documents with this risk level.
              </p>
            )}
          </div>
        </aside>

        <section className="space-y-5">
          {view === "overview" && <Overview stats={scopedStats} documents={visibleDocuments} deadlines={deadlines} />}
          {view === "document" && selected && (
            <DocumentWorkspace
              selected={selected}
              query={query}
              setQuery={setQuery}
              retrieval={retrieval}
              runRetrieval={runRetrieval}
              fragments={filteredFragments}
              question={question}
              setQuestion={setQuestion}
              answer={answer}
              citations={citations}
              messages={messages}
              askQuestion={askQuestion}
              shareEmail={shareEmail}
              setShareEmail={setShareEmail}
              shareDocument={shareDocument}
              commentBody={commentBody}
              setCommentBody={setCommentBody}
              addComment={addComment}
              updateReviewStatus={updateReviewStatus}
              metadataDraft={metadataDraft}
              setMetadataDraft={setMetadataDraft}
              saveMetadata={saveMetadata}
              generateReport={generateReport}
              downloadReport={downloadReport}
              report={report}
              uploadVersion={uploadVersion}
              busyAction={busyAction}
              statusFilter={statusFilter}
              setStatusFilter={setStatusFilter}
              clearMessages={() => {
                setMessages([]);
                setAnswer("Ask a question to generate a grounded answer with source passages.");
                setCitations([]);
              }}
              archiveDocument={archiveDocument}
              processingInfo={processingInfo}
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

function Overview({ stats, documents, deadlines }: { stats: DashboardStats; documents: DocumentItem[]; deadlines: DeadlineItem[] }) {
  const reviewQueue = documents
    .filter((document) => document.review_status !== "approved")
    .sort((left, right) => left.summary.overall_score - right.summary.overall_score);
  const owners = countBy(documents, (document) => document.owner || "Unassigned");
  const contractTypes = countBy(documents, (document) => document.contract_type || "Uncategorized");
  const priorityQueue = [...documents]
    .map((document) => ({
      document,
      score:
        (100 - document.summary.overall_score) +
        document.summary.risks.length * 10 +
        (document.review_status !== "approved" ? 15 : 0),
    }))
    .sort((left, right) => right.score - left.score)
    .slice(0, 3);

  return (
    <>
      <div className="grid grid-cols-4 gap-5 xl:grid-cols-8">
        {[
          ["Documents", stats.total_documents],
          ["High risk", stats.high_risk_documents],
          ["Average score", stats.average_score],
          ["Shared", stats.shared_documents],
          ["In review", stats.pending_review_documents],
          ["Approved", stats.approved_documents],
          ["Expiring soon", stats.expiring_soon_documents],
          ["Renewal due", stats.renewal_due_documents],
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
      <div className="grid gap-5 xl:grid-cols-2">
        <div className="rounded-[28px] bg-white p-6 shadow-panel">
          <h2 className="text-xl font-semibold">Portfolio insights</h2>
          <div className="mt-5 space-y-4">
            <InsightBlock title="By owner" items={owners} />
            <InsightBlock title="By contract type" items={contractTypes} />
          </div>
        </div>
        <div className="rounded-[28px] bg-white p-6 shadow-panel">
          <h2 className="text-xl font-semibold">Attention score</h2>
          <div className="mt-5 space-y-3">
            {priorityQueue.map(({ document, score }) => (
              <div key={document.id} className="flex items-center justify-between rounded-2xl bg-slate-50 p-4">
                <div>
                  <div className="font-medium">{document.filename}</div>
                  <div className="text-sm text-slate-500">
                    {document.owner || "Unassigned"} · {reviewStatusLabels[document.review_status]}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm text-slate-400">Priority</div>
                  <div className="text-2xl font-semibold">{score}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="rounded-[28px] bg-white p-6 shadow-panel">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Upcoming deadlines</h2>
          <span className="text-sm text-slate-400">{deadlines.length} within 60 days</span>
        </div>
        <div className="mt-5 space-y-3">
          {deadlines.length ? deadlines.map((deadline) => (
            <div key={`${deadline.document_id}-${deadline.kind}`} className="flex items-center justify-between rounded-2xl bg-slate-50 p-4">
              <div>
                <div className="font-medium">{deadline.filename}</div>
                <div className="text-sm text-slate-500">
                  {deadline.kind === "renewal" ? "Renewal" : "Expiry"} · {deadline.due_date}
                </div>
              </div>
              <div className="text-sm font-medium text-amber-700">
                {deadline.days_remaining} days left
              </div>
            </div>
          )) : <p className="text-sm text-slate-500">No deadlines in the next 60 days.</p>}
        </div>
      </div>
      <div className="rounded-[28px] bg-white p-6 shadow-panel">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Review queue</h2>
          <span className="text-sm text-slate-400">{reviewQueue.length} awaiting attention</span>
        </div>
        <div className="mt-5 space-y-3">
          {reviewQueue.length ? reviewQueue.map((document) => (
            <div key={document.id} className="flex items-center justify-between rounded-2xl bg-slate-50 p-4">
              <div>
                <div className="font-medium">{document.filename}</div>
                <div className="text-sm text-slate-500">
                  {reviewStatusLabels[document.review_status]} · score {document.summary.overall_score}
                </div>
              </div>
              <div className="text-sm text-slate-500">
                {document.summary.risks.length} risks ? {document.owner || "Unassigned"}
              </div>
            </div>
          )) : <p className="text-sm text-slate-500">Everything is approved.</p>}
        </div>
      </div>
    </>
  );
}

function countBy(documents: DocumentItem[], selector: (document: DocumentItem) => string) {
  return Object.entries(
    documents.reduce<Record<string, number>>((counts, document) => {
      const key = selector(document);
      counts[key] = (counts[key] ?? 0) + 1;
      return counts;
    }, {}),
  );
}

function InsightBlock({ title, items }: { title: string; items: [string, number][] }) {
  return (
    <div>
      <p className="text-sm font-medium text-slate-500">{title}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {items.map(([label, value]) => (
          <span key={label} className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700">
            {label} · {value}
          </span>
        ))}
      </div>
    </div>
  );
}

function DocumentWorkspace(props: {
  selected: DocumentItem;
  query: string;
  setQuery: (value: string) => void;
  retrieval: RetrievalResult | null;
  runRetrieval: () => void;
  fragments: DocumentItem["fragments"];
  question: string;
  setQuestion: (value: string) => void;
  answer: string;
  citations: DocumentItem["fragments"];
  messages: ChatMessage[];
  askQuestion: () => void;
  shareEmail: string;
  setShareEmail: (value: string) => void;
  shareDocument: () => void;
  commentBody: string;
  setCommentBody: (value: string) => void;
  addComment: () => void;
  updateReviewStatus: (status: DocumentItem["review_status"]) => void;
  metadataDraft: MetadataDraft;
  setMetadataDraft: (value: MetadataDraft) => void;
  saveMetadata: () => void;
  generateReport: () => void;
  downloadReport: () => void;
  report: ReportResult | null;
  uploadVersion: (file?: File) => void;
  busyAction: string | null;
  statusFilter: StatusFilter;
  setStatusFilter: (value: StatusFilter) => void;
  clearMessages: () => void;
  archiveDocument: () => void;
  processingInfo: ProcessingInfo | null;
}) {
  const { selected } = props;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_360px] gap-5">
      <section className="rounded-[28px] bg-white p-6 shadow-panel">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <p className="text-sm text-slate-400">Current document</p>
            <h1 className="text-2xl font-semibold tracking-tight">{selected.filename}</h1>
            <p className="mt-1 text-sm text-slate-500">
              Version {selected.version_number} {selected.is_latest_version ? "· latest" : ""}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Extraction: {selected.ocr_applied ? "OCR" : "native text"}
            </p>
          </div>
          <div className="flex gap-2">
            <input value={props.query} onChange={(event) => props.setQuery(event.target.value)} placeholder="Search fragments" className="w-64 rounded-2xl border border-line px-4 py-3 text-sm outline-none" />
            <button onClick={props.runRetrieval} className="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white">Retrieve</button>
          </div>
        </div>
        <div className="space-y-4">
          {props.fragments.map((fragment) => (
            <DocumentFragmentCard
              key={fragment.id}
              fragment={fragment}
              risks={selected.summary.risks}
            />
          ))}
        </div>
      </section>
      <aside className="space-y-5">
        <Panel title="AI Summary">
          <p className="leading-7 text-slate-700">{selected.summary.summary}</p>
        </Panel>
        <Panel title="Processing details">
          {props.processingInfo ? (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-slate-500">Extraction</dt>
              <dd className="text-right font-medium">{props.processingInfo.ocr_applied ? "OCR" : "Native text"}</dd>
              <dt className="text-slate-500">Pages</dt>
              <dd className="text-right font-medium">{props.processingInfo.page_count}</dd>
              <dt className="text-slate-500">Fragments</dt>
              <dd className="text-right font-medium">{props.processingInfo.fragment_count}</dd>
              <dt className="text-slate-500">Avg chunk</dt>
              <dd className="text-right font-medium">{props.processingInfo.avg_fragment_length.toLocaleString()} chars</dd>
              <dt className="text-slate-500">Max chunk</dt>
              <dd className="text-right font-medium">{props.processingInfo.max_fragment_length.toLocaleString()} chars</dd>
              <dt className="text-slate-500">Chunking</dt>
              <dd className="text-right font-medium capitalize">{props.processingInfo.chunking_strategy}</dd>
              <dt className="text-slate-500">Cleaning</dt>
              <dd className="text-right font-medium text-emerald-600">{props.processingInfo.cleaning_applied ? "Applied" : "None"}</dd>
            </dl>
          ) : (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-4 animate-pulse rounded bg-slate-100" />
              ))}
            </div>
          )}
        </Panel>
        <Panel title="Semantic retrieval">
          <p className="mb-3 text-sm leading-6 text-slate-500">Local RAG-style context search. Later this can be swapped for embeddings + pgvector.</p>
          {props.retrieval?.matches.length ? (
            <div className="space-y-3">
              {props.retrieval.matches.map((match) => (
                <div key={match.fragment.id} className="rounded-2xl bg-blue-50 p-4 text-sm leading-6 text-slate-700">
                  <div className="mb-1 flex items-center justify-between text-xs font-semibold uppercase tracking-[0.14em] text-blue-600">
                    <span>Page {match.fragment.page}</span>
                    <span>{Math.round(match.score * 100)}%</span>
                  </div>
                  {match.fragment.text}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm leading-6 text-slate-500">Type a phrase above and click Retrieve to inspect the source context.</p>
          )}
        </Panel>

        <Panel title="Contract metadata">
          <div className="space-y-3">
            <input value={props.metadataDraft.owner} onChange={(event) => props.setMetadataDraft({ ...props.metadataDraft, owner: event.target.value })} placeholder="Owner / assignee" className="w-full rounded-2xl border border-line px-4 py-3 text-sm outline-none" />
            <input value={props.metadataDraft.counterparty} onChange={(event) => props.setMetadataDraft({ ...props.metadataDraft, counterparty: event.target.value })} placeholder="Counterparty" className="w-full rounded-2xl border border-line px-4 py-3 text-sm outline-none" />
            <input value={props.metadataDraft.contract_type} onChange={(event) => props.setMetadataDraft({ ...props.metadataDraft, contract_type: event.target.value })} placeholder="Contract type" className="w-full rounded-2xl border border-line px-4 py-3 text-sm outline-none" />
            <input type="date" value={props.metadataDraft.effective_date} onChange={(event) => props.setMetadataDraft({ ...props.metadataDraft, effective_date: event.target.value })} className="w-full rounded-2xl border border-line px-4 py-3 text-sm outline-none" />
            <input type="date" value={props.metadataDraft.expiry_date} onChange={(event) => props.setMetadataDraft({ ...props.metadataDraft, expiry_date: event.target.value })} className="w-full rounded-2xl border border-line px-4 py-3 text-sm outline-none" />
            <input type="date" value={props.metadataDraft.renewal_date} onChange={(event) => props.setMetadataDraft({ ...props.metadataDraft, renewal_date: event.target.value })} className="w-full rounded-2xl border border-line px-4 py-3 text-sm outline-none" />
          </div>
          <button disabled={props.busyAction === "metadata"} onClick={props.saveMetadata} className="mt-3 w-full rounded-2xl border border-line px-4 py-3 text-sm font-medium disabled:opacity-60">
            {props.busyAction === "metadata" ? "Saving..." : "Save metadata"}
          </button>
        </Panel>
        <Panel title="Review status">
          <div className="mb-3 inline-flex rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
            {reviewStatusLabels[selected.review_status]}
          </div>
          <div className="mb-4 flex flex-wrap gap-2">
            {[
              ["all", "All status"],
              ["draft", "Draft"],
              ["in_review", "In review"],
              ["approved", "Approved"],
            ].map(([key, label]) => (
              <button
                key={key}
                onClick={() => props.setStatusFilter(key as StatusFilter)}
                className={`rounded-full px-3 py-1 text-xs font-medium ${
                  props.statusFilter === key ? "bg-blue-600 text-white" : "bg-blue-50 text-blue-700"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-3 gap-2">
            {(["draft", "in_review", "approved"] as const).map((status) => (
              <button
                key={status}
                disabled={props.busyAction === "status"}
                onClick={() => props.updateReviewStatus(status)}
                className={`rounded-2xl px-3 py-2 text-xs font-medium ${
                  selected.review_status === status ? "bg-slate-900 text-white" : "bg-slate-50 text-slate-600"
                }`}
              >
                {reviewStatusLabels[status]}
              </button>
            ))}
          </div>
        </Panel>
        <Panel title={`Risk score · ${selected.summary.overall_score}/100`}>
          <div className="space-y-3">
            {selected.summary.risks.map((risk) => <RiskRow key={risk.category} risk={risk} />)}
          </div>
        </Panel>
        <Panel title="Clause playbook">
          <div className="space-y-3">
            {selected.summary.missing_clauses.length ? selected.summary.missing_clauses.map((clause) => (
              <div key={clause.category} className="rounded-2xl bg-amber-50 p-4 text-sm">
                <div className="font-medium text-amber-900">{clause.title} missing</div>
                <p className="mt-1 text-amber-800">{clause.why_it_matters}</p>
                <p className="mt-2 text-xs text-amber-700">Expected signal: {clause.expected_signal}</p>
              </div>
            )) : <p className="text-sm text-slate-500">All expected clause families are present.</p>}
          </div>
        </Panel>
        <Panel title="Ask this contract">
          <div className="mb-4 flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 text-xs text-slate-500">
            <span>{props.messages.length ? `${props.messages.length} message(s) in this review` : "No questions yet"}</span>
            {props.messages.length > 0 && (
              <button onClick={props.clearMessages} className="font-medium text-slate-700 hover:text-slate-950">
                Clear history
              </button>
            )}
          </div>
          <textarea value={props.question} onChange={(event) => props.setQuestion(event.target.value)} placeholder="Ask about payment terms, termination, liability, renewal..." className="min-h-24 w-full rounded-2xl border border-line p-4 text-sm outline-none" />
          <button disabled={props.busyAction === "question"} onClick={props.askQuestion} className="mt-3 w-full rounded-2xl bg-slate-900 px-4 py-3 text-sm font-medium text-white disabled:opacity-60">
            {props.busyAction === "question" ? "Streaming…" : "Ask"}
          </button>
          <div className="mt-4 rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-700">
            <MarkdownText content={props.answer} />
            {props.busyAction === "question" && props.answer !== "" && (
              <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-slate-400" aria-hidden="true" />
            )}
          </div>
        </Panel>
        <Panel title="Conversation history">
          {props.messages.length === 0 ? (
            <p className="text-sm leading-6 text-slate-500">Ask a question to build an auditable Q&A trail for this document.</p>
          ) : (
            <div className="max-h-[520px] space-y-3 overflow-auto pr-1">
              {props.messages.map((message, index) => (
                <article
                  key={`${message.role}-${index}`}
                  className={`rounded-2xl p-4 text-sm leading-6 ${
                    message.role === "user" ? "bg-slate-900 text-white" : "bg-blue-50 text-slate-700"
                  }`}
                >
                  <div className={`mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-[0.14em] ${message.role === "user" ? "text-slate-300" : "text-blue-500"}`}>
                    <span>{message.role === "user" ? "Question" : "Answer"}</span>
                    <span>{message.timestamp}</span>
                  </div>
                  <MarkdownText content={message.content} />
                  {message.citations?.length ? (
                    <div className="mt-3 space-y-2">
                      {message.citations.map((citation) => (
                        <div key={citation.id} className="rounded-xl border border-blue-100 bg-white/70 p-3 text-xs leading-5 text-slate-600">
                          <div className="mb-1 font-semibold text-slate-500">Source page {citation.page}</div>
                          {citation.text}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          )}
        </Panel>
        <Panel title="Share document">
          <input value={props.shareEmail} onChange={(event) => props.setShareEmail(event.target.value)} placeholder="email współpracownika" className="w-full rounded-2xl border border-line px-4 py-3 text-sm outline-none" />
          <button disabled={props.busyAction === "share"} onClick={props.shareDocument} className="mt-3 w-full rounded-2xl border border-line px-4 py-3 text-sm font-medium disabled:opacity-60">
            {props.busyAction === "share" ? "Sharing..." : "Share"}
          </button>
          <p className="mt-3 text-sm text-slate-500">{selected.shared_with.join(", ") || "Jeszcze nikomu nie udostępniono."}</p>
        </Panel>
        <Panel title="Document version">
          <label className="block cursor-pointer rounded-2xl border border-line px-4 py-3 text-center text-sm font-medium">
            {props.busyAction === "version" ? "Uploading..." : "Upload new version"}
            <input type="file" accept=".pdf,.txt" className="hidden" onChange={(event) => props.uploadVersion(event.target.files?.[0])} />
          </label>
        </Panel>
        <Panel title="Danger zone">
          <p className="text-sm leading-6 text-slate-500">Archive this document from the local workspace when it is no longer part of the review queue.</p>
          <button disabled={props.busyAction === "delete"} onClick={props.archiveDocument} className="mt-3 w-full rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700 disabled:opacity-60">
            {props.busyAction === "delete" ? "Archiving..." : "Archive document"}
          </button>
        </Panel>
        <Panel title="Export report">
          <button disabled={props.busyAction === "report"} onClick={props.generateReport} className="w-full rounded-2xl bg-slate-900 px-4 py-3 text-sm font-medium text-white disabled:opacity-60">
            {props.busyAction === "report" ? "Generating..." : "Generate report"}
          </button>
          {props.report && (
            <>
              <button onClick={props.downloadReport} className="mt-3 w-full rounded-2xl border border-line px-4 py-3 text-sm font-medium">
                Download .md file
              </button>
              <div className="mt-4 max-h-72 overflow-auto rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-700">
                <MarkdownText content={props.report.markdown} />
              </div>
            </>
          )}
        </Panel>
        <Panel title="Review comments">
          <textarea value={props.commentBody} onChange={(event) => props.setCommentBody(event.target.value)} placeholder="Dodaj komentarz do umowy..." className="min-h-24 w-full rounded-2xl border border-line p-4 text-sm outline-none" />
          <button disabled={props.busyAction === "comment"} onClick={props.addComment} className="mt-3 w-full rounded-2xl border border-line px-4 py-3 text-sm font-medium disabled:opacity-60">
            {props.busyAction === "comment" ? "Saving..." : "Add comment"}
          </button>
          <div className="mt-4 space-y-3">
            {selected.comments.length ? selected.comments.map((comment, index) => (
              <div key={`${comment.author}-${index}`} className="rounded-2xl bg-slate-50 p-4 text-sm">
                <div className="font-medium">{comment.author}</div>
                <div className="mt-1 text-slate-600">{comment.body}</div>
              </div>
            )) : <p className="text-sm text-slate-500">No comments yet.</p>}
          </div>
        </Panel>
        <Panel title="Activity">
          <div className="space-y-3">
            {selected.activity.length ? selected.activity.slice(0, 5).map((item, index) => (
              <div key={`${item.type}-${index}`} className="rounded-2xl bg-slate-50 p-4 text-sm">
                <div className="font-medium">{item.label}</div>
                <div className="mt-1 text-slate-500">{item.detail}</div>
              </div>
            )) : <p className="text-sm text-slate-500">No activity yet.</p>}
          </div>
        </Panel>
      </aside>
    </div>
  );
}

function DocumentFragmentCard({
  fragment,
  risks,
}: {
  fragment: DocumentItem["fragments"][number];
  risks: RiskItem[];
}) {
  const matchedRisk = risks.find((risk) =>
    (riskMarkers[risk.category] ?? []).some((marker) =>
      fragment.text.toLowerCase().includes(marker),
    ),
  );

  return (
    <article className="rounded-3xl border border-line bg-slate-50 p-5 leading-7">
      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
        Page {fragment.page}
      </div>
      {matchedRisk && (
        <div className="mb-3 inline-flex rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">
          Risk: {matchedRisk.title}
        </div>
      )}
      {fragment.text}
    </article>
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
          <div className="mb-5 grid gap-3 md:grid-cols-[180px_1fr]">
            <div className="rounded-2xl bg-slate-900 p-4 text-white">
              <p className="text-sm text-slate-300">Changes found</p>
              <p className="mt-2 text-3xl font-semibold">{props.comparison.differences.length}</p>
            </div>
            <div className="rounded-2xl bg-blue-50 p-4">
              <p className="text-sm font-medium text-slate-900">Executive summary</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">{props.comparison.summary}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {props.comparison.differences.map((difference) => (
                  <span key={difference.category} className="rounded-full bg-white px-3 py-1 text-xs font-medium text-slate-600">
                    {difference.category}
                  </span>
                ))}
              </div>
            </div>
          </div>
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

function MarkdownText({ content }: { content: string }) {
  const lines = content.split("\n");
  const blocks: React.ReactNode[] = [];
  let listItems: string[] = [];

  function flushList() {
    if (!listItems.length) return;
    blocks.push(
      <ul key={`list-${blocks.length}`} className="my-3 list-disc space-y-1 pl-5">
        {listItems.map((item, index) => <li key={`${item}-${index}`}>{renderInlineMarkdown(item)}</li>)}
      </ul>,
    );
    listItems = [];
  }

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      return;
    }
    if (trimmed.startsWith("- ")) {
      listItems.push(trimmed.slice(2));
      return;
    }
    flushList();
    if (trimmed.startsWith("### ")) {
      blocks.push(<h3 key={index} className="mt-4 text-base font-semibold text-slate-900">{renderInlineMarkdown(trimmed.slice(4))}</h3>);
      return;
    }
    if (trimmed.startsWith("## ")) {
      blocks.push(<h2 key={index} className="mt-5 text-lg font-semibold text-slate-950">{renderInlineMarkdown(trimmed.slice(3))}</h2>);
      return;
    }
    if (trimmed.startsWith("# ")) {
      blocks.push(<h1 key={index} className="mt-5 text-xl font-semibold text-slate-950">{renderInlineMarkdown(trimmed.slice(2))}</h1>);
      return;
    }
    blocks.push(<p key={index} className="my-2">{renderInlineMarkdown(trimmed)}</p>);
  });
  flushList();

  return <div className="space-y-1">{blocks}</div>;
}

function renderInlineMarkdown(value: string) {
  const parts = value.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index} className="font-semibold text-slate-950">{part.slice(2, -2)}</strong>;
    }
    return <span key={index}>{part}</span>;
  });
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-[28px] bg-white p-5 shadow-panel">
      <p className="mb-3 text-sm text-slate-400">{title}</p>
      {children}
    </section>
  );
}

const providerBadgeStyles: Record<string, string> = {
  local:        "bg-slate-100 text-slate-600",
  claude:       "bg-violet-100 text-violet-700",
  openai:       "bg-emerald-100 text-emerald-700",
  unavailable:  "bg-amber-50 text-amber-600",
};

const providerLabels: Record<string, string> = {
  local:       "AI mode: Local",
  claude:      "AI mode: Claude",
  openai:      "AI mode: OpenAI",
  unavailable: "AI mode: unavailable",
};

function AiProviderBadge({ status }: { status: ProviderStatus }) {
  const key = status.provider in providerBadgeStyles ? status.provider : "unavailable";
  const label = providerLabels[key] ?? "AI mode: unavailable";
  const style = providerBadgeStyles[key];
  return (
    <div
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${style}`}
      title={status.cloud_enabled ? `Model: ${status.model}` : "Running fully on-device"}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${status.cloud_enabled ? "bg-violet-500" : "bg-slate-400"}`} />
      {label}
    </div>
  );
}

const storageBadgeStyles: Record<string, string> = {
  json:        "bg-slate-100 text-slate-600",
  postgres:    "bg-sky-100 text-sky-700",
  unavailable: "bg-amber-50 text-amber-600",
};

const storageLabels: Record<string, string> = {
  json:        "Storage: JSON",
  postgres:    "Storage: Postgres",
  unavailable: "Storage: unavailable",
};

function StorageBackendBadge({ status }: { status: StorageStatus }) {
  const key = status.storage_backend in storageBadgeStyles ? status.storage_backend : "unavailable";
  const label = storageLabels[key] ?? "Storage: unavailable";
  const style = storageBadgeStyles[key];
  const dot =
    key === "postgres"
      ? status.storage_ready
        ? "bg-sky-500"
        : "bg-amber-400"
      : key === "json"
      ? "bg-slate-400"
      : "bg-amber-400";
  const title =
    key === "postgres"
      ? status.storage_ready
        ? "PostgreSQL connected"
        : "PostgreSQL unreachable"
      : key === "json"
      ? "Local JSON file storage"
      : "Storage backend unavailable";
  return (
    <div
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${style}`}
      title={title}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {label}
    </div>
  );
}
