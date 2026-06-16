"""
test_ingestion.py — Tests for real-world document ingestion robustness.

Covers:
  - Text cleaning (clean_text)
  - Repeated-line removal (remove_repeated_lines)
  - Chunk splitting and page-number preservation (chunk_pages, split_text)
  - Analyzer robustness on short/empty/generic documents
  - Fixture-based integration tests (messy, short, long, generic)
  - API upload integration: multiple fragments, max-length, no crash
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import main, store
from backend.app.analyzer import analyze_risks, find_missing_clauses, summarize
from backend.app.chunker import (
    MAX_CHUNK_CHARS,
    MIN_CHUNK_CHARS,
    chunk_pages,
    clean_text,
    remove_repeated_lines,
    split_text,
)
from backend.app.main import app
from backend.app.providers import LocalProvider

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# API-level fixtures (mirror test_api.py pattern)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(store, "INDEX_FILE", tmp_path / "documents.json")


@pytest.fixture(autouse=True)
def force_local_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "provider", LocalProvider())


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------

class TestCleanText:
    def test_collapses_multiple_spaces(self) -> None:
        assert clean_text("hello   world") == "hello world"

    def test_removes_null_bytes(self) -> None:
        assert "\x00" not in clean_text("hello\x00world")

    def test_collapses_excess_blank_lines(self) -> None:
        result = clean_text("a\n\n\n\n\nb")
        assert "\n\n\n" not in result

    def test_strips_line_leading_trailing_whitespace(self) -> None:
        result = clean_text("  hello  \n  world  ")
        assert result == "hello\nworld"

    def test_normalizes_crlf(self) -> None:
        result = clean_text("line1\r\nline2\rline3")
        assert "\r" not in result
        assert "line1" in result and "line2" in result and "line3" in result

    def test_empty_string_returns_empty(self) -> None:
        assert clean_text("") == ""

    def test_only_whitespace_returns_empty(self) -> None:
        assert clean_text("   \n\n\t  ") == ""


# ---------------------------------------------------------------------------
# remove_repeated_lines
# ---------------------------------------------------------------------------

class TestRemoveRepeatedLines:
    def test_removes_header_present_in_all_pages(self) -> None:
        pages = [
            "CONFIDENTIAL\nPage one content about payment terms.",
            "CONFIDENTIAL\nPage two content about termination rights.",
            "CONFIDENTIAL\nPage three content about governing law.",
        ]
        result = remove_repeated_lines(pages)
        assert all("CONFIDENTIAL" not in p for p in result)

    def test_preserves_unique_content(self) -> None:
        pages = [
            "CONFIDENTIAL\nPayment is due net 60 days.",
            "CONFIDENTIAL\nTermination requires 90 days notice.",
            "CONFIDENTIAL\nGoverning law is Delaware.",
        ]
        result = remove_repeated_lines(pages)
        combined = "\n".join(result)
        assert "Payment" in combined
        assert "Termination" in combined

    def test_unchanged_when_fewer_than_three_pages(self) -> None:
        pages = ["header\npage one", "header\npage two"]
        assert remove_repeated_lines(pages) == pages

    def test_unchanged_when_no_repeated_lines(self) -> None:
        pages = [
            "Unique content for page one only.",
            "Different unique content for page two.",
            "Another unique block of text for page three.",
        ]
        result = remove_repeated_lines(pages)
        assert result == pages


# ---------------------------------------------------------------------------
# split_text
# ---------------------------------------------------------------------------

class TestSplitText:
    def test_short_text_returned_as_single_chunk(self) -> None:
        text = "Short contract clause."
        result = split_text(text, max_chars=200)
        assert result == [text]

    def test_long_text_split_into_multiple_chunks(self) -> None:
        text = "This is a test sentence. " * 100
        result = split_text(text)
        assert len(result) > 1

    def test_all_chunks_within_max_chars(self) -> None:
        text = "This fills up the text buffer for testing chunking. " * 200
        for chunk in split_text(text):
            assert len(chunk) <= MAX_CHUNK_CHARS

    def test_empty_text_returns_empty_list(self) -> None:
        assert split_text("") == []

    def test_heading_based_split(self) -> None:
        # Use a small max_chars so the heading-based split actually triggers.
        clause = (
            "1. Payment Terms\n"
            "Payment is due net thirty days from receipt of invoice. "
            "Late payments shall bear interest at one and a half percent per month. "
            "Client must submit disputes in writing within ten business days."
        )
        result = split_text(clause, max_chars=80)
        assert len(result) >= 2


# ---------------------------------------------------------------------------
# chunk_pages
# ---------------------------------------------------------------------------

class TestChunkPages:
    def test_short_page_produces_one_chunk(self) -> None:
        texts, pages = chunk_pages(["A brief contract clause for testing."])
        assert len(texts) >= 1

    def test_long_text_produces_multiple_chunks(self) -> None:
        long = "This sentence fills the buffer to test windowed chunking. " * 100
        texts, pages = chunk_pages([long])
        assert len(texts) > 1

    def test_all_chunks_within_max_length(self) -> None:
        long = "A sentence for stress testing the chunking function. " * 200
        texts, _ = chunk_pages([long])
        for chunk in texts:
            assert len(chunk) <= MAX_CHUNK_CHARS

    def test_page_numbers_preserved_across_pages(self) -> None:
        page1 = "Content on the first page of the document. " * 5
        page2 = "Content on the second page of the document. " * 5
        _, pages = chunk_pages([page1, page2])
        assert 1 in pages
        assert 2 in pages

    def test_chunks_from_long_page_all_share_source_page(self) -> None:
        long_page1 = "Long page one sentence for testing page number propagation. " * 100
        _, pages = chunk_pages([long_page1])
        assert all(p == 1 for p in pages)

    def test_chunks_from_page_two_have_page_two(self) -> None:
        short_page1 = "This is brief page one content that fits in one chunk."
        long_page2 = "Long page two content that forces splitting into multiple chunks. " * 100
        texts, pages = chunk_pages([short_page1, long_page2])
        page2_chunks = [t for t, p in zip(texts, pages) if p == 2]
        assert len(page2_chunks) > 1

    def test_empty_pages_skipped(self) -> None:
        texts, _ = chunk_pages(["", "   ", "Real contract content for this test."])
        assert all(t.strip() for t in texts)

    def test_short_document_does_not_crash(self) -> None:
        texts, pages = chunk_pages(["Short."])
        assert isinstance(texts, list)
        assert isinstance(pages, list)

    def test_parallel_lists_same_length(self) -> None:
        long = "Testing chunk page list length alignment. " * 100
        texts, pages = chunk_pages([long, "page two content here."])
        assert len(texts) == len(pages)

    def test_chunk_pages_min_length_filter(self) -> None:
        tiny = "Hi."
        medium = "This is a sufficient length paragraph for ingestion purposes."
        texts, _ = chunk_pages([tiny, medium])
        for t in texts:
            assert len(t) >= MIN_CHUNK_CHARS or len(texts) == 1


# ---------------------------------------------------------------------------
# Analyzer robustness
# ---------------------------------------------------------------------------

class TestAnalyzerRobustness:
    def test_summarize_empty_string(self) -> None:
        result = summarize("")
        assert isinstance(result, list)

    def test_summarize_very_short_document(self) -> None:
        result = summarize("Short.")
        assert isinstance(result, list)

    def test_summarize_single_sentence(self) -> None:
        result = summarize("This agreement governs the provision of services.")
        assert isinstance(result, list)

    def test_summarize_returns_list_of_strings(self) -> None:
        text = "Payment is due net 60 days. Either party may terminate with 90 days notice."
        result = summarize(text)
        assert all(isinstance(s, str) for s in result)

    def test_analyze_risks_empty_string(self) -> None:
        assert analyze_risks("") == []

    def test_analyze_risks_detects_liability_limitation(self) -> None:
        text = "In no event shall either party be liable for indirect, incidental, or consequential damages."
        risks = analyze_risks(text)
        categories = {r.category for r in risks}
        assert "liability" in categories

    def test_analyze_risks_detects_indemnification(self) -> None:
        text = "Client shall indemnify and hold harmless the service provider from all third-party claims."
        risks = analyze_risks(text)
        categories = {r.category for r in risks}
        assert "indemnification" in categories

    def test_analyze_risks_detects_extended_payment(self) -> None:
        text = "All invoices are payable within net 60 days of the invoice date."
        risks = analyze_risks(text)
        categories = {r.category for r in risks}
        assert "payment" in categories

    def test_analyze_risks_detects_auto_renewal(self) -> None:
        text = "This agreement shall automatically renew unless cancelled by either party."
        risks = analyze_risks(text)
        categories = {r.category for r in risks}
        assert "renewal" in categories

    def test_find_missing_clauses_returns_list(self) -> None:
        result = find_missing_clauses("")
        assert isinstance(result, list)

    def test_find_missing_clauses_detects_absent_governing_law(self) -> None:
        text = "The parties agree to provide services."
        missing = find_missing_clauses(text)
        missing_categories = {m.category for m in missing}
        assert "governing_law" in missing_categories


# ---------------------------------------------------------------------------
# Fixture-based integration tests
# ---------------------------------------------------------------------------

class TestFixtureIngestion:
    def test_messy_contract_produces_multiple_chunks(self) -> None:
        text = (FIXTURES / "messy_contract.txt").read_text(encoding="utf-8")
        texts, pages = chunk_pages([text])
        assert len(texts) > 1

    def test_messy_contract_all_chunks_within_limit(self) -> None:
        text = (FIXTURES / "messy_contract.txt").read_text(encoding="utf-8")
        texts, _ = chunk_pages([text])
        for chunk in texts:
            assert len(chunk) <= MAX_CHUNK_CHARS

    def test_short_document_does_not_crash(self) -> None:
        text = (FIXTURES / "short_document.txt").read_text(encoding="utf-8")
        texts, pages = chunk_pages([text])
        assert isinstance(texts, list)

    def test_short_document_summary_does_not_crash(self) -> None:
        text = (FIXTURES / "short_document.txt").read_text(encoding="utf-8")
        result = summarize(text)
        assert isinstance(result, list)

    def test_generic_agreement_risk_detection(self) -> None:
        text = (FIXTURES / "generic_service_agreement.txt").read_text(encoding="utf-8")
        risks = analyze_risks(text)
        assert len(risks) >= 2

    def test_generic_agreement_detects_liability(self) -> None:
        text = (FIXTURES / "generic_service_agreement.txt").read_text(encoding="utf-8")
        risks = analyze_risks(text)
        assert any(r.category == "liability" for r in risks)

    def test_generic_agreement_detects_indemnification(self) -> None:
        text = (FIXTURES / "generic_service_agreement.txt").read_text(encoding="utf-8")
        risks = analyze_risks(text)
        assert any(r.category == "indemnification" for r in risks)

    def test_long_paragraph_document_all_chunks_within_limit(self) -> None:
        text = (FIXTURES / "long_paragraph_document.txt").read_text(encoding="utf-8")
        texts, _ = chunk_pages([text])
        for chunk in texts:
            assert len(chunk) <= MAX_CHUNK_CHARS

    def test_long_paragraph_document_multiple_chunks(self) -> None:
        text = (FIXTURES / "long_paragraph_document.txt").read_text(encoding="utf-8")
        texts, _ = chunk_pages([text])
        assert len(texts) > 1

    def test_generic_agreement_summary_not_empty(self) -> None:
        text = (FIXTURES / "generic_service_agreement.txt").read_text(encoding="utf-8")
        result = summarize(text)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# API-level upload integration
# ---------------------------------------------------------------------------

class TestUploadIntegration:
    def test_upload_messy_contract_creates_multiple_fragments(self, client: TestClient) -> None:
        content = (FIXTURES / "messy_contract.txt").read_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("messy_contract.txt", content)},
        )
        assert response.status_code == 200
        doc = response.json()
        assert len(doc["fragments"]) > 1

    def test_upload_generic_agreement_fragments_within_max(self, client: TestClient) -> None:
        content = (FIXTURES / "generic_service_agreement.txt").read_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("generic_service_agreement.txt", content)},
        )
        assert response.status_code == 200
        doc = response.json()
        for fragment in doc["fragments"]:
            assert len(fragment["text"]) <= MAX_CHUNK_CHARS

    def test_upload_short_document_does_not_crash(self, client: TestClient) -> None:
        content = (FIXTURES / "short_document.txt").read_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("short_document.txt", content)},
        )
        assert response.status_code == 200

    def test_upload_long_paragraph_document_fragments_within_max(self, client: TestClient) -> None:
        content = (FIXTURES / "long_paragraph_document.txt").read_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("long_paragraph_document.txt", content)},
        )
        assert response.status_code == 200
        doc = response.json()
        for fragment in doc["fragments"]:
            assert len(fragment["text"]) <= MAX_CHUNK_CHARS

    def test_upload_preserves_page_numbers_as_positive_integers(self, client: TestClient) -> None:
        content = (FIXTURES / "generic_service_agreement.txt").read_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("generic_service_agreement.txt", content)},
        )
        assert response.status_code == 200
        doc = response.json()
        for fragment in doc["fragments"]:
            assert isinstance(fragment["page"], int)
            assert fragment["page"] >= 1

    def test_upload_generic_agreement_risk_analysis_works(self, client: TestClient) -> None:
        content = (FIXTURES / "generic_service_agreement.txt").read_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("generic_service_agreement.txt", content)},
        )
        assert response.status_code == 200
        doc = response.json()
        assert isinstance(doc["summary"]["risks"], list)
        assert len(doc["summary"]["risks"]) >= 1

    def test_upload_qa_finds_context_in_generic_wording(self, client: TestClient) -> None:
        content = (FIXTURES / "generic_service_agreement.txt").read_bytes()
        upload_response = client.post(
            "/documents/upload",
            files={"file": ("generic_service_agreement.txt", content)},
        )
        assert upload_response.status_code == 200
        doc_id = upload_response.json()["id"]

        ask_response = client.post(
            f"/documents/{doc_id}/ask",
            json={"question": "What are the payment terms?"},
        )
        assert ask_response.status_code == 200
        result = ask_response.json()
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0

    def test_upload_messy_contract_summary_not_empty(self, client: TestClient) -> None:
        content = (FIXTURES / "messy_contract.txt").read_bytes()
        response = client.post(
            "/documents/upload",
            files={"file": ("messy_contract.txt", content)},
        )
        assert response.status_code == 200
        doc = response.json()
        assert doc["summary"]["summary"]
