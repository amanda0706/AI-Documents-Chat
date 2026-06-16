from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .models import DifferenceItem, MissingClauseItem, RiskItem, SuggestionItem


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
        "patterns": (
            "net 45", "net 60", "net 90",
            "late fee", "within sixty", "within ninety",
            "payment within 45", "payment within 60", "payment within 90",
            "overdue interest", "interest on late", "accrues interest",
        ),
        "severity": "medium",
        "title": "Extended payment terms",
        "explanation": "Long payment windows hurt cash flow and increase collection risk.",
        "recommendation": "Consider reducing to net 30 or adding an advance payment.",
        "score": 18,
    },
    {
        "category": "termination",
        "patterns": (
            "90 days", "ninety days", "sixty days",
            "terminate for convenience", "written notice",
            "days' notice", "days notice", "termination for convenience",
            "either party may terminate",
        ),
        "severity": "medium",
        "title": "Long notice or termination period",
        "explanation": "A long notice period limits operational flexibility.",
        "recommendation": "Consider a 30-day notice period or mutual termination rights.",
        "score": 16,
    },
    {
        "category": "liability",
        "patterns": (
            "limitation of liability", "indirect damages", "consequential",
            "not be liable", "no liability", "excludes liability",
            "total liability", "aggregate liability", "liability cap",
            "incidental damages", "special damages", "in no event",
        ),
        "severity": "high",
        "title": "Liability limitation or exclusion",
        "explanation": "Broad liability exclusions may limit your ability to recover losses.",
        "recommendation": "Carve out fraud, wilful misconduct, and confidentiality breaches.",
        "score": 25,
    },
    {
        "category": "renewal",
        "patterns": (
            "automatic renewal", "auto-renew", "renews automatically",
            "automatically renews", "unless cancelled", "unless terminated prior",
            "unless notice is given", "shall automatically renew",
        ),
        "severity": "medium",
        "title": "Automatic renewal clause",
        "explanation": "Auto-renewal can create unexpected obligations.",
        "recommendation": "Add a clear opt-out window and calendar reminders.",
        "score": 14,
    },
    {
        "category": "confidentiality",
        "patterns": (
            "confidentiality", "confidential information", "non-disclosure",
            "proprietary information", "trade secrets",
        ),
        "severity": "low",
        "title": "Broad confidentiality obligations",
        "explanation": "Confidentiality scope may be too wide or its duration too long.",
        "recommendation": "Review the term, scope, and carve-outs for publicly available information.",
        "score": 10,
    },
    {
        "category": "indemnification",
        "patterns": (
            "indemnify", "indemnification", "indemnified",
            "hold harmless", "defend and hold", "indemnify and defend",
        ),
        "severity": "high",
        "title": "Broad indemnification obligation",
        "explanation": "Open-ended indemnification clauses can expose you to unlimited liability.",
        "recommendation": "Limit to direct claims arising from your own breach and add a mutual obligation.",
        "score": 20,
    },
    {
        "category": "ip_assignment",
        "patterns": (
            "work for hire", "assigns all", "all intellectual property",
            "sole and exclusive", "irrevocably assigns", "all right title and interest",
        ),
        "severity": "high",
        "title": "Broad IP assignment",
        "explanation": "Assigning all IP without limitation may transfer rights beyond the project scope.",
        "recommendation": "Narrow the assignment to deliverables created under this agreement.",
        "score": 22,
    },
]

CLAUSE_PLAYBOOK = [
    {
        "category": "governing_law",
        "title": "Governing law",
        "signals": ("governing law", "laws of", "jurisdiction"),
        "why_it_matters": "Establishes which country or state's law governs the agreement.",
        "expected_signal": "governing law / jurisdiction",
    },
    {
        "category": "confidentiality",
        "title": "Confidentiality",
        "signals": ("confidentiality", "confidential information", "non-disclosure"),
        "why_it_matters": "Protects commercially sensitive information shared between parties.",
        "expected_signal": "confidentiality / non-disclosure",
    },
    {
        "category": "termination",
        "title": "Termination",
        "signals": ("termination", "terminate", "written notice"),
        "why_it_matters": "Defines how each party can exit the agreement.",
        "expected_signal": "termination / written notice",
    },
    {
        "category": "liability",
        "title": "Liability",
        "signals": ("liability", "indirect damages", "consequential damages"),
        "why_it_matters": "Establishes financial exposure and liability limits.",
        "expected_signal": "liability / damages",
    },
    {
        "category": "payment",
        "title": "Payment terms",
        "signals": ("payment terms", "invoice", "net 30", "net 60", "fees", "compensation"),
        "why_it_matters": "Defines when and how payments are made.",
        "expected_signal": "payment terms / invoice",
    },
    {
        "category": "force_majeure",
        "title": "Force majeure",
        "signals": ("force majeure", "act of god", "circumstances beyond", "beyond reasonable control"),
        "why_it_matters": "Protects parties when performance is impossible due to unforeseeable events.",
        "expected_signal": "force majeure / circumstances beyond control",
    },
    {
        "category": "indemnification",
        "title": "Indemnification",
        "signals": ("indemnif", "hold harmless", "defend against"),
        "why_it_matters": "Establishes who bears costs if a third party makes a claim.",
        "expected_signal": "indemnification / hold harmless",
    },
    {
        "category": "dispute_resolution",
        "title": "Dispute resolution",
        "signals": ("arbitration", "dispute resolution", "mediation", "escalation procedure"),
        "why_it_matters": "Defines how disagreements are resolved, avoiding costly litigation.",
        "expected_signal": "arbitration / dispute resolution",
    },
    {
        "category": "ip_ownership",
        "title": "IP ownership",
        "signals": ("intellectual property", "work product", "deliverables", "proprietary rights"),
        "why_it_matters": "Clarifies who owns the outputs of the engagement.",
        "expected_signal": "intellectual property / work product",
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
        # Very short or structurally unusual document — return whatever text exists.
        stripped = text.strip()
        return [stripped[:500]] if stripped else []

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
                title="Shorten payment terms",
                rationale="Improves cash flow and reduces the risk of financing the counterparty.",
                proposed_text="Payment terms shall be net 30 days from receipt of a valid invoice.",
            )
        )
    if "termination" in by_category:
        proposed.append(
            SuggestionItem(
                title="Shorten notice period",
                rationale="Increases operational flexibility for both parties.",
                proposed_text="Either party may terminate this agreement with 30 days written notice.",
            )
        )
    if "liability" in by_category:
        proposed.append(
            SuggestionItem(
                title="Add carve-outs to liability cap",
                rationale="Protects against uncapped exposure for fraud and confidentiality breaches.",
                proposed_text="The liability cap shall not apply to fraud, wilful misconduct, or breach of confidentiality.",
            )
        )
    if "indemnification" in by_category:
        proposed.append(
            SuggestionItem(
                title="Narrow indemnification scope",
                rationale="Limits exposure to claims directly caused by your own breach.",
                proposed_text="Each party shall indemnify the other only for claims arising directly from its own material breach or gross negligence.",
            )
        )
    if "ip_assignment" in by_category:
        proposed.append(
            SuggestionItem(
                title="Scope IP assignment to deliverables",
                rationale="Prevents inadvertent assignment of pre-existing IP or tools.",
                proposed_text="IP assignment applies solely to work product created specifically under this agreement and does not extend to pre-existing materials.",
            )
        )
    return proposed


def find_missing_clauses(text: str) -> list[MissingClauseItem]:
    lowered = text.lower()
    return [
        MissingClauseItem(
            category=clause["category"],
            title=clause["title"],
            why_it_matters=clause["why_it_matters"],
            expected_signal=clause["expected_signal"],
        )
        for clause in CLAUSE_PLAYBOOK
        if not any(signal in lowered for signal in clause["signals"])
    ]


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
            left_sentence = sentence_for_marker(left_text, marker_a, marker_b)
            right_sentence = sentence_for_marker(right_text, marker_a, marker_b)
            differences.append(
                DifferenceItem(
                    category=category,
                    left_text=left_sentence,
                    right_text=right_sentence,
                    impact=impact,
                )
            )
    return differences


def sentence_for_marker(text: str, marker_a: str, marker_b: str) -> str:
    for sentence in split_sentences(text):
        lowered = sentence.lower()
        if marker_a in lowered or marker_b in lowered:
            return sentence
    return "not found"
