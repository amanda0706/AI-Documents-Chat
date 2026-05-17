from backend.app.models import (
    DocumentDetail,
    DocumentFragment,
    DocumentSummary,
    RiskItem,
)
from backend.app.providers import LocalProvider
from backend.app.services import build_dashboard_stats, build_report, compare_contracts


def build_document(
    *,
    doc_id: str,
    filename: str,
    score: int = 100,
    review_status: str = "draft",
    shared_with: list[str] | None = None,
    risks: list[RiskItem] | None = None,
) -> DocumentDetail:
    return DocumentDetail(
        id=doc_id,
        filename=filename,
        page_count=1,
        shared_with=shared_with or [],
        review_status=review_status,
        summary=DocumentSummary(
            title=filename,
            summary="Summary.",
            highlights=[],
            risks=risks or [],
            suggestions=[],
            missing_clauses=[],
            language="en",
            overall_score=score,
        ),
        fragments=[DocumentFragment(id=f"{doc_id}-1", page=1, text="Payment terms are net 30 days.")],
    )


def test_dashboard_stats_are_built_from_documents() -> None:
    risk = RiskItem(
        category="liability",
        severity="high",
        title="Risk",
        explanation="Risky.",
        recommendation="Fix it.",
        score=25,
    )
    stats = build_dashboard_stats(
        [
            build_document(doc_id="1", filename="a.txt", score=75, review_status="in_review", risks=[risk]),
            build_document(doc_id="2", filename="b.txt", score=95, review_status="approved", shared_with=["a@b.com"]),
        ]
    )

    assert stats.total_documents == 2
    assert stats.high_risk_documents == 1
    assert stats.pending_review_documents == 1
    assert stats.shared_documents == 1


def test_report_contains_contract_sections() -> None:
    report = build_report(build_document(doc_id="1", filename="agreement.txt"))
    assert "# Contract Review Report" in report.markdown
    assert "## Supporting passages" in report.markdown


def test_compare_contracts_delegates_to_provider() -> None:
    left = build_document(doc_id="1", filename="left.txt")
    right = DocumentDetail(
        **{
            **build_document(doc_id="2", filename="right.txt").model_dump(),
            "fragments": [DocumentFragment(id="2-1", page=1, text="Payment terms are net 60 days.")],
        }
    )
    result = compare_contracts(left, right, LocalProvider())
    assert result.left_filename == "left.txt"
    assert result.differences
