from backend.app.analyzer import analyze_risks, compare_documents, find_missing_clauses


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


def test_missing_clause_playbook_flags_absent_terms() -> None:
    missing = find_missing_clauses("Payment terms are net 30 days.")
    categories = {item.category for item in missing}

    assert "payment" not in categories
    assert "governing_law" in categories
    assert "confidentiality" in categories
