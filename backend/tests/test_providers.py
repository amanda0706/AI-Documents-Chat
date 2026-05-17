from backend.app.providers import LocalProvider, get_provider


def test_default_provider_is_local() -> None:
    provider = get_provider()
    assert provider.name == "local"


def test_local_provider_builds_document_summary() -> None:
    provider = LocalProvider()
    summary = provider.summarize_document(
        "agreement.txt",
        "Payment terms are net 60 days. Either party may terminate with 90 days written notice.",
    )
    assert summary.title == "agreement.txt"
    assert summary.overall_score < 100
    assert summary.risks
