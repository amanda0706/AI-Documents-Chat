from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.app.providers import ClaudeProvider, LocalProvider, OpenAIProvider, get_provider


def test_default_provider_is_local(monkeypatch: pytest.MonkeyPatch) -> None:
    # Explicitly clear provider vars so a local backend/.env loaded at startup
    # does not bleed into this assertion.
    monkeypatch.delenv("ANALYSIS_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
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


# ---------------------------------------------------------------------------
# ClaudeProvider method tests — all mocked, no real API key needed
# ---------------------------------------------------------------------------

def _make_claude_response(payload: dict) -> MagicMock:
    """Build a minimal fake anthropic Messages response."""
    content_block = SimpleNamespace(text=json.dumps(payload))
    return SimpleNamespace(content=[content_block])


def _claude_provider() -> ClaudeProvider:
    return ClaudeProvider(api_key="sk-ant-fake", model="claude-sonnet-4-6")


@patch("backend.app.providers.ClaudeProvider._client")
def test_claude_answer_returns_answer_and_citations(mock_client: MagicMock) -> None:
    fragments = [
        "Payment terms are net 60 days from invoice date.",
        "Either party may terminate with 90 days written notice.",
        "Liability is limited to the fees paid in the prior 12 months.",
    ]
    fake_response = _make_claude_response({"answer": "Net 60 days.", "used_indices": [0]})
    mock_client.return_value.messages.create.return_value = fake_response

    provider = _claude_provider()
    answer, cited = provider.answer("What are the payment terms?", fragments)

    assert answer == "Net 60 days."
    assert cited == [fragments[0]]


@patch("backend.app.providers.ClaudeProvider._client")
def test_claude_answer_with_multiple_citations(mock_client: MagicMock) -> None:
    fragments = ["Clause A.", "Clause B.", "Clause C."]
    fake_response = _make_claude_response({"answer": "A and B apply.", "used_indices": [0, 1]})
    mock_client.return_value.messages.create.return_value = fake_response

    provider = _claude_provider()
    answer, cited = provider.answer("What clauses apply?", fragments)

    assert answer == "A and B apply."
    assert cited == [fragments[0], fragments[1]]


@patch("backend.app.providers.ClaudeProvider._client")
def test_claude_answer_with_no_fragments_skips_api(mock_client: MagicMock) -> None:
    provider = _claude_provider()
    answer, cited = provider.answer("Anything?", [])

    mock_client.assert_not_called()
    assert cited == []
    assert "No document content" in answer


@patch("backend.app.providers.ClaudeProvider._client")
def test_claude_answer_out_of_range_indices_are_ignored(mock_client: MagicMock) -> None:
    fragments = ["Only fragment."]
    fake_response = _make_claude_response({"answer": "Found it.", "used_indices": [0, 99]})
    mock_client.return_value.messages.create.return_value = fake_response

    provider = _claude_provider()
    _, cited = provider.answer("Question?", fragments)

    assert cited == [fragments[0]]


@patch("backend.app.providers.ClaudeProvider._client")
def test_claude_answer_handles_malformed_json_gracefully(mock_client: MagicMock) -> None:
    bad_response = SimpleNamespace(content=[SimpleNamespace(text="not json at all")])
    mock_client.return_value.messages.create.return_value = bad_response

    provider = _claude_provider()
    answer, cited = provider.answer("Question?", ["Some fragment."])

    # Should not raise; answer will be empty string, citations empty
    assert isinstance(answer, str)
    assert cited == []


@patch("backend.app.providers.ClaudeProvider._client")
def test_claude_summarize_document_returns_document_summary(mock_client: MagicMock) -> None:
    text = "Payment terms are net 60 days. Either party may terminate with 90 days written notice."
    fake_response = _make_claude_response({
        "summary": "This is a services agreement with net-60 payment terms.",
        "highlights": ["Net 60 payment terms", "90 day termination notice"],
    })
    mock_client.return_value.messages.create.return_value = fake_response

    provider = _claude_provider()
    summary = provider.summarize_document("contract.txt", text)

    assert summary.title == "contract.txt"
    assert summary.summary == "This is a services agreement with net-60 payment terms."
    assert "Net 60 payment terms" in summary.highlights
    # Risks are computed locally — payment risk should be detected
    assert any(r.category == "payment" for r in summary.risks)
    assert summary.overall_score < 100


@patch("backend.app.providers.ClaudeProvider._client")
def test_claude_summarize_falls_back_when_json_malformed(mock_client: MagicMock) -> None:
    bad_response = SimpleNamespace(content=[SimpleNamespace(text="oops not json")])
    mock_client.return_value.messages.create.return_value = bad_response

    provider = _claude_provider()
    text = "Payment terms are net 60 days."
    summary = provider.summarize_document("contract.txt", text)

    # Should still return a valid DocumentSummary using local fallback
    assert summary.title == "contract.txt"
    assert isinstance(summary.summary, str)
    assert isinstance(summary.highlights, list)


@patch("backend.app.providers.ClaudeProvider._client")
def test_claude_compare_returns_difference_items(mock_client: MagicMock) -> None:
    fake_response = _make_claude_response({
        "differences": [
            {
                "category": "payment",
                "left_text": "Payment terms are net 30 days.",
                "right_text": "Payment terms are net 60 days.",
                "impact": "Longer payment cycle in Contract B may affect cash flow.",
            }
        ]
    })
    mock_client.return_value.messages.create.return_value = fake_response

    provider = _claude_provider()
    diffs = provider.compare("net 30 days terms.", "net 60 days terms.")

    assert len(diffs) == 1
    assert diffs[0].category == "payment"
    assert "30" in diffs[0].left_text
    assert "60" in diffs[0].right_text
    assert "cash flow" in diffs[0].impact


@patch("backend.app.providers.ClaudeProvider._client")
def test_claude_compare_handles_malformed_json_gracefully(mock_client: MagicMock) -> None:
    bad_response = SimpleNamespace(content=[SimpleNamespace(text="```\nnot json\n```")])
    mock_client.return_value.messages.create.return_value = bad_response

    provider = _claude_provider()
    diffs = provider.compare("Contract A text.", "Contract B text.")

    assert diffs == []


# ---------------------------------------------------------------------------
# OpenAIProvider method tests — all mocked, no real API key needed
# ---------------------------------------------------------------------------

def _make_openai_response(payload: dict) -> SimpleNamespace:
    """Build a minimal fake openai ChatCompletion response."""
    message = SimpleNamespace(content=json.dumps(payload))
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _openai_provider() -> OpenAIProvider:
    return OpenAIProvider(api_key="sk-fake-key", model="gpt-4o")


@patch("backend.app.providers.OpenAIProvider._client")
def test_openai_answer_returns_answer_and_citations(mock_client: MagicMock) -> None:
    fragments = [
        "Payment terms are net 60 days from invoice date.",
        "Either party may terminate with 90 days written notice.",
        "Liability is limited to the fees paid in the prior 12 months.",
    ]
    fake_response = _make_openai_response({"answer": "Net 60 days.", "used_indices": [0]})
    mock_client.return_value.chat.completions.create.return_value = fake_response

    provider = _openai_provider()
    answer, cited = provider.answer("What are the payment terms?", fragments)

    assert answer == "Net 60 days."
    assert cited == [fragments[0]]


@patch("backend.app.providers.OpenAIProvider._client")
def test_openai_answer_with_multiple_citations(mock_client: MagicMock) -> None:
    fragments = ["Clause A.", "Clause B.", "Clause C."]
    fake_response = _make_openai_response({"answer": "A and B apply.", "used_indices": [0, 1]})
    mock_client.return_value.chat.completions.create.return_value = fake_response

    provider = _openai_provider()
    answer, cited = provider.answer("What clauses apply?", fragments)

    assert answer == "A and B apply."
    assert cited == [fragments[0], fragments[1]]


@patch("backend.app.providers.OpenAIProvider._client")
def test_openai_answer_with_no_fragments_skips_api(mock_client: MagicMock) -> None:
    provider = _openai_provider()
    answer, cited = provider.answer("Anything?", [])

    mock_client.assert_not_called()
    assert cited == []
    assert "No document content" in answer


@patch("backend.app.providers.OpenAIProvider._client")
def test_openai_answer_out_of_range_indices_are_ignored(mock_client: MagicMock) -> None:
    fragments = ["Only fragment."]
    fake_response = _make_openai_response({"answer": "Found it.", "used_indices": [0, 99]})
    mock_client.return_value.chat.completions.create.return_value = fake_response

    provider = _openai_provider()
    _, cited = provider.answer("Question?", fragments)

    assert cited == [fragments[0]]


@patch("backend.app.providers.OpenAIProvider._client")
def test_openai_answer_handles_malformed_json_gracefully(mock_client: MagicMock) -> None:
    bad_message = SimpleNamespace(content="not json at all")
    bad_response = SimpleNamespace(choices=[SimpleNamespace(message=bad_message)])
    mock_client.return_value.chat.completions.create.return_value = bad_response

    provider = _openai_provider()
    answer, cited = provider.answer("Question?", ["Some fragment."])

    assert isinstance(answer, str)
    assert cited == []


@patch("backend.app.providers.OpenAIProvider._client")
def test_openai_summarize_document_returns_document_summary(mock_client: MagicMock) -> None:
    text = "Payment terms are net 60 days. Either party may terminate with 90 days written notice."
    fake_response = _make_openai_response({
        "summary": "This is a services agreement with net-60 payment terms.",
        "highlights": ["Net 60 payment terms", "90 day termination notice"],
    })
    mock_client.return_value.chat.completions.create.return_value = fake_response

    provider = _openai_provider()
    summary = provider.summarize_document("contract.txt", text)

    assert summary.title == "contract.txt"
    assert summary.summary == "This is a services agreement with net-60 payment terms."
    assert "Net 60 payment terms" in summary.highlights
    assert any(r.category == "payment" for r in summary.risks)
    assert summary.overall_score < 100


@patch("backend.app.providers.OpenAIProvider._client")
def test_openai_summarize_falls_back_when_json_malformed(mock_client: MagicMock) -> None:
    bad_message = SimpleNamespace(content="oops not json")
    bad_response = SimpleNamespace(choices=[SimpleNamespace(message=bad_message)])
    mock_client.return_value.chat.completions.create.return_value = bad_response

    provider = _openai_provider()
    text = "Payment terms are net 60 days."
    summary = provider.summarize_document("contract.txt", text)

    assert summary.title == "contract.txt"
    assert isinstance(summary.summary, str)
    assert isinstance(summary.highlights, list)


@patch("backend.app.providers.OpenAIProvider._client")
def test_openai_compare_returns_difference_items(mock_client: MagicMock) -> None:
    fake_response = _make_openai_response({
        "differences": [
            {
                "category": "payment",
                "left_text": "Payment terms are net 30 days.",
                "right_text": "Payment terms are net 60 days.",
                "impact": "Longer payment cycle in Contract B may affect cash flow.",
            }
        ]
    })
    mock_client.return_value.chat.completions.create.return_value = fake_response

    provider = _openai_provider()
    diffs = provider.compare("net 30 days terms.", "net 60 days terms.")

    assert len(diffs) == 1
    assert diffs[0].category == "payment"
    assert "30" in diffs[0].left_text
    assert "60" in diffs[0].right_text
    assert "cash flow" in diffs[0].impact


@patch("backend.app.providers.OpenAIProvider._client")
def test_openai_compare_handles_malformed_json_gracefully(mock_client: MagicMock) -> None:
    bad_message = SimpleNamespace(content="```\nnot json\n```")
    bad_response = SimpleNamespace(choices=[SimpleNamespace(message=bad_message)])
    mock_client.return_value.chat.completions.create.return_value = bad_response

    provider = _openai_provider()
    diffs = provider.compare("Contract A text.", "Contract B text.")

    assert diffs == []


@patch("backend.app.providers.OpenAIProvider._client")
def test_openai_answer_prompt_includes_question(mock_client: MagicMock) -> None:
    """Verify the question text is passed to the API, not silently dropped."""
    fake_response = _make_openai_response({"answer": "Some answer.", "used_indices": []})
    mock_client.return_value.chat.completions.create.return_value = fake_response

    provider = _openai_provider()
    provider.answer("What is the termination clause?", ["Clause text."])

    call_kwargs = mock_client.return_value.chat.completions.create.call_args
    messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][1]
    user_content = next(m["content"] for m in messages if m["role"] == "user")
    assert "What is the termination clause?" in user_content


@patch("backend.app.providers.OpenAIProvider._client")
def test_openai_compare_empty_differences_list(mock_client: MagicMock) -> None:
    fake_response = _make_openai_response({"differences": []})
    mock_client.return_value.chat.completions.create.return_value = fake_response

    provider = _openai_provider()
    diffs = provider.compare("Text A.", "Text B.")

    assert diffs == []
