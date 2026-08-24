from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.api.v1.repositories import get_repository_service
from app.main import app
from app.modules.ingestion.archive import SafeZipExtractor
from app.modules.ingestion.service import RepositoryIngestionService
from tests.fakes import FakeGithubClient, InMemoryMetadataStore


def build_archive() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("hello-python-sha/main.py", "def main(): pass")
    return output.getvalue()


@pytest.fixture
def api() -> tuple[TestClient, InMemoryMetadataStore]:
    store = InMemoryMetadataStore()
    service = RepositoryIngestionService(
        github=FakeGithubClient(build_archive()),
        store=store,
        extractor=SafeZipExtractor(100, 100_000, 10_000),
    )
    app.dependency_overrides[get_repository_service] = lambda: service
    with TestClient(app) as client:
        yield client, store
    app.dependency_overrides.clear()


def test_register_and_fetch_repository_snapshot(
    api: tuple[TestClient, InMemoryMetadataStore],
) -> None:
    client, _store = api

    registration = client.post(
        "/api/v1/repositories",
        json={"github_url": "https://github.com/octocat/hello-python"},
    )

    assert registration.status_code == 201
    payload = registration.json()
    assert payload["idempotent"] is False
    assert payload["repository"]["owner"] == "octocat"
    assert payload["snapshot"]["status"] == "ready"
    assert payload["snapshot"]["discovered_file_count"] == 1

    repository_id = payload["repository"]["id"]
    snapshot_id = payload["snapshot"]["id"]
    repository = client.get(f"/api/v1/repositories/{repository_id}")
    snapshot = client.get(f"/api/v1/repositories/{repository_id}/snapshots/{snapshot_id}")

    assert repository.status_code == 200
    assert repository.json()["github_url"] == "https://github.com/octocat/hello-python"
    assert snapshot.status_code == 200
    assert snapshot.json()["commit_sha"] == "a" * 40


def test_api_registration_is_idempotent(api: tuple[TestClient, InMemoryMetadataStore]) -> None:
    client, _store = api
    request = {"github_url": "https://github.com/octocat/hello-python", "ref": "main"}

    first = client.post("/api/v1/repositories", json=request)
    second = client.post("/api/v1/repositories", json=request)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["idempotent"] is True
    assert first.json()["snapshot"]["id"] == second.json()["snapshot"]["id"]


def test_api_rejects_invalid_repository_url(api: tuple[TestClient, InMemoryMetadataStore]) -> None:
    client, _store = api

    response = client.post(
        "/api/v1/repositories",
        json={"github_url": "https://example.com/octocat/hello-python"},
    )

    assert response.status_code == 422
    assert "github.com" in response.json()["detail"]


def test_api_rejects_unsafe_archive_and_records_failed_snapshot() -> None:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("../escape.py", "print('unsafe')")

    store = InMemoryMetadataStore()
    service = RepositoryIngestionService(
        github=FakeGithubClient(output.getvalue()),
        store=store,
        extractor=SafeZipExtractor(100, 100_000, 10_000),
    )
    app.dependency_overrides[get_repository_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/repositories",
                json={"github_url": "https://github.com/octocat/hello-python"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "Repository archive contains path traversal"
    failed_snapshot = next(iter(store.snapshots.values()))
    assert failed_snapshot.status == "failed"
    assert failed_snapshot.errors


def test_api_returns_404_for_unknown_metadata(
    api: tuple[TestClient, InMemoryMetadataStore],
) -> None:
    client, _store = api

    repository = client.get("/api/v1/repositories/missing")
    snapshot = client.get("/api/v1/repositories/missing/snapshots/missing")

    assert repository.status_code == 404
    assert snapshot.status_code == 404
