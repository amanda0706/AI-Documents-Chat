from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
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


_FENCE_RE = re.compile(r"^```[a-z]*\n?|\n?```$")

# Maximum characters sent to Claude per field to keep token costs low.
_MAX_DOC_CHARS = 6000
_MAX_COMPARE_CHARS = 3000


def _strip_fences(text: str) -> str:
    """Remove optional markdown code fences from a Claude response."""
    return _FENCE_RE.sub("", text.strip()).strip()


@dataclass(frozen=True)
class ClaudeProvider:
    """Anthropic Claude adapter. Requires ANTHROPIC_API_KEY at runtime.

    Activated by setting ANALYSIS_PROVIDER=claude.  Uses retrieved source
    fragments as context so full documents are never blindly sent to the API.
    Structured analysis fields (risks, score, suggestions, missing clauses) are
    still computed locally so scoring stays deterministic and explainable.
    """

    name: str = "claude"
    api_key: str = ""
    model: str = "claude-sonnet-4-6"

    def _client(self):  # type: ignore[return]
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "The 'anthropic' package is not installed. "
                "Run: pip install anthropic"
            ) from exc
        return anthropic.Anthropic(api_key=self.api_key)

    def summarize_document(self, filename: str, text: str) -> DocumentSummary:
        """Ask Claude for a prose summary and highlights; keep local structured analysis."""
        client = self._client()
        truncated = text[:_MAX_DOC_CHARS]
        prompt = (
            "You are a contract analyst. Read the contract text below and return a JSON object "
            "with exactly two fields:\n"
            '- "summary": a 2-3 sentence plain-English overview of what this contract covers\n'
            '- "highlights": a list of 3-5 key points a reviewer should know\n\n'
            "Return only valid JSON — no markdown fences, no extra keys.\n\n"
            f"Contract text:\n{truncated}"
        )
        message = client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _strip_fences(message.content[0].text)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}

        prose_summary = parsed.get("summary") or " ".join(summarize(text))
        highlights = parsed.get("highlights") or summarize(text)

        # Structured fields stay local for deterministic, explainable scoring.
        risks = analyze_risks(text)
        return DocumentSummary(
            title=filename,
            summary=prose_summary,
            highlights=highlights,
            risks=risks,
            suggestions=build_suggestions(risks),
            missing_clauses=find_missing_clauses(text),
            language=detect_language(text),
            overall_score=overall_score(risks),
        )

    def answer(self, question: str, fragments: list[str]) -> tuple[str, list[str]]:
        """Ask Claude a question grounded in the provided document fragments.

        Returns ``(answer_text, used_fragment_texts)`` so that the /ask route
        can match used fragments back to stored DocumentFragment objects and
        preserve citations.
        """
        if not fragments:
            return ("No document content available to answer from.", [])

        client = self._client()
        fragment_block = "\n".join(
            f"[{i}] {frag}" for i, frag in enumerate(fragments)
        )
        prompt = (
            "You are a contract analyst. Answer the question using only the document "
            "fragments provided below.\n"
            "If the answer cannot be found in the fragments, say so clearly.\n\n"
            "Return a JSON object with exactly two fields:\n"
            '- "answer": your answer as a plain string\n'
            '- "used_indices": a list of 0-based integer indices of the fragments you used\n\n'
            "Return only valid JSON — no markdown fences.\n\n"
            f"Document fragments:\n{fragment_block}\n\n"
            f"Question: {question}"
        )
        message = client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _strip_fences(message.content[0].text)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}

        answer_text = parsed.get("answer", "")
        used_indices: list[int] = [
            int(i) for i in parsed.get("used_indices", [])
            if isinstance(i, (int, float)) and 0 <= int(i) < len(fragments)
        ]
        used_fragments = [fragments[i] for i in used_indices]
        return (answer_text, used_fragments)

    def compare(self, left_text: str, right_text: str) -> list[DifferenceItem]:
        """Ask Claude to identify material differences between two contracts."""
        client = self._client()
        prompt = (
            "You are a contract analyst. Compare the two contract texts below and identify "
            "material differences.\n\n"
            "Return a JSON object with one field:\n"
            '- "differences": a list of objects, each with:\n'
            '  - "category": one of payment, termination, liability, renewal, confidentiality, other\n'
            '  - "left_text": the relevant excerpt from Contract A (or "not found")\n'
            '  - "right_text": the relevant excerpt from Contract B (or "not found")\n'
            '  - "impact": a brief explanation of why this difference matters\n\n'
            "Return only valid JSON — no markdown fences. "
            "Use an empty list if no material differences are found.\n\n"
            f"Contract A:\n{left_text[:_MAX_COMPARE_CHARS]}\n\n"
            f"Contract B:\n{right_text[:_MAX_COMPARE_CHARS]}"
        )
        message = client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _strip_fences(message.content[0].text)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}

        return [
            DifferenceItem(
                category=item.get("category", "other"),
                left_text=item.get("left_text", ""),
                right_text=item.get("right_text", ""),
                impact=item.get("impact", ""),
            )
            for item in parsed.get("differences", [])
        ]


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
