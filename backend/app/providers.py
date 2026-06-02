from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Protocol

from .analyzer import (
    analyze_risks,
    answer_question,
    build_suggestions,
    compare_documents,
    detect_language,
    find_missing_clauses,
    overall_score,
    summarize,
)
from .models import DifferenceItem, DocumentSummary


class AnalysisProvider(Protocol):
    name: str

    def summarize_document(self, filename: str, text: str) -> DocumentSummary: ...

    def answer(self, question: str, fragments: list[str]) -> tuple[str, list[str]]: ...

    def compare(self, left_text: str, right_text: str) -> list[DifferenceItem]: ...


@dataclass(frozen=True)
class LocalProvider:
    name: str = "local"

    def summarize_document(self, filename: str, text: str) -> DocumentSummary:
        summary_lines = summarize(text)
        risks = analyze_risks(text)
        return DocumentSummary(
            title=filename,
            summary=" ".join(summary_lines) if summary_lines else "Nie udało się wygenerować streszczenia.",
            highlights=summary_lines,
            risks=risks,
            suggestions=build_suggestions(risks),
            missing_clauses=find_missing_clauses(text),
            language=detect_language(text),
            overall_score=overall_score(risks),
        )

    def answer(self, question: str, fragments: list[str]) -> tuple[str, list[str]]:
        return answer_question(question, fragments)

    def compare(self, left_text: str, right_text: str) -> list[DifferenceItem]:
        return compare_documents(left_text, right_text)


@dataclass(frozen=True)
class ClaudeProvider:
    """Adapter seam for Anthropic Claude. Requires ANTHROPIC_API_KEY at runtime.

    Not active unless ANALYSIS_PROVIDER=claude is set with a valid key.
    Uses retrieved source fragments as context so full documents are not blindly sent.
    """

    name: str = "claude"
    api_key: str = ""
    model: str = "claude-sonnet-4-6"

    def summarize_document(self, filename: str, text: str) -> DocumentSummary:
        # Local fallback for structure; real implementation sends retrieved
        # fragments to the Claude Messages API and parses structured output.
        raise NotImplementedError(
            "ClaudeProvider.summarize_document is a stub. "
            "Implement with anthropic SDK when ready."
        )

    def answer(self, question: str, fragments: list[str]) -> tuple[str, list[str]]:
        # Real implementation: POST fragments as context to Claude, return
        # (answer_text, list_of_cited_fragment_texts) to preserve citations.
        raise NotImplementedError(
            "ClaudeProvider.answer is a stub. "
            "Implement with anthropic SDK when ready."
        )

    def compare(self, left_text: str, right_text: str) -> list[DifferenceItem]:
        raise NotImplementedError(
            "ClaudeProvider.compare is a stub. "
            "Implement with anthropic SDK when ready."
        )


@dataclass(frozen=True)
class OpenAIProvider:
    """Adapter seam for OpenAI. Requires OPENAI_API_KEY at runtime.

    Not active unless ANALYSIS_PROVIDER=openai is set with a valid key.
    Uses retrieved source fragments as context so full documents are not blindly sent.
    """

    name: str = "openai"
    api_key: str = ""
    model: str = "gpt-4o"

    def summarize_document(self, filename: str, text: str) -> DocumentSummary:
        raise NotImplementedError(
            "OpenAIProvider.summarize_document is a stub. "
            "Implement with openai SDK when ready."
        )

    def answer(self, question: str, fragments: list[str]) -> tuple[str, list[str]]:
        raise NotImplementedError(
            "OpenAIProvider.answer is a stub. "
            "Implement with openai SDK when ready."
        )

    def compare(self, left_text: str, right_text: str) -> list[DifferenceItem]:
        raise NotImplementedError(
            "OpenAIProvider.compare is a stub. "
            "Implement with openai SDK when ready."
        )


def get_provider() -> AnalysisProvider:
    provider_name = os.getenv("ANALYSIS_PROVIDER", "local").strip().lower()

    if provider_name == "local":
        return LocalProvider()

    if provider_name == "claude":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "ANALYSIS_PROVIDER=claude requires ANTHROPIC_API_KEY to be set. "
                "Set the key or switch back to ANALYSIS_PROVIDER=local."
            )
        model = os.getenv("AI_MODEL", "claude-sonnet-4-6").strip()
        return ClaudeProvider(api_key=api_key, model=model)

    if provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "ANALYSIS_PROVIDER=openai requires OPENAI_API_KEY to be set. "
                "Set the key or switch back to ANALYSIS_PROVIDER=local."
            )
        model = os.getenv("AI_MODEL", "gpt-4o").strip()
        return OpenAIProvider(api_key=api_key, model=model)

    raise ValueError(
        f"Unsupported analysis provider: '{provider_name}'. "
        "Supported values: local, claude, openai."
    )
