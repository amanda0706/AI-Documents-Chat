from backend.app.analyzer import analyze_risks, compare_documents


def test_payment_risk_requires_unfavorable_terms() -> None:
    text = "The supplier shall issue an invoice after delivery. Payment terms are net 30 days."
    categories = {risk.category for risk in analyze_risks(text)}
    assert "payment" not in categories


def test_payment_risk_detects_long_payment_window() -> None:
    text = "Payment terms are net 60 days from receipt of invoice."
    categories = {risk.category for risk in analyze_risks(text)}
    assert "payment" in categories


def test_comparison_returns_full_sentences() -> None:
    differences = compare_documents(
        "Payment terms are net 60 days from receipt of invoice.",
        "Payment terms are net 30 days from receipt of invoice.",
    )
    assert differences[0].left_text == "Payment terms are net 60 days from receipt of invoice."
    assert differences[0].right_text == "Payment terms are net 30 days from receipt of invoice."
