from copy import deepcopy

from app.domain.analysis import SnapshotAnalysis, StructuralSymbol
from app.domain.graph import (
    GraphNeighborhood,
    GraphNode,
    GraphPersistenceStatus,
    GraphRelationship,
    GraphRelationshipType,
)
from app.domain.repositories import RepositoryMetadata, SnapshotMetadata

_NODE_TYPES = {
    "file": "File",
    "class": "Class",
    "function": "Function",
    "method": "Method",
}


class FakeGraphStore:
    """In-memory GraphStore implementation for unit and API tests."""

    def __init__(self) -> None:
        self.nodes: dict[tuple[str, str], GraphNode] = {}
        self.relationships: dict[tuple[str, str], GraphRelationship] = {}
        self.statuses: dict[tuple[str, str], GraphPersistenceStatus] = {}
        self.persist_count = 0

    def persist_snapshot(
        self,
        repository: RepositoryMetadata,
        snapshot: SnapshotMetadata,
        analysis: SnapshotAnalysis,
    ) -> GraphPersistenceStatus:
        key = (repository.id, snapshot.id)
        existing = self.statuses.get(key)
        if existing is not None:
            return existing.model_copy(update={"idempotent": True})
        if analysis.snapshot_id != snapshot.id:
            raise ValueError("Analysis and snapshot identities do not match")

        self.persist_count += 1
        self._add_node(
            snapshot.id,
            GraphNode(
                id=repository.id,
                node_type="Repository",
                repository_id=repository.id,
            ),
        )
        self._add_node(
            snapshot.id,
            GraphNode(
                id=snapshot.id,
                node_type="Snapshot",
                repository_id=repository.id,
                snapshot_id=snapshot.id,
                commit_sha=snapshot.commit_sha,
            ),
        )
        self._add_relationship(
            GraphRelationship(
                id=f"{repository.id}:has_snapshot:{snapshot.id}",
                relationship_type="HAS_SNAPSHOT",
                source_id=repository.id,
                target_id=snapshot.id,
                snapshot_id=snapshot.id,
            )
        )

        file_ids: dict[str, str] = {}
        for symbol in analysis.symbols:
            self._add_symbol(repository.id, snapshot, symbol)
            if symbol.symbol_type == "file":
                file_ids[symbol.file_path] = symbol.id
                self._add_relationship(
                    GraphRelationship(
                        id=f"{snapshot.id}:contains:{symbol.id}",
                        relationship_type="CONTAINS",
                        source_id=snapshot.id,
                        target_id=symbol.id,
                        snapshot_id=snapshot.id,
                    )
                )

        for symbol in analysis.symbols:
            if symbol.symbol_type == "file":
                continue
            source_id = symbol.parent_symbol_id or file_ids[symbol.file_path]
            self._add_relationship(
                GraphRelationship(
                    id=f"{source_id}:declares:{symbol.id}",
                    relationship_type="DECLARES",
                    source_id=source_id,
                    target_id=symbol.id,
                    snapshot_id=snapshot.id,
                )
            )

        for record in analysis.imports:
            if record.resolution == "resolved" and record.resolved_file_id is not None:
                self._add_relationship(
                    GraphRelationship(
                        id=record.id,
                        relationship_type="IMPORTS",
                        source_id=file_ids[record.file_path],
                        target_id=record.resolved_file_id,
                        snapshot_id=snapshot.id,
                        start_line=record.start_line,
                        end_line=record.end_line,
                    )
                )
        for record in analysis.inheritances:
            if record.resolution == "resolved" and record.resolved_symbol_id is not None:
                self._add_relationship(
                    GraphRelationship(
                        id=record.id,
                        relationship_type="INHERITS",
                        source_id=record.class_symbol_id,
                        target_id=record.resolved_symbol_id,
                        snapshot_id=snapshot.id,
                        start_line=record.start_line,
                        end_line=record.end_line,
                    )
                )
        for record in analysis.calls:
            if (
                record.resolution == "resolved"
                and record.caller_symbol_id is not None
                and record.resolved_symbol_id is not None
            ):
                self._add_relationship(
                    GraphRelationship(
                        id=record.id,
                        relationship_type="CALLS",
                        source_id=record.caller_symbol_id,
                        target_id=record.resolved_symbol_id,
                        snapshot_id=snapshot.id,
                        start_line=record.start_line,
                        end_line=record.end_line,
                    )
                )

        status = GraphPersistenceStatus(
            repository_id=repository.id,
            snapshot_id=snapshot.id,
            node_count=len(self._snapshot_nodes(snapshot.id)),
            relationship_count=len(self._snapshot_relationships(snapshot.id)),
            diagnostic_count=len(analysis.diagnostics),
        )
        self.statuses[key] = status
        return deepcopy(status)

    def get_persistence_status(
        self, repository_id: str, snapshot_id: str
    ) -> GraphPersistenceStatus | None:
        status = self.statuses.get((repository_id, snapshot_id))
        return status.model_copy(update={"idempotent": True}) if status else None

    def get_symbol(self, snapshot_id: str, symbol_id: str) -> GraphNode | None:
        node = self.nodes.get((snapshot_id, symbol_id))
        if node is None or node.node_type not in {"Class", "Function", "Method"}:
            return None
        return deepcopy(node)

    def get_containment(self, snapshot_id: str, node_id: str) -> list[GraphNode]:
        return self._targets(snapshot_id, node_id, {"CONTAINS", "DECLARES"})

    def get_callers(self, snapshot_id: str, symbol_id: str) -> list[GraphNode]:
        source_ids = {
            relationship.source_id
            for relationship in self._snapshot_relationships(snapshot_id)
            if relationship.relationship_type == "CALLS" and relationship.target_id == symbol_id
        }
        return self._nodes_by_ids(snapshot_id, source_ids)

    def get_callees(self, snapshot_id: str, symbol_id: str) -> list[GraphNode]:
        return self._targets(snapshot_id, symbol_id, {"CALLS"})

    def get_imports(self, snapshot_id: str, file_id: str) -> list[GraphNode]:
        return self._targets(snapshot_id, file_id, {"IMPORTS"})

    def get_dependencies(self, snapshot_id: str, node_id: str) -> list[GraphNode]:
        return self._targets(snapshot_id, node_id, {"IMPORTS", "INHERITS", "CALLS"})

    def get_neighbors(self, snapshot_id: str, symbol_id: str, max_depth: int) -> GraphNeighborhood:
        if max_depth < 1 or max_depth > 3:
            raise ValueError("max_depth must be between 1 and 3")
        relationships = self._snapshot_relationships(snapshot_id)
        visited = {symbol_id}
        frontier = {symbol_id}
        selected_relationships: dict[str, GraphRelationship] = {}
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for relationship in relationships:
                if relationship.source_id in frontier or relationship.target_id in frontier:
                    selected_relationships[relationship.id] = relationship
                    next_frontier.update({relationship.source_id, relationship.target_id} - visited)
            visited.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        return GraphNeighborhood(
            nodes=self._nodes_by_ids(snapshot_id, visited),
            relationships=sorted(
                (deepcopy(item) for item in selected_relationships.values()),
                key=lambda item: item.id,
            ),
        )

    def _add_symbol(
        self,
        repository_id: str,
        snapshot: SnapshotMetadata,
        symbol: StructuralSymbol,
    ) -> None:
        self._add_node(
            snapshot.id,
            GraphNode(
                id=symbol.id,
                node_type=_NODE_TYPES[symbol.symbol_type],
                repository_id=repository_id,
                snapshot_id=snapshot.id,
                commit_sha=snapshot.commit_sha,
                file_path=symbol.file_path,
                symbol_name=symbol.symbol_name,
                qualified_name=symbol.qualified_name,
                symbol_type=symbol.symbol_type,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
            ),
        )

    def _add_node(self, snapshot_id: str, node: GraphNode) -> None:
        self.nodes.setdefault((snapshot_id, node.id), deepcopy(node))

    def _add_relationship(self, relationship: GraphRelationship) -> None:
        self.relationships.setdefault(
            (relationship.snapshot_id, relationship.id), deepcopy(relationship)
        )

    def _snapshot_nodes(self, snapshot_id: str) -> list[GraphNode]:
        return [node for (scope, _), node in self.nodes.items() if scope == snapshot_id]

    def _snapshot_relationships(self, snapshot_id: str) -> list[GraphRelationship]:
        return [
            relationship
            for (scope, _), relationship in self.relationships.items()
            if scope == snapshot_id
        ]

    def _targets(
        self,
        snapshot_id: str,
        source_id: str,
        relationship_types: set[GraphRelationshipType],
    ) -> list[GraphNode]:
        target_ids = {
            relationship.target_id
            for relationship in self._snapshot_relationships(snapshot_id)
            if relationship.source_id == source_id
            and relationship.relationship_type in relationship_types
        }
        return self._nodes_by_ids(snapshot_id, target_ids)

    def _nodes_by_ids(self, snapshot_id: str, node_ids: set[str]) -> list[GraphNode]:
        return sorted(
            (
                deepcopy(node)
                for (scope, node_id), node in self.nodes.items()
                if scope == snapshot_id and node_id in node_ids
            ),
            key=lambda node: node.id,
        )
