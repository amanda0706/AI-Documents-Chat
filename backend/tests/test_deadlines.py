from datetime import date, timedelta

from backend.app.deadlines import build_deadlines
from backend.app.models import DocumentDetail, DocumentSummary


def build_document(*, expiry_date: str = "", renewal_date: str = "") -> DocumentDetail:
    return DocumentDetail(
        id="doc-1",
        filename="agreement.txt",
        page_count=1,
        shared_with=[],
        expiry_date=expiry_date,
        renewal_date=renewal_date,
        summary=DocumentSummary(
            title="agreement.txt",
            summary="Summary.",
            highlights=[],
            risks=[],
            suggestions=[],
            language="en",
            overall_score=100,
        ),
        fragments=[],
    )


def test_deadlines_include_dates_within_sixty_days() -> None:
    expiry = (date.today() + timedelta(days=15)).isoformat()
    renewal = (date.today() + timedelta(days=30)).isoformat()
    items = build_deadlines([build_document(expiry_date=expiry, renewal_date=renewal)])

    assert [item.kind for item in items] == ["expiry", "renewal"]


def test_deadlines_ignore_far_future_dates() -> None:
    expiry = (date.today() + timedelta(days=90)).isoformat()
    items = build_deadlines([build_document(expiry_date=expiry)])

    assert items == []
