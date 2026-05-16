from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .models import DifferenceItem, RiskItem, SuggestionItem


STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "this",
    "from",
    "shall",
    "will",
    "have",
    "been",
    "into",
    "your",
    "their",
    "agreement",
    "contract",
}


@dataclass
class RankedSentence:
    sentence: str
    score: float


RISK_RULES = [
    {
        "category": "payment",
        "patterns": ("net 60", "net 90", "late fee", "within sixty", "within ninety"),
        "severity": "medium",
        "title": "Długi termin płatności",
        "explanation": "Dłuższy termin płatności może pogorszyć płynność finansową.",
        "recommendation": "Rozważ skrócenie terminu do 30 dni albo dodanie zaliczki.",
        "score": 18,
    },
    {
        "category": "termination",
        "patterns": ("90 days", "terminate for convenience", "written notice"),
        "severity": "medium",
        "title": "Długi okres wypowiedzenia",
        "explanation": "Długi okres wypowiedzenia ogranicza elastyczność zakończenia współpracy.",
        "recommendation": "Rozważ skrócenie okresu wypowiedzenia lub dodanie wyjątków.",
        "score": 16,
    },
    {
        "category": "liability",
        "patterns": ("limitation of liability", "indirect damages", "consequential"),
        "severity": "high",
        "title": "Ograniczona odpowiedzialność",
        "explanation": "Szerokie wyłączenia odpowiedzialności mogą utrudnić dochodzenie roszczeń.",
        "recommendation": "Doprecyzuj limity oraz wyjątki dla rażącego naruszenia i poufności.",
        "score": 25,
    },
    {
        "category": "renewal",
        "patterns": ("automatic renewal", "auto-renew", "renews automatically"),
        "severity": "medium",
        "title": "Automatyczne odnowienie",
        "explanation": "Automatyczne przedłużenie może tworzyć niechciane zobowiązania.",
        "recommendation": "Dodaj przypomnienie i wyraźne okno rezygnacji przed odnowieniem.",
        "score": 14,
    },
    {
        "category": "confidentiality",
        "patterns": ("confidentiality", "confidential information", "non-disclosure"),
        "severity": "low",
        "title": "Szerokie obowiązki poufności",
        "explanation": "Zakres poufności może być zbyt szeroki lub zbyt długi.",
        "recommendation": "Sprawdź czas obowiązywania i wyłączenia dla informacji publicznych.",
        "score": 10,
    },
]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+", normalize(text))
    return [chunk for chunk in chunks if len(chunk) > 25]


def keywords(text: str) -> Counter[str]:
    tokens = re.findall(r"[A-Za-zÀ-ž]{3,}", text.lower())
    return Counter(token for token in tokens if token not in STOPWORDS)


def summarize(text: str, limit: int = 4) -> list[str]:
    sentences = split_sentences(text)
    if not sentences:
        return []

    frequencies = keywords(text)
    ranked = []
    for sentence in sentences:
        score = sum(frequencies[word] for word in keywords(sentence))
        ranked.append(RankedSentence(sentence=sentence, score=float(score)))

    ranked.sort(key=lambda item: item.score, reverse=True)
    return [item.sentence for item in ranked[:limit]]


def detect_language(text: str) -> str:
    lowered = text.lower()
    polish_markers = (" oraz ", " umowa ", " wypowiedzenia ", " płatności ")
    if any(marker in lowered for marker in polish_markers):
        return "pl"
    return "en"


def analyze_risks(text: str) -> list[RiskItem]:
    lowered = text.lower()
    risks = []
    for rule in RISK_RULES:
        if any(pattern in lowered for pattern in rule["patterns"]):
            risks.append(
                RiskItem(
                    category=rule["category"],
                    severity=rule["severity"],
                    title=rule["title"],
                    explanation=rule["explanation"],
                    recommendation=rule["recommendation"],
                    score=rule["score"],
                )
            )
    return risks


def build_suggestions(risks: list[RiskItem]) -> list[SuggestionItem]:
    proposed = []
    by_category = {risk.category for risk in risks}
    if "payment" in by_category:
        proposed.append(
            SuggestionItem(
                title="Skróć termin płatności",
                rationale="Poprawia płynność i zmniejsza ryzyko finansowania kontrahenta.",
                proposed_text="Payment terms shall be net 30 days from receipt of a valid invoice.",
            )
        )
    if "termination" in by_category:
        proposed.append(
            SuggestionItem(
                title="Skróć okres wypowiedzenia",
                rationale="Zwiększa elastyczność operacyjną obu stron.",
                proposed_text="Either party may terminate this agreement with 30 days written notice.",
            )
        )
    if "liability" in by_category:
        proposed.append(
            SuggestionItem(
                title="Dodaj wyjątki do limitu odpowiedzialności",
                rationale="Chroni przy naruszeniu poufności i umyślnym działaniu.",
                proposed_text="The liability cap shall not apply to fraud, wilful misconduct, or breach of confidentiality.",
            )
        )
    return proposed


def overall_score(risks: list[RiskItem]) -> int:
    return max(0, 100 - sum(risk.score for risk in risks))


def similarity_score(question: str, fragment: str) -> float:
    q = set(keywords(question))
    f = set(keywords(fragment))
    if not q or not f:
        return 0.0
    return len(q & f) / len(q)


def answer_question(question: str, fragments: list[str]) -> tuple[str, list[str]]:
    ranked = sorted(fragments, key=lambda fragment: similarity_score(question, fragment), reverse=True)
    relevant = [fragment for fragment in ranked if similarity_score(question, fragment) > 0][:3]
    if not relevant:
        return (
            "Nie znalazłem wystarczająco mocnego fragmentu w dokumencie, żeby odpowiedzieć pewnie.",
            [],
        )
    return ("Na podstawie dokumentu: " + " ".join(relevant), relevant)


def compare_documents(left_text: str, right_text: str) -> list[DifferenceItem]:
    left_lower = left_text.lower()
    right_lower = right_text.lower()
    differences = []

    checks = [
        ("payment", "net 30", "net 60", "Zmiana może wpływać na cash flow."),
        ("termination", "30 days", "90 days", "Zmiana wpływa na elastyczność zakończenia umowy."),
        ("liability", "liability cap", "limitation of liability", "Zmiana wpływa na ekspozycję prawną."),
        ("renewal", "automatic renewal", "no automatic renewal", "Zmiana wpływa na kontrolę nad przedłużeniem."),
    ]

    for category, marker_a, marker_b, impact in checks:
        left_has_a = marker_a in left_lower
        right_has_a = marker_a in right_lower
        left_has_b = marker_b in left_lower
        right_has_b = marker_b in right_lower
        if (left_has_a != right_has_a) or (left_has_b != right_has_b):
            differences.append(
                DifferenceItem(
                    category=category,
                    left_text=marker_a if left_has_a else marker_b if left_has_b else "not found",
                    right_text=marker_a if right_has_a else marker_b if right_has_b else "not found",
                    impact=impact,
                )
            )
    return differences
