"""
Tests for the streaming Q&A endpoint: POST /documents/{id}/ask/stream

Verifies:
- response is text/event-stream
- event sequence is delta(s) → citations → done
- every delta event carries a "text" string
- the citations event carries a "citations" list
- "done" is always the final event
- non-empty answer produces at least one delta
- 404 for unknown document
- non-streaming /ask still works alongside the stream endpoint
- activity is recorded for streamed questions
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import main, store
from backend.app.main import app
from backend.app.providers import LocalProvider


# ---------------------------------------------------------------------------
# Fixtures (mirror test_api.py pattern)
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
# Helpers
# ---------------------------------------------------------------------------


def _upload(client: TestClient, content: bytes = b"", filename: str = "contract.txt") -> dict:
    if not content:
        content = (
            b"Payment terms are net sixty days from invoice receipt.\n\n"
            b"Either party may terminate this agreement with ninety days written notice.\n\n"
            b"Liability for indirect and consequential damages is fully excluded by both parties."
        )
    resp = client.post(
        "/documents/upload",
        files={"file": (filename, content)},
    )
    assert resp.status_code == 200
    return resp.json()


def _parse_sse(body: str) -> list[dict]:
    """Parse SSE body into a list of event dicts (data lines only)."""
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


# ---------------------------------------------------------------------------
# Content-type and basic shape
# ---------------------------------------------------------------------------


class TestStreamEndpointShape:
    def test_content_type_is_event_stream(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "payment terms"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_cache_control_header_set(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "payment"},
        )
        assert resp.headers.get("cache-control") == "no-cache"

    def test_unknown_document_returns_404(self, client: TestClient):
        resp = client.post(
            "/documents/no-such-id/ask/stream",
            json={"question": "anything"},
        )
        assert resp.status_code == 404

    def test_response_body_is_non_empty(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "termination notice"},
        )
        assert len(resp.text) > 0


# ---------------------------------------------------------------------------
# Event sequence
# ---------------------------------------------------------------------------


class TestStreamEventSequence:
    def test_final_event_is_done(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "payment terms"},
        )
        events = _parse_sse(resp.text)
        assert events, "no SSE events parsed"
        assert events[-1]["type"] == "done"

    def test_second_to_last_event_is_citations(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "payment terms"},
        )
        events = _parse_sse(resp.text)
        assert len(events) >= 2
        assert events[-2]["type"] == "citations"

    def test_delta_events_precede_citations(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "payment"},
        )
        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        # All events before the last two must be deltas
        for t in types[:-2]:
            assert t == "delta", f"unexpected event type before citations: {t!r}"

    def test_at_least_one_delta_for_answerable_question(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "payment terms invoice"},
        )
        events = _parse_sse(resp.text)
        delta_events = [e for e in events if e["type"] == "delta"]
        assert len(delta_events) >= 1

    def test_exactly_one_citations_event(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "termination"},
        )
        events = _parse_sse(resp.text)
        citations_events = [e for e in events if e["type"] == "citations"]
        assert len(citations_events) == 1

    def test_exactly_one_done_event(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "liability damages"},
        )
        events = _parse_sse(resp.text)
        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1


# ---------------------------------------------------------------------------
# Delta event payload
# ---------------------------------------------------------------------------


class TestDeltaEventPayload:
    def test_delta_events_have_text_field(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "payment terms"},
        )
        events = _parse_sse(resp.text)
        for event in events:
            if event["type"] == "delta":
                assert "text" in event, "delta event missing 'text' field"

    def test_delta_text_values_are_strings(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "termination notice"},
        )
        events = _parse_sse(resp.text)
        for event in events:
            if event["type"] == "delta":
                assert isinstance(event["text"], str)

    def test_reassembled_answer_is_non_empty(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "payment invoice"},
        )
        events = _parse_sse(resp.text)
        full_text = "".join(e["text"] for e in events if e["type"] == "delta")
        assert full_text.strip() != ""

    def test_reassembled_answer_matches_non_stream_answer(self, client: TestClient):
        """Stream and non-stream endpoints produce the same answer text."""
        doc = _upload(client)
        question = "payment terms"

        stream_resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": question},
        )
        events = _parse_sse(stream_resp.text)
        streamed_answer = "".join(e["text"] for e in events if e["type"] == "delta")

        ask_resp = client.post(
            f"/documents/{doc['id']}/ask",
            json={"question": question},
        )
        assert ask_resp.status_code == 200
        direct_answer = ask_resp.json()["answer"]

        assert streamed_answer.strip() == direct_answer.strip()


# ---------------------------------------------------------------------------
# Citations event payload
# ---------------------------------------------------------------------------


class TestCitationsEventPayload:
    def test_citations_field_is_list(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "payment terms"},
        )
        events = _parse_sse(resp.text)
        cit_event = next(e for e in events if e["type"] == "citations")
        assert isinstance(cit_event["citations"], list)

    def test_citation_objects_have_expected_fields(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "payment invoice net"},
        )
        events = _parse_sse(resp.text)
        cit_event = next(e for e in events if e["type"] == "citations")
        for citation in cit_event["citations"]:
            assert "id" in citation
            assert "page" in citation
            assert "text" in citation

    def test_stream_citations_match_ask_citations(self, client: TestClient):
        """Citations from /ask/stream and /ask should agree."""
        doc = _upload(client)
        question = "termination notice"

        stream_resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": question},
        )
        events = _parse_sse(stream_resp.text)
        stream_citation_ids = {
            c["id"]
            for e in events if e["type"] == "citations"
            for c in e["citations"]
        }

        ask_resp = client.post(
            f"/documents/{doc['id']}/ask",
            json={"question": question},
        )
        ask_citation_ids = {c["id"] for c in ask_resp.json()["citations"]}

        assert stream_citation_ids == ask_citation_ids


# ---------------------------------------------------------------------------
# Activity recording
# ---------------------------------------------------------------------------


class TestStreamActivityRecording:
    def test_stream_records_question_activity(self, client: TestClient):
        doc = _upload(client)
        client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "liability cap"},
        )
        updated = client.get(f"/documents/{doc['id']}").json()
        activity_types = [a["type"] for a in updated["activity"]]
        assert "question" in activity_types

    def test_stream_activity_detail_contains_question(self, client: TestClient):
        doc = _upload(client)
        question_text = "governing law arbitration"
        client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": question_text},
        )
        updated = client.get(f"/documents/{doc['id']}").json()
        question_activities = [a for a in updated["activity"] if a["type"] == "question"]
        assert any(question_text in a["detail"] for a in question_activities)


# ---------------------------------------------------------------------------
# Non-streaming /ask endpoint still works
# ---------------------------------------------------------------------------


class TestNonStreamingAskStillWorks:
    def test_ask_returns_200_with_answer(self, client: TestClient):
        doc = _upload(client)
        resp = client.post(
            f"/documents/{doc['id']}/ask",
            json={"question": "payment terms"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "answer" in body
        assert "citations" in body
        assert isinstance(body["citations"], list)

    def test_ask_and_stream_coexist_for_same_document(self, client: TestClient):
        doc = _upload(client)

        ask_resp = client.post(
            f"/documents/{doc['id']}/ask",
            json={"question": "termination"},
        )
        assert ask_resp.status_code == 200

        stream_resp = client.post(
            f"/documents/{doc['id']}/ask/stream",
            json={"question": "termination"},
        )
        assert stream_resp.status_code == 200
        events = _parse_sse(stream_resp.text)
        assert events[-1]["type"] == "done"
