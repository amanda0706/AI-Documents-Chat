"""
Tests for the local embeddings / vector retrieval layer.

Covers:
- local_embed: determinism, dimensionality, unit-norm, empty input, divergence
- cosine_similarity: identity, symmetry, zero-vector, high-overlap
- reindex_document: record count, provider/dim metadata, idempotence
- vector_search: top-k ordering, score bounds, empty-index fallback
- API endpoints: POST /embeddings/reindex, GET /documents/{id}/embeddings,
  GET /documents/{id}/vector-search
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import embeddings as emb_module
from backend.app import main, store
from backend.app.embeddings import (
    EMBED_DIM,
    EmbeddingRecord,
    cosine_similarity,
    delete_document_embeddings,
    get_document_embeddings,
    local_embed,
    reindex_document,
    upsert_embeddings,
    vector_search,
)
from backend.app.main import app
from backend.app.models import (
    DocumentDetail,
    DocumentFragment,
    DocumentSummary,
    ReviewStatus,
)
from backend.app.providers import LocalProvider


# ---------------------------------------------------------------------------
# Fixtures shared with test_api.py pattern
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(store, "INDEX_FILE", tmp_path / "documents.json")


@pytest.fixture(autouse=True)
def isolated_embed_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the embeddings JSON file to a per-test temp directory."""
    monkeypatch.setattr(emb_module, "_EMBED_FILE", tmp_path / "embeddings.json")


@pytest.fixture(autouse=True)
def force_local_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "provider", LocalProvider())


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper: minimal DocumentDetail
# ---------------------------------------------------------------------------


def _make_doc(fragment_texts: list[str], doc_id: str = "doc-001") -> DocumentDetail:
    return DocumentDetail(
        id=doc_id,
        filename="test.txt",
        version_group_id=doc_id,
        version_number=1,
        is_latest_version=True,
        extraction_method="text",
        page_count=len(fragment_texts),
        shared_with=[],
        summary=DocumentSummary(
            title="Test Contract",
            summary="A synthetic test document.",
            highlights=[],
            risks=[],
            suggestions=[],
            missing_clauses=[],
            language="en",
            overall_score=100,
        ),
        fragments=[
            DocumentFragment(id=f"{doc_id}-{i}", page=i + 1, text=text)
            for i, text in enumerate(fragment_texts)
        ],
    )


# ---------------------------------------------------------------------------
# local_embed
# ---------------------------------------------------------------------------


class TestLocalEmbed:
    def test_returns_correct_dimension(self):
        vec = local_embed("payment terms invoice due date")
        assert len(vec) == EMBED_DIM

    def test_deterministic(self):
        text = "governing law Germany arbitration proceedings"
        assert local_embed(text) == local_embed(text)

    def test_unit_vector(self):
        vec = local_embed("confidentiality obligations non-disclosure agreement")
        magnitude = math.sqrt(sum(v * v for v in vec))
        assert abs(magnitude - 1.0) < 1e-9

    def test_empty_text_returns_zero_vector(self):
        assert local_embed("") == [0.0] * EMBED_DIM
        assert local_embed("   ") == [0.0] * EMBED_DIM

    def test_short_tokens_ignored(self):
        # Only tokens >= 3 chars are counted; "is", "an" etc. should be skipped
        vec_short = local_embed("is an to of")
        assert vec_short == [0.0] * EMBED_DIM

    def test_different_texts_differ(self):
        a = local_embed("payment invoice net thirty days")
        b = local_embed("arbitration dispute resolution governing law")
        assert a != b

    def test_all_values_in_valid_range(self):
        vec = local_embed("liability consequential damages indirect losses")
        assert all(-1.0 <= v <= 1.0 for v in vec)


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_unit_vectors_score_one(self):
        vec = local_embed("contract termination written notice period")
        assert abs(cosine_similarity(vec, vec) - 1.0) < 1e-9

    def test_symmetry(self):
        a = local_embed("liability cap consequential damages")
        b = local_embed("payment terms invoice due thirty")
        assert abs(cosine_similarity(a, b) - cosine_similarity(b, a)) < 1e-9

    def test_zero_vector_returns_zero(self):
        zero = [0.0] * EMBED_DIM
        unit = local_embed("termination notice")
        assert cosine_similarity(zero, unit) == 0.0

    def test_result_clamped_to_minus_one_one(self):
        a = local_embed("foo bar baz")
        b = local_embed("qux quux corge")
        score = cosine_similarity(a, b)
        assert -1.0 <= score <= 1.0

    def test_shared_vocabulary_boosts_similarity(self):
        a = local_embed("payment payment payment invoice")
        b = local_embed("payment invoice fees")
        unrelated = local_embed("termination arbitration dispute")
        assert cosine_similarity(a, b) > cosine_similarity(a, unrelated)


# ---------------------------------------------------------------------------
# reindex_document
# ---------------------------------------------------------------------------


class TestReindexDocument:
    def test_creates_one_record_per_fragment(self):
        doc = _make_doc([
            "Payment terms shall be net thirty days from receipt.",
            "Either party may terminate with thirty days written notice.",
        ])
        records = reindex_document(doc)
        assert len(records) == 2

    def test_record_metadata_populated(self):
        doc = _make_doc(["Liability is limited to fees paid in the last six months."])
        records = reindex_document(doc)
        rec = records[0]
        assert rec.document_id == doc.id
        assert rec.provider == "local"
        assert rec.dim == EMBED_DIM
        assert len(rec.vector) == EMBED_DIM

    def test_skips_blank_fragments(self):
        doc = _make_doc(["Valid clause text here.", "   ", ""])
        records = reindex_document(doc)
        assert len(records) == 1

    def test_idempotent_no_duplicate_records(self):
        doc = _make_doc(["Confidentiality obligations survive termination for three years."])
        reindex_document(doc)
        reindex_document(doc)
        raw = emb_module._load_raw()
        assert len(raw) == 1

    def test_provider_field_stored(self):
        doc = _make_doc(["Governing law shall be the laws of Scotland."])
        records = reindex_document(doc, provider="local")
        assert records[0].provider == "local"


# ---------------------------------------------------------------------------
# vector_search
# ---------------------------------------------------------------------------


class TestVectorSearch:
    def test_returns_top_k_results(self):
        doc = _make_doc([
            "Payment shall be due within thirty days of invoice.",
            "Either party may terminate with ninety days written notice.",
            "Liability for consequential damages is expressly excluded.",
        ])
        reindex_document(doc)
        results = vector_search("payment invoice", doc.id, top_k=2)
        assert len(results) == 2

    def test_results_sorted_descending(self):
        doc = _make_doc([
            "Payment shall be due within thirty days of invoice.",
            "Termination requires ninety days written notice.",
        ])
        reindex_document(doc)
        results = vector_search("payment invoice", doc.id, top_k=2)
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True)

    def test_scores_in_valid_range(self):
        doc = _make_doc(["Confidentiality obligations are binding on both parties."])
        reindex_document(doc)
        results = vector_search("confidentiality", doc.id, top_k=1)
        _, score = results[0]
        assert -1.0 <= score <= 1.0

    def test_empty_index_returns_empty(self):
        results = vector_search("payment", "nonexistent-doc", top_k=3)
        assert results == []

    def test_metadata_excludes_vector(self):
        doc = _make_doc(["Governing law is the law of England and Wales."])
        reindex_document(doc)
        results = vector_search("governing law", doc.id, top_k=1)
        meta, _ = results[0]
        assert "vector" not in meta
        assert "text" in meta
        assert "page" in meta

    def test_relevant_fragment_ranked_above_irrelevant(self):
        doc = _make_doc([
            "Payment terms are net thirty days from invoice receipt.",
            "The parties agree to arbitrate disputes in Berlin under DIS rules.",
        ])
        reindex_document(doc)
        results = vector_search("invoice payment due", doc.id, top_k=2)
        top_meta, _ = results[0]
        assert "payment" in top_meta["text"].lower() or "invoice" in top_meta["text"].lower()


# ---------------------------------------------------------------------------
# upsert / get / delete helpers
# ---------------------------------------------------------------------------


class TestStoreHelpers:
    def test_upsert_and_retrieve(self):
        rec = EmbeddingRecord(
            document_id="d1",
            fragment_id="d1-0",
            page=1,
            text="Sample clause text.",
            vector=local_embed("Sample clause text."),
            provider="local",
            dim=EMBED_DIM,
        )
        upsert_embeddings([rec])
        retrieved = get_document_embeddings("d1")
        assert len(retrieved) == 1
        assert "vector" not in retrieved[0]

    def test_include_vectors_flag(self):
        rec = EmbeddingRecord(
            document_id="d2",
            fragment_id="d2-0",
            page=1,
            text="Another clause.",
            vector=local_embed("Another clause."),
            provider="local",
            dim=EMBED_DIM,
        )
        upsert_embeddings([rec])
        with_vec = get_document_embeddings("d2", include_vectors=True)
        assert "vector" in with_vec[0]
        assert len(with_vec[0]["vector"]) == EMBED_DIM

    def test_delete_removes_records(self):
        doc = _make_doc(["Clause one.", "Clause two and more text here."])
        reindex_document(doc)
        removed = delete_document_embeddings(doc.id)
        assert removed == 2
        remaining = get_document_embeddings(doc.id)
        assert remaining == []

    def test_delete_nonexistent_returns_zero(self):
        removed = delete_document_embeddings("no-such-doc")
        assert removed == 0

    def test_get_embeddings_empty_store_returns_empty(self):
        result = get_document_embeddings("missing-doc")
        assert result == []


# ---------------------------------------------------------------------------
# API: POST /embeddings/reindex
# ---------------------------------------------------------------------------


class TestReindexEndpoint:
    def _upload(self, client: TestClient) -> str:
        resp = client.post(
            "/documents/upload",
            files={"file": ("sample.txt", b"Payment terms are net sixty days. Liability cap applies to all indirect losses.")},
        )
        assert resp.status_code == 200
        return resp.json()["id"]

    def test_reindex_single_document(self, client: TestClient):
        doc_id = self._upload(client)
        resp = client.post("/embeddings/reindex", json={"doc_id": doc_id})
        assert resp.status_code == 200
        body = resp.json()
        assert body["indexed_documents"] == 1
        assert body["total_fragments"] >= 1
        assert body["provider"] == "local"
        assert body["dim"] == EMBED_DIM

    def test_reindex_all_documents(self, client: TestClient):
        self._upload(client)
        self._upload(client)
        resp = client.post("/embeddings/reindex", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["indexed_documents"] == 2

    def test_reindex_null_doc_id_indexes_all(self, client: TestClient):
        self._upload(client)
        resp = client.post("/embeddings/reindex", json={"doc_id": None})
        assert resp.status_code == 200
        assert resp.json()["indexed_documents"] == 1

    def test_reindex_unknown_doc_returns_404(self, client: TestClient):
        resp = client.post("/embeddings/reindex", json={"doc_id": "no-such-id"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API: GET /documents/{id}/embeddings
# ---------------------------------------------------------------------------


class TestEmbeddingsEndpoint:
    def _upload_and_reindex(self, client: TestClient) -> str:
        resp = client.post(
            "/documents/upload",
            files={"file": ("nda.txt", b"Confidentiality obligations bind both parties for three years after termination.")},
        )
        doc_id = resp.json()["id"]
        client.post("/embeddings/reindex", json={"doc_id": doc_id})
        return doc_id

    def test_returns_embedding_metadata(self, client: TestClient):
        doc_id = self._upload_and_reindex(client)
        resp = client.get(f"/documents/{doc_id}/embeddings")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        first = items[0]
        assert first["document_id"] == doc_id
        assert "fragment_id" in first
        assert "page" in first
        assert "provider" in first
        assert "dim" in first
        assert "vector" not in first  # omitted by default

    def test_vectors_included_when_requested(self, client: TestClient):
        doc_id = self._upload_and_reindex(client)
        resp = client.get(f"/documents/{doc_id}/embeddings?include_vectors=true")
        assert resp.status_code == 200
        first = resp.json()[0]
        assert "vector" in first
        assert len(first["vector"]) == EMBED_DIM

    def test_not_indexed_returns_404(self, client: TestClient):
        resp = client.post(
            "/documents/upload",
            files={"file": ("empty.txt", b"Some contract text with enough content to index here.")},
        )
        doc_id = resp.json()["id"]
        # no reindex call
        resp = client.get(f"/documents/{doc_id}/embeddings")
        assert resp.status_code == 404

    def test_unknown_document_returns_404(self, client: TestClient):
        resp = client.get("/documents/no-such-doc/embeddings")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API: GET /documents/{id}/vector-search
# ---------------------------------------------------------------------------


class TestVectorSearchEndpoint:
    def _upload_and_reindex(self, client: TestClient, content: bytes) -> str:
        resp = client.post(
            "/documents/upload",
            files={"file": ("contract.txt", content)},
        )
        doc_id = resp.json()["id"]
        client.post("/embeddings/reindex", json={"doc_id": doc_id})
        return doc_id

    def test_returns_ranked_results(self, client: TestClient):
        content = (
            b"Payment terms are net thirty days from invoice date.\n\n"
            b"Either party may terminate this agreement with ninety days written notice.\n\n"
            b"Liability for indirect and consequential damages is excluded by mutual agreement."
        )
        doc_id = self._upload_and_reindex(client, content)
        resp = client.get(f"/documents/{doc_id}/vector-search?query=payment+invoice&top_k=2")
        assert resp.status_code == 200
        body = resp.json()
        assert body["query"] == "payment invoice"
        assert body["top_k"] == 2
        assert body["provider"] == "local"
        assert body["dim"] == EMBED_DIM
        assert len(body["results"]) == 2
        result = body["results"][0]
        assert result["rank"] == 1
        assert "fragment_id" in result
        assert "page" in result
        assert "text" in result
        assert -1.0 <= result["score"] <= 1.0

    def test_top_k_clamped_to_max_8(self, client: TestClient):
        content = b"Confidentiality obligations apply for three years after termination of the agreement."
        doc_id = self._upload_and_reindex(client, content)
        resp = client.get(f"/documents/{doc_id}/vector-search?query=confidentiality&top_k=99")
        assert resp.status_code == 200
        assert resp.json()["top_k"] == 8

    def test_empty_query_returns_400(self, client: TestClient):
        resp = client.post(
            "/documents/upload",
            files={"file": ("t.txt", b"Sample contract text for testing purposes here.")},
        )
        doc_id = resp.json()["id"]
        client.post("/embeddings/reindex", json={"doc_id": doc_id})
        resp = client.get(f"/documents/{doc_id}/vector-search?query=")
        assert resp.status_code == 400

    def test_not_indexed_returns_404(self, client: TestClient):
        resp = client.post(
            "/documents/upload",
            files={"file": ("t.txt", b"Governing law is England and Wales for all disputes.")},
        )
        doc_id = resp.json()["id"]
        resp = client.get(f"/documents/{doc_id}/vector-search?query=governing+law")
        assert resp.status_code == 404

    def test_unknown_document_returns_404(self, client: TestClient):
        resp = client.get("/documents/no-such-doc/vector-search?query=payment")
        assert resp.status_code == 404

    def test_results_sorted_by_score_descending(self, client: TestClient):
        content = (
            b"Payment terms are net thirty days from invoice date.\n\n"
            b"Arbitration shall take place in Berlin under DIS rules and proceedings."
        )
        doc_id = self._upload_and_reindex(client, content)
        resp = client.get(f"/documents/{doc_id}/vector-search?query=payment+invoice&top_k=2")
        results = resp.json()["results"]
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# API: DELETE cleans up embeddings
# ---------------------------------------------------------------------------


class TestDeleteCleansEmbeddings:
    def test_delete_document_removes_embeddings(self, client: TestClient):
        resp = client.post(
            "/documents/upload",
            files={"file": ("del.txt", b"Termination clause requires written notice of thirty days minimum.")},
        )
        doc_id = resp.json()["id"]
        client.post("/embeddings/reindex", json={"doc_id": doc_id})

        # Confirm embeddings exist
        emb_resp = client.get(f"/documents/{doc_id}/embeddings")
        assert emb_resp.status_code == 200

        # Delete document
        del_resp = client.delete(f"/documents/{doc_id}")
        assert del_resp.status_code == 200

        # Embeddings should be gone (document itself is gone → 404 on doc endpoint)
        remaining = get_document_embeddings(doc_id)
        assert remaining == []
