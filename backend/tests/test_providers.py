import pytest

from backend.app.providers import ClaudeProvider, LocalProvider, OpenAIProvider, get_provider


def test_default_provider_is_local() -> None:
    provider = get_provider()
    assert provider.name == "local"


def test_provider_can_be_selected_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_PROVIDER", "local")
    assert get_provider().name == "local"


def test_unknown_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_PROVIDER", "future-cloud")
    with pytest.raises(ValueError):
        get_provider()


def test_local_provider_builds_document_summary() -> None:
    provider = LocalProvider()
    summary = provider.summarize_document(
        "agreement.txt",
        "Payment terms are net 60 days. Either party may terminate with 90 days written notice.",
    )
    assert summary.title == "agreement.txt"
    assert summary.overall_score < 100
    assert summary.risks


# --- cloud provider seam tests ---


def test_claude_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_PROVIDER", "claude")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        get_provider()


def test_claude_provider_with_empty_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        get_provider()


def test_claude_provider_instantiates_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    provider = get_provider()
    assert provider.name == "claude"
    assert isinstance(provider, ClaudeProvider)


def test_claude_provider_uses_custom_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("AI_MODEL", "claude-opus-4-7")
    provider = get_provider()
    assert isinstance(provider, ClaudeProvider)
    assert provider.model == "claude-opus-4-7"


def test_openai_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        get_provider()


def test_openai_provider_with_empty_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        get_provider()


def test_openai_provider_instantiates_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    provider = get_provider()
    assert provider.name == "openai"
    assert isinstance(provider, OpenAIProvider)


def test_openai_provider_uses_custom_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("AI_MODEL", "gpt-4-turbo")
    provider = get_provider()
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "gpt-4-turbo"


def test_local_remains_default_when_no_cloud_keys_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANALYSIS_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = get_provider()
    assert provider.name == "local"
    assert isinstance(provider, LocalProvider)
