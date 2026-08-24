from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.api.v1.repositories import (
    get_analysis_service,
    get_graph_service,
    get_repository_service,
    get_vector_service,
)
from app.main import app
from app.modules.analysis.chunking import SemanticChunker
from app.modules.analysis.python_ast import PythonAstAnalyzer
from app.modules.analysis.service import SnapshotAnalysisService
from app.modules.embeddings.fake import DeterministicEmbeddingProvider
from app.modules.graph.service import GraphPersistenceService
from app.modules.ingestion.archive import SafeZipExtractor
from app.modules.ingestion.service import RepositoryIngestionService
from app.modules.vector.faiss_store import FaissVectorIndex
from app.modules.vector.service import VectorRetrievalService
from tests.fake_graph import FakeGraphStore
from tests.fakes import FakeGithubClient, InMemoryMetadataStore


def build_archive() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("hello-python-sha/main.py", "def main(): pass")
    return output.getvalue()


@pytest.fixture
def api(tmp_path: Path) -> tuple[TestClient, InMemoryMetadataStore]:
    store = InMemoryMetadataStore()
    github = FakeGithubClient(build_archive())
    extractor = SafeZipExtractor(100, 100_000, 10_000)
    service = RepositoryIngestionService(
        github=github,
        store=store,
        extractor=extractor,
    )
    analysis_service = SnapshotAnalysisService(
        github=github,
        store=store,
        extractor=extractor,
        analyzer=PythonAstAnalyzer(),
    )
    graph_service = GraphPersistenceService(store, analysis_service, FakeGraphStore())
    vector_service = VectorRetrievalService(
        metadata_store=store,
        analyzer=analysis_service,
        chunker=SemanticChunker(8_000),
        embedding_provider=DeterministicEmbeddingProvider(32),
        vector_index=FaissVectorIndex(tmp_path / "vectors"),
    )
    app.dependency_overrides[get_repository_service] = lambda: service
    app.dependency_overrides[get_analysis_service] = lambda: analysis_service
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
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


def test_api_analyzes_an_ingested_snapshot(api: tuple[TestClient, InMemoryMetadataStore]) -> None:
    client, _store = api
    registration = client.post(
        "/api/v1/repositories",
        json={"github_url": "https://github.com/octocat/hello-python"},
    ).json()

    repository_id = registration["repository"]["id"]
    snapshot_id = registration["snapshot"]["id"]
    response = client.post(f"/api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/analysis")

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot_id"] == snapshot_id
    assert [symbol["qualified_name"] for symbol in payload["symbols"]] == [
        "main",
        "main.main",
    ]
    assert payload["diagnostics"] == []


def test_api_persists_graph_and_returns_idempotent_status(
    api: tuple[TestClient, InMemoryMetadataStore],
) -> None:
    client, _store = api
    registration = client.post(
        "/api/v1/repositories",
        json={"github_url": "https://github.com/octocat/hello-python"},
    ).json()
    repository_id = registration["repository"]["id"]
    snapshot_id = registration["snapshot"]["id"]
    path = f"/api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/graph"

    first = client.post(path)
    status_response = client.get(path)
    second = client.post(path)

    assert first.status_code == 200
    assert first.json()["idempotent"] is False
    assert first.json()["node_count"] == 4
    assert first.json()["relationship_count"] == 3
    assert status_response.status_code == 200
    assert status_response.json()["idempotent"] is True
    assert second.status_code == 200
    assert second.json() == status_response.json()


def test_api_builds_searches_and_reuses_vector_index(
    api: tuple[TestClient, InMemoryMetadataStore],
) -> None:
    client, _store = api
    registration = client.post(
        "/api/v1/repositories",
        json={"github_url": "https://github.com/octocat/hello-python"},
    ).json()
    repository_id = registration["repository"]["id"]
    snapshot_id = registration["snapshot"]["id"]
    index_path = f"/api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/vector-index"

    first = client.post(index_path)
    status_response = client.get(index_path)
    repeated = client.post(index_path)
    search = client.post(
        f"/api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/vector-search",
        json={"query": "main function", "top_k": 5},
    )

    assert first.status_code == 200
    assert first.json()["chunk_count"] == 1
    assert first.json()["vector_dimension"] == 32
    assert first.json()["idempotent"] is False
    assert status_response.status_code == 200
    assert status_response.json()["idempotent"] is True
    assert repeated.json() == status_response.json()
    assert search.status_code == 200
    assert len(search.json()["results"]) == 1
    assert search.json()["results"][0]["file_path"] == "main.py"
    assert search.json()["results"][0]["qualified_name"] == "main.main"


def test_api_rejects_search_before_index_and_invalid_top_k(
    api: tuple[TestClient, InMemoryMetadataStore],
) -> None:
    client, _store = api
    registration = client.post(
        "/api/v1/repositories",
        json={"github_url": "https://github.com/octocat/hello-python"},
    ).json()
    repository_id = registration["repository"]["id"]
    snapshot_id = registration["snapshot"]["id"]
    path = f"/api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/vector-search"

    missing = client.post(path, json={"query": "main", "top_k": 1})
    invalid = client.post(path, json={"query": "main", "top_k": 0})

    assert missing.status_code == 404
    assert invalid.status_code == 422


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
