import json
from pathlib import Path

import pytest

from app.core.errors import VectorIndexCorruptError, VectorIndexNotFoundError
from app.domain.vector import CodeChunk, VectorIndexSpec
from app.modules.analysis.chunking import chunk_embedding_text
from app.modules.embeddings.fake import DeterministicEmbeddingProvider
from app.modules.vector.faiss_store import INDEX_VERSION, FaissVectorIndex


def _spec(snapshot_id: str = "snapshot-1") -> VectorIndexSpec:
    return VectorIndexSpec(
        repository_id="repository-1",
        snapshot_id=snapshot_id,
        commit_sha="a" * 40,
        embedding_provider="deterministic-local",
        embedding_model="hashed-token-v1",
        vector_dimension=64,
        chunking_version="python-semantic-v1",
        index_version=INDEX_VERSION,
    )


def _chunks(snapshot_id: str = "snapshot-1") -> list[CodeChunk]:
    return [
        CodeChunk(
            id=f"chunk-{index}",
            repository_id="repository-1",
            snapshot_id=snapshot_id,
            commit_sha="a" * 40,
            file_path=file_path,
            symbol_id=f"symbol-{index}",
            symbol_name=symbol,
            qualified_name=f"module.{symbol}",
            symbol_type="function",
            start_line=index * 10 + 1,
            end_line=index * 10 + 3,
            content=content,
            chunking_version="python-semantic-v1",
        )
        for index, (file_path, symbol, content) in enumerate(
            (
                (
                    "auth.py",
                    "authenticate",
                    "def authenticate(token):\n    validate token credential",
                ),
                ("cache.py", "cache_result", "def cache_result(value):\n    store cached value"),
                ("graph.py", "neighbors", "def neighbors(symbol):\n    traverse graph edges"),
            )
        )
    ]


def _build(root: Path) -> tuple[FaissVectorIndex, VectorIndexSpec]:
    index = FaissVectorIndex(root)
    spec = _spec()
    chunks = _chunks()
    provider = DeterministicEmbeddingProvider(spec.vector_dimension)
    vectors = provider.embed_documents([chunk_embedding_text(chunk) for chunk in chunks])
    status = index.build_index(spec, chunks, vectors)
    assert status.idempotent is False
    return index, spec


def test_creates_persists_reloads_and_searches_exact_index(tmp_path: Path) -> None:
    _index, spec = _build(tmp_path)
    reloaded = FaissVectorIndex(tmp_path)
    provider = DeterministicEmbeddingProvider(spec.vector_dimension)

    status = reloaded.get_status(spec)
    response = reloaded.search(
        spec,
        "authenticate token credential",
        provider.embed_query("authenticate token credential"),
        2,
    )

    assert status is not None
    assert status.chunk_count == 3
    assert status.vector_dimension == 64
    assert status.idempotent is True
    assert len(response.results) == 2
    assert response.results[0].file_path == "auth.py"
    assert response.results[0].symbol_name == "authenticate"
    assert all(result.chunk_id in {"chunk-0", "chunk-1", "chunk-2"} for result in response.results)


def test_build_is_idempotent_for_same_snapshot_and_configuration(tmp_path: Path) -> None:
    index, spec = _build(tmp_path)
    chunks = _chunks()
    provider = DeterministicEmbeddingProvider(spec.vector_dimension)

    repeated = index.build_index(
        spec,
        chunks,
        provider.embed_documents([chunk_embedding_text(chunk) for chunk in chunks]),
    )

    assert repeated.idempotent is True
    assert repeated.chunk_count == 3


def test_snapshot_isolation_and_missing_index_behavior(tmp_path: Path) -> None:
    index, spec = _build(tmp_path)
    other_spec = _spec("snapshot-2")
    provider = DeterministicEmbeddingProvider(spec.vector_dimension)

    assert index.get_status(other_spec) is None
    with pytest.raises(VectorIndexNotFoundError, match="not found"):
        index.search(other_spec, "query", provider.embed_query("query"), 1)

    response = index.search(spec, "query", provider.embed_query("query"), 10)
    assert len(response.results) == 3
    assert response.snapshot_id == "snapshot-1"


def test_rejects_invalid_top_k(tmp_path: Path) -> None:
    index, spec = _build(tmp_path)
    provider = DeterministicEmbeddingProvider(spec.vector_dimension)

    with pytest.raises(ValueError, match="top_k"):
        index.search(spec, "query", provider.embed_query("query"), 0)


def test_detects_corrupt_or_mismatched_manifest(tmp_path: Path) -> None:
    index, spec = _build(tmp_path)
    manifest_path = next(tmp_path.rglob("manifest.json"))
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["repository_id"] = "different-repository"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(VectorIndexCorruptError, match="repository_id"):
        index.get_status(spec)


def test_missing_and_malformed_manifests_are_distinct(tmp_path: Path) -> None:
    index = FaissVectorIndex(tmp_path)
    spec = _spec()
    assert index.get_status(spec) is None

    _build(tmp_path)
    manifest_path = next(tmp_path.rglob("manifest.json"))
    manifest_path.write_text("not-json", encoding="utf-8")

    with pytest.raises(VectorIndexCorruptError, match="corrupt"):
        index.get_status(spec)
