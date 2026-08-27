from typing import Protocol

from app.domain.analysis import SnapshotAnalysis
from app.domain.graph import (
    GraphNeighborhood,
    GraphNode,
    GraphPersistenceStatus,
)
from app.domain.repositories import RepositoryMetadata, SnapshotMetadata
from app.modules.operations.port import OperationReporter


class GraphStore(Protocol):
    def persist_snapshot(
        self,
        repository: RepositoryMetadata,
        snapshot: SnapshotMetadata,
        analysis: SnapshotAnalysis,
        reporter: OperationReporter | None = None,
    ) -> GraphPersistenceStatus: ...

    def get_persistence_status(
        self, repository_id: str, snapshot_id: str
    ) -> GraphPersistenceStatus | None: ...

    def get_symbol(
        self, repository_id: str, snapshot_id: str, symbol_id: str
    ) -> GraphNode | None: ...

    def get_containment(
        self, repository_id: str, snapshot_id: str, node_id: str
    ) -> list[GraphNode]: ...

    def get_callers(
        self, repository_id: str, snapshot_id: str, symbol_id: str
    ) -> list[GraphNode]: ...

    def get_callees(
        self, repository_id: str, snapshot_id: str, symbol_id: str
    ) -> list[GraphNode]: ...

    def get_imports(
        self, repository_id: str, snapshot_id: str, file_id: str
    ) -> list[GraphNode]: ...

    def get_dependencies(
        self, repository_id: str, snapshot_id: str, node_id: str
    ) -> list[GraphNode]: ...

    def get_neighbors(
        self, repository_id: str, snapshot_id: str, symbol_id: str, max_depth: int
    ) -> GraphNeighborhood: ...

    def get_retrieval_context(
        self,
        repository_id: str,
        snapshot_id: str,
        symbol_ids: list[str],
        max_neighbors_per_symbol: int,
    ) -> GraphNeighborhood: ...

    def get_preview(
        self, repository_id: str, snapshot_id: str, max_nodes: int
    ) -> GraphNeighborhood: ...
