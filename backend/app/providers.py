from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .analyzer import (
    analyze_risks,
    answer_question,
    build_suggestions,
    compare_documents,
    detect_language,
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
            language=detect_language(text),
            overall_score=overall_score(risks),
        )

    def answer(self, question: str, fragments: list[str]) -> tuple[str, list[str]]:
        return answer_question(question, fragments)

    def compare(self, left_text: str, right_text: str) -> list[DifferenceItem]:
        return compare_documents(left_text, right_text)


def get_provider() -> AnalysisProvider:
    return LocalProvider()
