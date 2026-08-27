from typing import Protocol

from app.core.errors import (
    RepositoryNotFoundError,
    SnapshotNotFoundError,
    VectorIndexNotFoundError,
)
from app.domain.repositories import RepositoryMetadata, SnapshotMetadata
from app.domain.vector import (
    VectorIndexSpec,
    VectorIndexStatus,
    VectorSearchRequest,
    VectorSearchResponse,
)
from app.modules.analysis.chunking import SemanticChunker, chunk_embedding_text
from app.modules.analysis.service import AnalyzedSnapshotSource
from app.modules.embeddings.port import EmbeddingProvider
from app.modules.ingestion.store import MetadataStore
from app.modules.operations.port import NULL_OPERATION_REPORTER, OperationReporter
from app.modules.vector.faiss_store import INDEX_VERSION
from app.modules.vector.port import VectorIndex


class SnapshotSourceAnalyzer(Protocol):
    def analyze_snapshot_source(
        self, repository_id: str, snapshot_id: str
    ) -> AnalyzedSnapshotSource: ...


class VectorRetrievalService:
    """Orchestrate immutable snapshot analysis, chunking, embedding, and retrieval."""

    def __init__(
        self,
        metadata_store: MetadataStore,
        analyzer: SnapshotSourceAnalyzer,
        chunker: SemanticChunker,
        embedding_provider: EmbeddingProvider,
        vector_index: VectorIndex,
    ) -> None:
        self._metadata_store = metadata_store
        self._analyzer = analyzer
        self._chunker = chunker
        self._embedding_provider = embedding_provider
        self._vector_index = vector_index

    def build_index(
        self,
        repository_id: str,
        snapshot_id: str,
        reporter: OperationReporter | None = None,
    ) -> VectorIndexStatus:
        active_reporter = reporter or NULL_OPERATION_REPORTER
        if reporter is not None:
            active_reporter.start_stage("vector")
        try:
            repository, snapshot = self._get_snapshot(repository_id, snapshot_id)
            spec = self._spec(repository.id, snapshot.id, snapshot.commit_sha)
            existing = self._vector_index.get_status(spec)
            if existing is not None:
                status = existing.model_copy(update={"idempotent": True})
            else:
                analysis_event = active_reporter.start_event(
                    "vector", "Loading analyzed snapshot source"
                )
                analyzed = self._analyzer.analyze_snapshot_source(repository_id, snapshot_id)
                active_reporter.complete_event(analysis_event)
                chunks_event = active_reporter.start_event(
                    "vector", "Generating evidence-preserving semantic chunks"
                )
                chunks = self._chunker.build_chunks(
                    analyzed.repository,
                    analyzed.snapshot,
                    analyzed.analysis,
                    analyzed.sources,
                )
                active_reporter.complete_event(
                    chunks_event,
                    metric_key="chunks",
                    metric_label="Chunks",
                    metric_value=len(chunks),
                )
                embedding_event = active_reporter.start_event(
                    "vector", "Generating embedding vectors"
                )
                vectors = self._embedding_provider.embed_documents(
                    [chunk_embedding_text(chunk) for chunk in chunks]
                )
                active_reporter.complete_event(
                    embedding_event,
                    metric_key="vectors",
                    metric_label="Vectors",
                    metric_value=len(vectors),
                )
                index_event = active_reporter.start_event(
                    "vector", "Constructing and persisting FAISS index artifacts"
                )
                status = self._vector_index.build_index(spec, chunks, vectors)
                active_reporter.complete_event(
                    index_event,
                    metric_key="index_vectors",
                    metric_label="FAISS vectors",
                    metric_value=status.chunk_count,
                )
        except Exception:
            if reporter is not None:
                active_reporter.fail_stage("vector")
            raise
        if reporter is not None:
            active_reporter.complete_stage(
                "vector",
                {
                    "chunks": ("Chunks", status.chunk_count),
                    "vectors": ("Vectors", status.chunk_count),
                    "dimension": ("Dimensions", status.vector_dimension),
                    "faiss_vectors": ("FAISS vectors", status.chunk_count),
                },
            )
        return status

    def get_status(self, repository_id: str, snapshot_id: str) -> VectorIndexStatus:
        repository, snapshot = self._get_snapshot(repository_id, snapshot_id)
        status = self._vector_index.get_status(
            self._spec(repository.id, snapshot.id, snapshot.commit_sha)
        )
        if status is None:
            raise VectorIndexNotFoundError("Vector index was not found")
        return status

    def search(
        self,
        repository_id: str,
        snapshot_id: str,
        request: VectorSearchRequest,
    ) -> VectorSearchResponse:
        repository, snapshot = self._get_snapshot(repository_id, snapshot_id)
        spec = self._spec(repository.id, snapshot.id, snapshot.commit_sha)
        if self._vector_index.get_status(spec) is None:
            raise VectorIndexNotFoundError("Vector index was not found")
        query_vector = self._embedding_provider.embed_query(request.query)
        return self._vector_index.search(
            spec,
            request.query,
            query_vector,
            request.top_k,
        )

    def _spec(self, repository_id: str, snapshot_id: str, commit_sha: str) -> VectorIndexSpec:
        return VectorIndexSpec(
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            commit_sha=commit_sha,
            embedding_provider=self._embedding_provider.provider_name,
            embedding_model=self._embedding_provider.model_name,
            vector_dimension=self._embedding_provider.dimension,
            chunking_version=self._chunker.version,
            index_version=INDEX_VERSION,
        )

    def _get_snapshot(
        self, repository_id: str, snapshot_id: str
    ) -> tuple[RepositoryMetadata, SnapshotMetadata]:
        repository = self._metadata_store.get_repository(repository_id)
        if repository is None:
            raise RepositoryNotFoundError("Repository was not found")
        snapshot = self._metadata_store.get_snapshot(repository_id, snapshot_id)
        if snapshot is None:
            raise SnapshotNotFoundError("Snapshot was not found")
        return repository, snapshot
