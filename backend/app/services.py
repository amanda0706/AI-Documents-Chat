from __future__ import annotations

from .deadlines import build_deadlines
from .models import ComparisonResponse, DashboardStats, DocumentDetail, ReportResponse
from .providers import AnalysisProvider


def build_dashboard_stats(documents: list[DocumentDetail]) -> DashboardStats:
    total = len(documents)
    deadlines = build_deadlines(documents)
    return DashboardStats(
        total_documents=total,
        high_risk_documents=sum(
            1 for document in documents if any(risk.severity == "high" for risk in document.summary.risks)
        ),
        average_score=round(sum(document.summary.overall_score for document in documents) / total) if total else 0,
        shared_documents=sum(1 for document in documents if document.shared_with),
        pending_review_documents=sum(1 for document in documents if document.review_status == "in_review"),
        approved_documents=sum(1 for document in documents if document.review_status == "approved"),
        expiring_soon_documents=sum(1 for item in deadlines if item.kind == "expiry"),
        renewal_due_documents=sum(1 for item in deadlines if item.kind == "renewal"),
    )


def build_report(document: DocumentDetail) -> ReportResponse:
    risk_lines = "\n".join(
        f"- **{risk.title}** ({risk.severity}) — {risk.explanation}"
        for risk in document.summary.risks
    ) or "- No material risks detected."
    suggestion_lines = "\n".join(
        f"- **{suggestion.title}** — {suggestion.rationale}\n  - Suggested text: `{suggestion.proposed_text}`"
        for suggestion in document.summary.suggestions
    ) or "- No suggested edits."
    missing_clause_lines = "\n".join(
        f"- **{clause.title}** ? {clause.why_it_matters}"
        for clause in document.summary.missing_clauses
    ) or "- No expected clauses missing."
    passage_lines = "\n".join(
        f"- Page {fragment.page}: {fragment.text}"
        for fragment in document.fragments[:3]
    ) or "- No passages available."
    markdown = f"""# Contract Review Report

## Document
{document.filename}

## Executive summary
{document.summary.summary}

## Risk score
{document.summary.overall_score}/100

## Key risks
{risk_lines}

## Suggested edits
{suggestion_lines}

## Missing clauses
{missing_clause_lines}

## Supporting passages
{passage_lines}
"""
    return ReportResponse(filename=document.filename, markdown=markdown)


def compare_contracts(left: DocumentDetail, right: DocumentDetail, provider: AnalysisProvider) -> ComparisonResponse:
    left_text = "\n".join(fragment.text for fragment in left.fragments)
    right_text = "\n".join(fragment.text for fragment in right.fragments)
    differences = provider.compare(left_text, right_text)
    summary = (
        f"Znaleziono {len(differences)} istotne różnice między dokumentami."
        if differences
        else "Nie wykryto istotnych różnic na podstawie lokalnych reguł."
    )
    return ComparisonResponse(
        left_filename=left.filename,
        right_filename=right.filename,
        summary=summary,
        differences=differences,
    )
