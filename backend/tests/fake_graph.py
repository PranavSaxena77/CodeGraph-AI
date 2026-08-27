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
from app.modules.operations.port import OperationReporter

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
        reporter: OperationReporter | None = None,
    ) -> GraphPersistenceStatus:
        del reporter
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
                repository_id=repository.id,
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
                        repository_id=repository.id,
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
                    repository_id=repository.id,
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
                        repository_id=repository.id,
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
                        repository_id=repository.id,
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
                        repository_id=repository.id,
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

    def get_symbol(self, repository_id: str, snapshot_id: str, symbol_id: str) -> GraphNode | None:
        node = self.nodes.get((snapshot_id, symbol_id))
        if (
            node is None
            or node.repository_id != repository_id
            or node.node_type not in {"Class", "Function", "Method"}
        ):
            return None
        return deepcopy(node)

    def get_containment(
        self, repository_id: str, snapshot_id: str, node_id: str
    ) -> list[GraphNode]:
        return self._targets(repository_id, snapshot_id, node_id, {"CONTAINS", "DECLARES"})

    def get_callers(self, repository_id: str, snapshot_id: str, symbol_id: str) -> list[GraphNode]:
        source_ids = {
            relationship.source_id
            for relationship in self._snapshot_relationships(snapshot_id)
            if relationship.repository_id == repository_id
            and relationship.relationship_type == "CALLS"
            and relationship.target_id == symbol_id
        }
        return self._nodes_by_ids(repository_id, snapshot_id, source_ids)

    def get_callees(self, repository_id: str, snapshot_id: str, symbol_id: str) -> list[GraphNode]:
        return self._targets(repository_id, snapshot_id, symbol_id, {"CALLS"})

    def get_imports(self, repository_id: str, snapshot_id: str, file_id: str) -> list[GraphNode]:
        return self._targets(repository_id, snapshot_id, file_id, {"IMPORTS"})

    def get_dependencies(
        self, repository_id: str, snapshot_id: str, node_id: str
    ) -> list[GraphNode]:
        return self._targets(repository_id, snapshot_id, node_id, {"IMPORTS", "INHERITS", "CALLS"})

    def get_neighbors(
        self,
        repository_id: str,
        snapshot_id: str,
        symbol_id: str,
        max_depth: int,
    ) -> GraphNeighborhood:
        if max_depth < 1 or max_depth > 3:
            raise ValueError("max_depth must be between 1 and 3")
        relationships = [
            item
            for item in self._snapshot_relationships(snapshot_id)
            if item.repository_id == repository_id
        ]
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
            nodes=self._nodes_by_ids(repository_id, snapshot_id, visited),
            relationships=sorted(
                (deepcopy(item) for item in selected_relationships.values()),
                key=lambda item: item.id,
            ),
        )

    def get_retrieval_context(
        self,
        repository_id: str,
        snapshot_id: str,
        symbol_ids: list[str],
        max_neighbors_per_symbol: int,
    ) -> GraphNeighborhood:
        if max_neighbors_per_symbol < 1 or max_neighbors_per_symbol > 50:
            raise ValueError("max_neighbors_per_symbol must be between 1 and 50")
        selected_ids = set(symbol_ids[:50])
        selected_relationships: dict[str, GraphRelationship] = {}
        for symbol_id in symbol_ids[:50]:
            connected = [
                item
                for item in self._snapshot_relationships(snapshot_id)
                if item.repository_id == repository_id
                and item.relationship_type
                in {"CALLS", "IMPORTS", "INHERITS", "DECLARES", "CONTAINS"}
                and symbol_id in {item.source_id, item.target_id}
            ]
            for relationship in sorted(connected, key=lambda item: item.id)[
                :max_neighbors_per_symbol
            ]:
                selected_relationships[relationship.id] = relationship
                selected_ids.update({relationship.source_id, relationship.target_id})
        return GraphNeighborhood(
            nodes=self._nodes_by_ids(repository_id, snapshot_id, selected_ids),
            relationships=sorted(
                (deepcopy(item) for item in selected_relationships.values()),
                key=lambda item: item.id,
            ),
        )

    def get_preview(
        self, repository_id: str, snapshot_id: str, max_nodes: int
    ) -> GraphNeighborhood:
        if max_nodes < 1 or max_nodes > 100:
            raise ValueError("max_nodes must be between 1 and 100")
        nodes = [
            deepcopy(node)
            for node in self._snapshot_nodes(snapshot_id)
            if node.repository_id == repository_id and node.node_type != "Repository"
        ][:max_nodes]
        node_ids = {node.id for node in nodes}
        relationships = [
            deepcopy(relationship)
            for relationship in self._snapshot_relationships(snapshot_id)
            if relationship.repository_id == repository_id
            and relationship.source_id in node_ids
            and relationship.target_id in node_ids
        ]
        return GraphNeighborhood(nodes=nodes, relationships=relationships)

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
        repository_id: str,
        snapshot_id: str,
        source_id: str,
        relationship_types: set[GraphRelationshipType],
    ) -> list[GraphNode]:
        target_ids = {
            relationship.target_id
            for relationship in self._snapshot_relationships(snapshot_id)
            if relationship.repository_id == repository_id
            and relationship.source_id == source_id
            and relationship.relationship_type in relationship_types
        }
        return self._nodes_by_ids(repository_id, snapshot_id, target_ids)

    def _nodes_by_ids(
        self, repository_id: str, snapshot_id: str, node_ids: set[str]
    ) -> list[GraphNode]:
        return sorted(
            (
                deepcopy(node)
                for (scope, node_id), node in self.nodes.items()
                if scope == snapshot_id
                and node.repository_id == repository_id
                and node_id in node_ids
            ),
            key=lambda node: node.id,
        )
