import pytest
from pydantic import ValidationError

from backend.app.models import MetadataRequest, ReviewStatusRequest, RiskItem


def test_review_status_rejects_unknown_values() -> None:
    with pytest.raises(ValidationError):
        ReviewStatusRequest(status="waiting")


def test_risk_severity_rejects_unknown_values() -> None:
    with pytest.raises(ValidationError):
        RiskItem(
            category="payment",
            severity="critical",
            title="Bad severity",
            explanation="Invalid.",
            recommendation="Fix.",
            score=1,
        )


def test_metadata_dates_require_valid_iso_dates() -> None:
    with pytest.raises(ValidationError):
        MetadataRequest(expiry_date="17-05-2026")

    with pytest.raises(ValidationError):
        MetadataRequest(expiry_date="2026-99-99")


def test_metadata_dates_accept_valid_iso_dates() -> None:
    request = MetadataRequest(expiry_date="2026-05-17")

    assert request.expiry_date == "2026-05-17"
