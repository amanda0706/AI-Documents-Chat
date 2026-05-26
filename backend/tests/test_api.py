from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app


@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(store, "INDEX_FILE", tmp_path / "documents.json")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def upload_contract(client: TestClient, filename: str = "agreement.txt") -> dict:
    response = client.post(
        "/documents/upload",
        files={"file": (filename, b"Payment terms are net 60 days. Either party may terminate with 90 days notice.")},
    )
    assert response.status_code == 200
    return response.json()


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_document_review_flow_through_api(client: TestClient) -> None:
    document = upload_contract(client)
    document_id = document["id"]

    ask_response = client.post(f"/documents/{document_id}/ask", json={"question": "What are the payment terms?"})
    share_response = client.post(f"/documents/{document_id}/share", json={"email": "anna@example.com"})
    status_response = client.post(f"/documents/{document_id}/status", json={"status": "in_review"})
    metadata_response = client.post(
        f"/documents/{document_id}/metadata",
        json={
            "owner": "anna@example.com",
            "counterparty": "Northwind Labs",
            "contract_type": "MSA",
            "effective_date": "2026-01-01",
            "expiry_date": "2026-12-31",
            "renewal_date": "2026-11-30",
        },
    )
    report_response = client.get(f"/documents/{document_id}/report")

    assert ask_response.status_code == 200
    assert ask_response.json()["citations"]
    assert share_response.status_code == 200
    assert share_response.json()["shared_with"] == ["anna@example.com"]
    assert status_response.status_code == 200
    assert status_response.json()["review_status"] == "in_review"
    assert metadata_response.status_code == 200
    assert metadata_response.json()["counterparty"] == "Northwind Labs"
    assert report_response.status_code == 200
    assert "# Contract Review Report" in report_response.json()["markdown"]


def test_api_rejects_invalid_status_and_invalid_metadata_dates(client: TestClient) -> None:
    document = upload_contract(client)
    document_id = document["id"]

    invalid_status = client.post(f"/documents/{document_id}/status", json={"status": "waiting"})
    invalid_date = client.post(f"/documents/{document_id}/metadata", json={"expiry_date": "2026-99-99"})

    assert invalid_status.status_code == 422
    assert invalid_date.status_code == 422


def test_compare_endpoint_returns_document_differences(client: TestClient) -> None:
    first = upload_contract(client, "msa.txt")
    second_response = client.post(
        "/documents/upload",
        files={"file": ("supplier.txt", b"Payment terms are net 30 days. Either party may terminate with 30 days notice.")},
    )
    assert second_response.status_code == 200
    second = second_response.json()

    response = client.post("/compare", json={"left_id": first["id"], "right_id": second["id"]})

    assert response.status_code == 200
    assert response.json()["differences"]


def test_bulk_upload_creates_multiple_documents(client: TestClient) -> None:
    response = client.post(
        "/documents/bulk-upload",
        files=[
            ("files", ("msa.txt", b"Payment terms are net 60 days.")),
            ("files", ("supplier.txt", b"Payment terms are net 30 days.")),
        ],
    )

    assert response.status_code == 200
    assert [item["filename"] for item in response.json()] == ["msa.txt", "supplier.txt"]


def test_delete_document_removes_it_from_collection(client: TestClient) -> None:
    document = upload_contract(client)

    delete_response = client.delete(f"/documents/{document['id']}")
    list_response = client.get("/documents")
    missing_response = client.get(f"/documents/{document['id']}")

    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"
    assert all(item["id"] != document["id"] for item in list_response.json())
    assert missing_response.status_code == 404


def test_upload_accepts_owner_metadata(client: TestClient) -> None:
    response = client.post(
        "/documents/upload",
        data={"owner": "owner@example.com"},
        files={"file": ("owned.txt", b"Payment terms are net 60 days.")},
    )

    assert response.status_code == 200
    assert response.json()["owner"] == "owner@example.com"


def test_upload_rejects_empty_and_large_files(client: TestClient) -> None:
    empty_response = client.post(
        "/documents/upload",
        files={"file": ("empty.txt", b"")},
    )
    large_response = client.post(
        "/documents/upload",
        files={"file": ("large.txt", b"x" * (5 * 1024 * 1024 + 1))},
    )

    assert empty_response.status_code == 400
    assert large_response.status_code == 413


def test_upload_sanitizes_filename(client: TestClient) -> None:
    response = client.post(
        "/documents/upload",
        files={"file": ("../Unsafe Contract 2026.txt", b"Payment terms are net 60 days.")},
    )

    assert response.status_code == 200
    assert response.json()["filename"] == "Unsafe-Contract-2026.txt"


def test_retrieval_endpoint_returns_ranked_context(client: TestClient) -> None:
    document = upload_contract(client)

    response = client.get(f"/documents/{document['id']}/retrieval", params={"query": "payment terms", "top_k": 2})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "payment terms"
    assert payload["matches"]
    assert "Source page" in payload["context"]


def test_metrics_endpoint_reports_operational_snapshot(client: TestClient) -> None:
    document = upload_contract(client, "metrics-contract.txt")
    client.post(f"/documents/{document['id']}/comments", json={"author": "qa@example.com", "body": "Looks risky."})

    response = client.get("/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "luminaclause-api"
    assert payload["total_documents"] == 1
    assert payload["total_fragments"] >= 1
    assert payload["comments_count"] == 1
    assert payload["activity_events"] >= 2
    assert payload["latest_upload_filename"] == "metrics-contract.txt"
