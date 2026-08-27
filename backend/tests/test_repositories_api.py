from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.api.v1.repositories import (
    get_analysis_service,
    get_graph_service,
    get_hybrid_retriever,
    get_question_service,
    get_repository_service,
    get_vector_service,
)
from app.core.errors import MalformedReasoningOutputError
from app.main import app
from app.modules.ai.fake import DeterministicReasoningProvider
from app.modules.analysis.chunking import SemanticChunker
from app.modules.analysis.python_ast import PythonAstAnalyzer
from app.modules.analysis.service import SnapshotAnalysisService
from app.modules.embeddings.fake import DeterministicEmbeddingProvider
from app.modules.graph.service import GraphPersistenceService
from app.modules.ingestion.archive import SafeZipExtractor
from app.modules.ingestion.service import RepositoryIngestionService
from app.modules.qa.service import RepositoryQuestionService
from app.modules.retrieval.service import HybridRetriever
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
    graph_store = FakeGraphStore()
    graph_service = GraphPersistenceService(store, analysis_service, graph_store)
    vector_service = VectorRetrievalService(
        metadata_store=store,
        analyzer=analysis_service,
        chunker=SemanticChunker(8_000),
        embedding_provider=DeterministicEmbeddingProvider(32),
        vector_index=FaissVectorIndex(tmp_path / "vectors"),
    )
    hybrid_retriever = HybridRetriever(vector_service, graph_store)
    question_service = RepositoryQuestionService(
        snapshot_reader=store,
        hybrid_searcher=hybrid_retriever,
        reasoning_provider=DeterministicReasoningProvider(),
    )
    app.dependency_overrides[get_repository_service] = lambda: service
    app.dependency_overrides[get_analysis_service] = lambda: analysis_service
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_hybrid_retriever] = lambda: hybrid_retriever
    app.dependency_overrides[get_question_service] = lambda: question_service
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


def test_api_exposes_only_real_ingestion_events_and_metrics(
    api: tuple[TestClient, InMemoryMetadataStore],
) -> None:
    client, _store = api
    operation_id = "ingestion-observability"

    response = client.post(
        "/api/v1/repositories",
        json={"github_url": "https://github.com/octocat/hello-python"},
        headers={"X-CodeGraph-Operation-ID": operation_id},
    )
    operation = client.get(f"/api/v1/operations/{operation_id}")

    assert response.status_code == 201
    assert response.headers["X-CodeGraph-Operation-ID"] == operation_id
    assert operation.status_code == 200
    payload = operation.json()
    assert payload["stages"] == {
        "ingestion": "complete",
        "analysis": "pending",
        "graph": "pending",
        "vector": "pending",
    }
    assert {event["stage"] for event in payload["events"]} == {"ingestion"}
    assert all(event["status"] == "done" for event in payload["events"])
    assert "Parsing Python ASTs" not in {event["message"] for event in payload["events"]}
    assert payload["metrics"]["ingestion"] == [
        {"key": "python_files", "label": "Python files", "value": 1}
    ]


def test_api_operation_events_survive_across_pipeline_requests(
    api: tuple[TestClient, InMemoryMetadataStore],
) -> None:
    client, _store = api
    operation_id = "cross-request-operation"
    headers = {"X-CodeGraph-Operation-ID": operation_id}
    registration = client.post(
        "/api/v1/repositories",
        json={"github_url": "https://github.com/octocat/hello-python"},
        headers=headers,
    ).json()
    first_read = client.get(f"/api/v1/operations/{operation_id}").json()

    repository_id = registration["repository"]["id"]
    snapshot_id = registration["snapshot"]["id"]
    analysis = client.post(
        f"/api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/analysis",
        headers=headers,
    )
    second_read = client.get(f"/api/v1/operations/{operation_id}")

    assert analysis.status_code == 200
    assert second_read.status_code == 200
    assert {event["id"] for event in first_read["events"]}.issubset(
        {event["id"] for event in second_read.json()["events"]}
    )
    assert {event["stage"] for event in second_read.json()["events"]} == {
        "ingestion",
        "analysis",
    }


def test_api_returns_404_for_unknown_operation(
    api: tuple[TestClient, InMemoryMetadataStore],
) -> None:
    client, _store = api

    response = client.get("/api/v1/operations/unknown-operation-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "Pipeline operation was not found"


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_repository_registration_cors_preflight_succeeds(
    api: tuple[TestClient, InMemoryMetadataStore],
    origin: str,
) -> None:
    client, _store = api

    response = client.options(
        "/api/v1/repositories",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-codegraph-operation-id",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "x-codegraph-operation-id" in response.headers["access-control-allow-headers"].lower()


def test_api_pipeline_operation_reports_accurate_metrics_and_graph_preview(
    api: tuple[TestClient, InMemoryMetadataStore],
) -> None:
    client, _store = api
    operation_id = "complete-pipeline-observability"
    headers = {"X-CodeGraph-Operation-ID": operation_id}
    registration = client.post(
        "/api/v1/repositories",
        json={"github_url": "https://github.com/octocat/hello-python"},
        headers=headers,
    ).json()
    repository_id = registration["repository"]["id"]
    snapshot_id = registration["snapshot"]["id"]
    base = f"/api/v1/repositories/{repository_id}/snapshots/{snapshot_id}"

    client.post(f"{base}/analysis", headers=headers)
    graph = client.post(f"{base}/graph", headers=headers).json()
    vector = client.post(f"{base}/vector-index", headers=headers).json()
    operation = client.get(f"/api/v1/operations/{operation_id}").json()
    preview = client.get(f"{base}/graph-preview?max_nodes=60")

    assert operation["status"] == "complete"
    assert set(operation["stages"].values()) == {"complete"}
    metrics = {
        stage: {metric["key"]: metric["value"] for metric in values}
        for stage, values in operation["metrics"].items()
    }
    assert metrics["analysis"] == {
        "python_files": 1,
        "classes": 0,
        "functions": 1,
        "methods": 0,
        "imports": 0,
        "inheritances": 0,
        "resolved_calls": 0,
        "diagnostics": 0,
    }
    assert metrics["graph"]["nodes"] == graph["node_count"] == 4
    assert metrics["graph"]["relationships"] == graph["relationship_count"] == 3
    assert metrics["vector"]["chunks"] == vector["chunk_count"] == 1
    assert metrics["vector"]["vectors"] == vector["chunk_count"]
    assert metrics["vector"]["dimension"] == vector["vector_dimension"] == 32
    assert preview.status_code == 200
    assert len(preview.json()["nodes"]) == 3
    assert len(preview.json()["relationships"]) == 2
    assert all(node["repository_id"] == repository_id for node in preview.json()["nodes"])
    assert all(node["snapshot_id"] == snapshot_id for node in preview.json()["nodes"])


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


def test_api_hybrid_search_success_and_error_behavior(
    api: tuple[TestClient, InMemoryMetadataStore],
) -> None:
    client, _store = api
    registration = client.post(
        "/api/v1/repositories",
        json={"github_url": "https://github.com/octocat/hello-python"},
    ).json()
    repository_id = registration["repository"]["id"]
    snapshot_id = registration["snapshot"]["id"]
    path = f"/api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/hybrid-search"

    missing = client.post(path, json={"query": "main function", "top_k": 1})
    invalid = client.post(path, json={"query": "main function", "top_k": 0})
    client.post(f"/api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/vector-index")
    success = client.post(path, json={"query": "main.py main", "top_k": 1})

    assert missing.status_code == 404
    assert invalid.status_code == 422
    assert success.status_code == 200
    payload = success.json()
    assert payload["repository_id"] == repository_id
    assert payload["snapshot_id"] == snapshot_id
    assert payload["metadata"]["outcome"] == "sufficient"
    assert payload["metadata"]["returned_count"] == 1
    assert payload["evidence"][0]["file_path"] == "main.py"
    assert "exact_file_path" in payload["evidence"][0]["retrieval_reasons"]


def test_api_repository_qa_returns_grounded_snapshot_evidence(
    api: tuple[TestClient, InMemoryMetadataStore],
) -> None:
    client, _store = api
    registration = client.post(
        "/api/v1/repositories",
        json={"github_url": "https://github.com/octocat/hello-python"},
    ).json()
    repository_id = registration["repository"]["id"]
    snapshot_id = registration["snapshot"]["id"]
    client.post(f"/api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/vector-index")

    response = client.post(
        f"/api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/ask",
        json={"question": "What does the main function do?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome"] == "answered"
    assert payload["snapshot_id"] == snapshot_id
    assert payload["commit_sha"] == "a" * 40
    assert payload["cited_evidence_ids"] == ["E1"]
    assert payload["evidence"][0]["evidence_id"] == "E1"
    assert payload["evidence"][0]["file_path"] == "main.py"
    assert payload["evidence"][0]["symbol_name"] == "main"


def test_api_repository_qa_validation_and_missing_index_errors(
    api: tuple[TestClient, InMemoryMetadataStore],
) -> None:
    client, _store = api
    registration = client.post(
        "/api/v1/repositories",
        json={"github_url": "https://github.com/octocat/hello-python"},
    ).json()
    repository_id = registration["repository"]["id"]
    snapshot_id = registration["snapshot"]["id"]
    path = f"/api/v1/repositories/{repository_id}/snapshots/{snapshot_id}/ask"

    blank = client.post(path, json={"question": "   "})
    missing_index = client.post(path, json={"question": "What does main do?"})

    assert blank.status_code == 422
    assert missing_index.status_code == 404


def test_api_repository_qa_maps_malformed_provider_output_to_bad_gateway(
    api: tuple[TestClient, InMemoryMetadataStore],
) -> None:
    client, _store = api

    class MalformedQuestionService:
        def ask(self, *args: object) -> None:
            raise MalformedReasoningOutputError("malformed structured output")

    original_override = app.dependency_overrides[get_question_service]
    app.dependency_overrides[get_question_service] = lambda: MalformedQuestionService()
    try:
        response = client.post(
            "/api/v1/repositories/repository-1/snapshots/snapshot-1/ask",
            json={"question": "How does it work?"},
        )
    finally:
        app.dependency_overrides[get_question_service] = original_override

    assert response.status_code == 502
    assert response.json()["detail"] == "malformed structured output"


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
