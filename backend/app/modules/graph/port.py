from typing import Protocol

from app.domain.analysis import SnapshotAnalysis
from app.domain.graph import (
    GraphNeighborhood,
    GraphNode,
    GraphPersistenceStatus,
)
from app.domain.repositories import RepositoryMetadata, SnapshotMetadata


class GraphStore(Protocol):
    def persist_snapshot(
        self,
        repository: RepositoryMetadata,
        snapshot: SnapshotMetadata,
        analysis: SnapshotAnalysis,
    ) -> GraphPersistenceStatus: ...

    def get_persistence_status(
        self, repository_id: str, snapshot_id: str
    ) -> GraphPersistenceStatus | None: ...

    def get_symbol(self, snapshot_id: str, symbol_id: str) -> GraphNode | None: ...

    def get_containment(self, snapshot_id: str, node_id: str) -> list[GraphNode]: ...

    def get_callers(self, snapshot_id: str, symbol_id: str) -> list[GraphNode]: ...

    def get_callees(self, snapshot_id: str, symbol_id: str) -> list[GraphNode]: ...

    def get_imports(self, snapshot_id: str, file_id: str) -> list[GraphNode]: ...

    def get_dependencies(self, snapshot_id: str, node_id: str) -> list[GraphNode]: ...

    def get_neighbors(
        self, snapshot_id: str, symbol_id: str, max_depth: int
    ) -> GraphNeighborhood: ...
