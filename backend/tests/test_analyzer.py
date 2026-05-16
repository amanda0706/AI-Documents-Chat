from backend.app.analyzer import analyze_risks


def test_payment_risk_requires_unfavorable_terms() -> None:
    text = "The supplier shall issue an invoice after delivery. Payment terms are net 30 days."
    categories = {risk.category for risk in analyze_risks(text)}
    assert "payment" not in categories


def test_payment_risk_detects_long_payment_window() -> None:
    text = "Payment terms are net 60 days from receipt of invoice."
    categories = {risk.category for risk in analyze_risks(text)}
    assert "payment" in categories
