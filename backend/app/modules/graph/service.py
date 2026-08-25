from typing import Protocol

from app.core.errors import (
    GraphSnapshotNotFoundError,
    RepositoryNotFoundError,
    SnapshotNotFoundError,
)
from app.domain.analysis import SnapshotAnalysis
from app.domain.graph import GraphNeighborhood, GraphNode, GraphPersistenceStatus
from app.domain.repositories import RepositoryMetadata, SnapshotMetadata
from app.modules.graph.port import GraphStore
from app.modules.ingestion.store import MetadataStore


class SnapshotAnalyzer(Protocol):
    def analyze_snapshot(self, repository_id: str, snapshot_id: str) -> SnapshotAnalysis: ...


class GraphPersistenceService:
    """Run deterministic snapshot analysis and persist/query its code graph."""

    def __init__(
        self,
        metadata_store: MetadataStore,
        analyzer: SnapshotAnalyzer,
        graph_store: GraphStore,
    ) -> None:
        self._metadata_store = metadata_store
        self._analyzer = analyzer
        self._graph_store = graph_store

    def analyze_and_persist(self, repository_id: str, snapshot_id: str) -> GraphPersistenceStatus:
        repository, snapshot = self._get_snapshot(repository_id, snapshot_id)
        existing = self._graph_store.get_persistence_status(repository_id, snapshot_id)
        if existing is not None:
            return existing.model_copy(update={"idempotent": True})
        analysis = self._analyzer.analyze_snapshot(repository_id, snapshot_id)
        return self._graph_store.persist_snapshot(repository, snapshot, analysis)

    def get_status(self, repository_id: str, snapshot_id: str) -> GraphPersistenceStatus:
        self._get_snapshot(repository_id, snapshot_id)
        graph_status = self._graph_store.get_persistence_status(repository_id, snapshot_id)
        if graph_status is None:
            raise GraphSnapshotNotFoundError("Snapshot graph was not found")
        return graph_status

    def get_symbol(self, repository_id: str, snapshot_id: str, symbol_id: str) -> GraphNode | None:
        return self._graph_store.get_symbol(repository_id, snapshot_id, symbol_id)

    def get_containment(
        self, repository_id: str, snapshot_id: str, node_id: str
    ) -> list[GraphNode]:
        return self._graph_store.get_containment(repository_id, snapshot_id, node_id)

    def get_callers(self, repository_id: str, snapshot_id: str, symbol_id: str) -> list[GraphNode]:
        return self._graph_store.get_callers(repository_id, snapshot_id, symbol_id)

    def get_callees(self, repository_id: str, snapshot_id: str, symbol_id: str) -> list[GraphNode]:
        return self._graph_store.get_callees(repository_id, snapshot_id, symbol_id)

    def get_imports(self, repository_id: str, snapshot_id: str, file_id: str) -> list[GraphNode]:
        return self._graph_store.get_imports(repository_id, snapshot_id, file_id)

    def get_dependencies(
        self, repository_id: str, snapshot_id: str, node_id: str
    ) -> list[GraphNode]:
        return self._graph_store.get_dependencies(repository_id, snapshot_id, node_id)

    def get_neighbors(
        self, repository_id: str, snapshot_id: str, symbol_id: str, max_depth: int
    ) -> GraphNeighborhood:
        return self._graph_store.get_neighbors(repository_id, snapshot_id, symbol_id, max_depth)

    def get_retrieval_context(
        self,
        repository_id: str,
        snapshot_id: str,
        symbol_ids: list[str],
        max_neighbors_per_symbol: int,
    ) -> GraphNeighborhood:
        return self._graph_store.get_retrieval_context(
            repository_id,
            snapshot_id,
            symbol_ids,
            max_neighbors_per_symbol,
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
