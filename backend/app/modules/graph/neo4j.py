from typing import Any

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import Neo4jError

from app.core.config import Settings
from app.core.errors import GraphStoreError
from app.domain.analysis import SnapshotAnalysis, StructuralSymbol
from app.domain.graph import (
    GraphNeighborhood,
    GraphNode,
    GraphPersistenceStatus,
    GraphRelationship,
)
from app.domain.repositories import RepositoryMetadata, SnapshotMetadata

_SYMBOL_LABELS = {
    "class": "Class",
    "function": "Function",
    "method": "Method",
}


class Neo4jGraphStore:
    """Neo4j adapter for idempotent snapshot graphs and snapshot-scoped queries."""

    def __init__(self, settings: Settings) -> None:
        if settings.neo4j_password is None:
            raise GraphStoreError("Neo4j password is not configured")
        self._driver: Driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password.get_secret_value()),
            connection_timeout=settings.dependency_timeout_seconds,
        )
        self._database = settings.neo4j_database
        self._schema_ready = False

    def persist_snapshot(
        self,
        repository: RepositoryMetadata,
        snapshot: SnapshotMetadata,
        analysis: SnapshotAnalysis,
    ) -> GraphPersistenceStatus:
        if analysis.snapshot_id != snapshot.id:
            raise GraphStoreError("Analysis and snapshot identities do not match")
        existing = self.get_persistence_status(repository.id, snapshot.id)
        if existing is not None:
            return existing.model_copy(update={"idempotent": True})

        self._ensure_schema()
        files = [symbol for symbol in analysis.symbols if symbol.symbol_type == "file"]
        symbols = [symbol for symbol in analysis.symbols if symbol.symbol_type != "file"]
        file_ids = {record.file_path: record.id for record in files}

        self._write_repository_snapshot(repository, snapshot, len(analysis.diagnostics))
        self._write_files(repository.id, snapshot, files)
        for symbol_type, label in _SYMBOL_LABELS.items():
            self._write_symbols(
                repository.id,
                snapshot,
                label,
                [record for record in symbols if record.symbol_type == symbol_type],
            )
        self._write_declarations(repository.id, snapshot.id, symbols, file_ids)
        self._write_imports(repository.id, snapshot.id, analysis)
        self._write_inheritances(repository.id, snapshot.id, analysis)
        self._write_calls(repository.id, snapshot.id, analysis)
        self._execute(
            """
            MATCH (snapshot:Snapshot {id: $snapshot_id, repository_id: $repository_id})
            SET snapshot.graph_status = 'persisted'
            """,
            {"repository_id": repository.id, "snapshot_id": snapshot.id},
        )

        status = self.get_persistence_status(repository.id, snapshot.id)
        if status is None:
            raise GraphStoreError("Neo4j graph persistence could not be verified")
        return status.model_copy(update={"idempotent": False})

    def get_persistence_status(
        self, repository_id: str, snapshot_id: str
    ) -> GraphPersistenceStatus | None:
        snapshot_rows = self._execute(
            """
            MATCH (snapshot)
            WHERE 'Snapshot' IN labels(snapshot)
              AND snapshot[$id_property] = $snapshot_id
              AND snapshot[$repository_property] = $repository_id
              AND snapshot[$status_property] = 'persisted'
            RETURN snapshot[$diagnostic_property] AS diagnostic_count
            """,
            {
                "repository_id": repository_id,
                "snapshot_id": snapshot_id,
                "id_property": "id",
                "repository_property": "repository_id",
                "status_property": "graph_status",
                "diagnostic_property": "diagnostic_count",
            },
        )
        if not snapshot_rows:
            return None

        node_rows = self._execute(
            """
            MATCH (node)
            WHERE node.snapshot_id = $snapshot_id AND node.repository_id = $repository_id
            RETURN count(node) AS count
            """,
            {"repository_id": repository_id, "snapshot_id": snapshot_id},
        )
        relationship_rows = self._execute(
            """
            MATCH ()-[relationship]->()
            WHERE relationship.snapshot_id = $snapshot_id
              AND relationship.repository_id = $repository_id
            RETURN count(relationship) AS count
            """,
            {"repository_id": repository_id, "snapshot_id": snapshot_id},
        )
        return GraphPersistenceStatus(
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            node_count=int(node_rows[0]["count"]) + 1,
            relationship_count=int(relationship_rows[0]["count"]),
            idempotent=True,
            diagnostic_count=int(snapshot_rows[0]["diagnostic_count"] or 0),
        )

    def get_symbol(self, snapshot_id: str, symbol_id: str) -> GraphNode | None:
        rows = self._execute(
            """
            MATCH (node:Symbol {id: $symbol_id, snapshot_id: $snapshot_id})
            RETURN node
            """,
            {"snapshot_id": snapshot_id, "symbol_id": symbol_id},
        )
        return self._node_from_value(rows[0]["node"]) if rows else None

    def get_containment(self, snapshot_id: str, node_id: str) -> list[GraphNode]:
        return self._query_nodes(
            """
            MATCH (source {id: $node_id})
                  -[relationship:CONTAINS|DECLARES]->(node)
            WHERE relationship.snapshot_id = $snapshot_id
              AND node.snapshot_id = $snapshot_id
            RETURN DISTINCT node
            ORDER BY node.file_path, node.start_line, node.id
            """,
            {"snapshot_id": snapshot_id, "node_id": node_id},
        )

    def get_callers(self, snapshot_id: str, symbol_id: str) -> list[GraphNode]:
        return self._query_nodes(
            """
            MATCH (node:Symbol)-[relationship:CALLS]->
                  (:Symbol {id: $symbol_id, snapshot_id: $snapshot_id})
            WHERE relationship.snapshot_id = $snapshot_id
              AND node.snapshot_id = $snapshot_id
            RETURN DISTINCT node
            ORDER BY node.file_path, node.start_line, node.id
            """,
            {"snapshot_id": snapshot_id, "symbol_id": symbol_id},
        )

    def get_callees(self, snapshot_id: str, symbol_id: str) -> list[GraphNode]:
        return self._query_nodes(
            """
            MATCH (:Symbol {id: $symbol_id, snapshot_id: $snapshot_id})
                  -[relationship:CALLS]->(node:Symbol)
            WHERE relationship.snapshot_id = $snapshot_id
              AND node.snapshot_id = $snapshot_id
            RETURN DISTINCT node
            ORDER BY node.file_path, node.start_line, node.id
            """,
            {"snapshot_id": snapshot_id, "symbol_id": symbol_id},
        )

    def get_imports(self, snapshot_id: str, file_id: str) -> list[GraphNode]:
        return self._query_nodes(
            """
            MATCH (:File {id: $file_id, snapshot_id: $snapshot_id})
                  -[relationship:IMPORTS]->(node:File)
            WHERE relationship.snapshot_id = $snapshot_id
              AND node.snapshot_id = $snapshot_id
            RETURN DISTINCT node
            ORDER BY node.file_path, node.id
            """,
            {"snapshot_id": snapshot_id, "file_id": file_id},
        )

    def get_dependencies(self, snapshot_id: str, node_id: str) -> list[GraphNode]:
        return self._query_nodes(
            """
            MATCH (source {id: $node_id})
                  -[relationship:IMPORTS|INHERITS|CALLS]->(node)
            WHERE relationship.snapshot_id = $snapshot_id
              AND node.snapshot_id = $snapshot_id
            RETURN DISTINCT node
            ORDER BY node.file_path, node.start_line, node.id
            """,
            {"snapshot_id": snapshot_id, "node_id": node_id},
        )

    def get_neighbors(self, snapshot_id: str, symbol_id: str, max_depth: int) -> GraphNeighborhood:
        if max_depth < 1 or max_depth > 3:
            raise ValueError("max_depth must be between 1 and 3")
        rows = self._execute(
            f"""
            MATCH path=(source:Symbol {{id: $symbol_id, snapshot_id: $snapshot_id}})
                  -[*1..{max_depth}]-(neighbor)
            WHERE neighbor.snapshot_id = $snapshot_id
              AND all(
                  relationship IN relationships(path)
                  WHERE relationship.snapshot_id = $snapshot_id
              )
            RETURN nodes(path) AS nodes, relationships(path) AS relationships
            ORDER BY length(path)
            """,
            {"snapshot_id": snapshot_id, "symbol_id": symbol_id},
        )
        nodes: dict[str, GraphNode] = {}
        relationships: dict[str, GraphRelationship] = {}
        for row in rows:
            for value in row["nodes"]:
                node = self._node_from_value(value)
                nodes[node.id] = node
            for value in row["relationships"]:
                relationship = self._relationship_from_value(value)
                relationships[relationship.id] = relationship
        return GraphNeighborhood(
            nodes=sorted(nodes.values(), key=lambda node: node.id),
            relationships=sorted(relationships.values(), key=lambda relationship: relationship.id),
        )

    def close(self) -> None:
        self._driver.close()

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        constraints = (
            "CREATE CONSTRAINT repository_id_unique IF NOT EXISTS "
            "FOR (node:Repository) REQUIRE node.id IS UNIQUE",
            "CREATE CONSTRAINT snapshot_id_unique IF NOT EXISTS "
            "FOR (node:Snapshot) REQUIRE node.id IS UNIQUE",
            "CREATE CONSTRAINT file_id_unique IF NOT EXISTS "
            "FOR (node:File) REQUIRE node.id IS UNIQUE",
            "CREATE CONSTRAINT symbol_id_unique IF NOT EXISTS "
            "FOR (node:Symbol) REQUIRE node.id IS UNIQUE",
        )
        for query in constraints:
            self._execute(query, {})
        self._schema_ready = True

    def _write_repository_snapshot(
        self,
        repository: RepositoryMetadata,
        snapshot: SnapshotMetadata,
        diagnostic_count: int,
    ) -> None:
        self._execute(
            """
            MERGE (repository:Repository {id: $repository_id})
            SET repository.repository_id = $repository_id,
                repository.owner = $owner,
                repository.name = $name,
                repository.github_url = $github_url,
                repository.node_type = 'Repository'
            MERGE (snapshot:Snapshot {id: $snapshot_id})
            SET snapshot.snapshot_id = $snapshot_id,
                snapshot.repository_id = $repository_id,
                snapshot.commit_sha = $commit_sha,
                snapshot.ref = $ref,
                snapshot.node_type = 'Snapshot',
                snapshot.graph_status = 'persisting',
                snapshot.diagnostic_count = $diagnostic_count
            MERGE (repository)-[relationship:HAS_SNAPSHOT {
                id: $relationship_id
            }]->(snapshot)
            SET relationship.snapshot_id = $snapshot_id,
                relationship.repository_id = $repository_id,
                relationship.source_id = $repository_id,
                relationship.target_id = $snapshot_id
            """,
            {
                "repository_id": repository.id,
                "owner": repository.owner,
                "name": repository.name,
                "github_url": repository.github_url,
                "snapshot_id": snapshot.id,
                "commit_sha": snapshot.commit_sha,
                "ref": snapshot.ref,
                "diagnostic_count": diagnostic_count,
                "relationship_id": f"{repository.id}:has_snapshot:{snapshot.id}",
            },
        )

    def _write_files(
        self,
        repository_id: str,
        snapshot: SnapshotMetadata,
        files: list[StructuralSymbol],
    ) -> None:
        rows = [self._symbol_row(repository_id, snapshot.commit_sha, record) for record in files]
        self._execute(
            """
            UNWIND $rows AS row
            MATCH (snapshot:Snapshot {id: $snapshot_id, repository_id: $repository_id})
            MERGE (node:File {id: row.id})
            SET node += row.properties
            MERGE (snapshot)-[relationship:CONTAINS {id: row.relationship_id}]->(node)
            SET relationship.snapshot_id = $snapshot_id,
                relationship.repository_id = $repository_id,
                relationship.source_id = $snapshot_id,
                relationship.target_id = row.id
            """,
            {
                "rows": rows,
                "repository_id": repository_id,
                "snapshot_id": snapshot.id,
            },
        )

    def _write_symbols(
        self,
        repository_id: str,
        snapshot: SnapshotMetadata,
        label: str,
        symbols: list[StructuralSymbol],
    ) -> None:
        rows = [self._symbol_row(repository_id, snapshot.commit_sha, record) for record in symbols]
        self._execute(
            f"""
            UNWIND $rows AS row
            MERGE (node:Symbol:{label} {{id: row.id}})
            SET node += row.properties
            """,
            {"rows": rows},
        )

    def _write_declarations(
        self,
        repository_id: str,
        snapshot_id: str,
        symbols: list[StructuralSymbol],
        file_ids: dict[str, str],
    ) -> None:
        rows: list[dict[str, object]] = [
            {
                "id": (
                    f"{record.parent_symbol_id or file_ids[record.file_path]}:declares:{record.id}"
                ),
                "source_id": record.parent_symbol_id or file_ids[record.file_path],
                "target_id": record.id,
            }
            for record in symbols
        ]
        self._execute(
            """
            UNWIND $rows AS row
            MATCH (source {id: row.source_id, snapshot_id: $snapshot_id})
            WHERE source:File OR source:Symbol
            MATCH (target:Symbol {id: row.target_id, snapshot_id: $snapshot_id})
            MERGE (source)-[relationship:DECLARES {id: row.id}]->(target)
            SET relationship.snapshot_id = $snapshot_id,
                relationship.repository_id = $repository_id,
                relationship.source_id = row.source_id,
                relationship.target_id = row.target_id
            """,
            {
                "rows": rows,
                "repository_id": repository_id,
                "snapshot_id": snapshot_id,
            },
        )

    def _write_imports(
        self, repository_id: str, snapshot_id: str, analysis: SnapshotAnalysis
    ) -> None:
        file_ids = {
            record.file_path: record.id
            for record in analysis.symbols
            if record.symbol_type == "file"
        }
        rows: list[dict[str, object]] = [
            {
                "id": record.id,
                "source_id": file_ids[record.file_path],
                "target_id": record.resolved_file_id,
                "module": record.module,
                "imported_name": record.imported_name,
                "alias": record.alias,
                "start_line": record.start_line,
                "end_line": record.end_line,
            }
            for record in analysis.imports
            if record.resolution == "resolved" and record.resolved_file_id is not None
        ]
        self._write_reference_relationships(
            "IMPORTS", repository_id, snapshot_id, rows, "File", "File"
        )

    def _write_inheritances(
        self, repository_id: str, snapshot_id: str, analysis: SnapshotAnalysis
    ) -> None:
        rows: list[dict[str, object]] = [
            {
                "id": record.id,
                "source_id": record.class_symbol_id,
                "target_id": record.resolved_symbol_id,
                "base_text": record.base_text,
                "start_line": record.start_line,
                "end_line": record.end_line,
            }
            for record in analysis.inheritances
            if record.resolution == "resolved" and record.resolved_symbol_id is not None
        ]
        self._write_reference_relationships(
            "INHERITS", repository_id, snapshot_id, rows, "Class", "Class"
        )

    def _write_calls(
        self, repository_id: str, snapshot_id: str, analysis: SnapshotAnalysis
    ) -> None:
        rows: list[dict[str, object]] = [
            {
                "id": record.id,
                "source_id": record.caller_symbol_id,
                "target_id": record.resolved_symbol_id,
                "callee_text": record.callee_text,
                "start_line": record.start_line,
                "end_line": record.end_line,
            }
            for record in analysis.calls
            if record.resolution == "resolved"
            and record.caller_symbol_id is not None
            and record.resolved_symbol_id is not None
        ]
        self._write_reference_relationships(
            "CALLS", repository_id, snapshot_id, rows, "Symbol", "Symbol"
        )

    def _write_reference_relationships(
        self,
        relationship_type: str,
        repository_id: str,
        snapshot_id: str,
        rows: list[dict[str, object]],
        source_label: str,
        target_label: str,
    ) -> None:
        self._execute(
            f"""
            UNWIND $rows AS row
            MATCH (source:{source_label} {{id: row.source_id, snapshot_id: $snapshot_id}})
            MATCH (target:{target_label} {{id: row.target_id, snapshot_id: $snapshot_id}})
            MERGE (source)-[relationship:{relationship_type} {{id: row.id}}]->(target)
            SET relationship += row,
                relationship.snapshot_id = $snapshot_id,
                relationship.repository_id = $repository_id
            """,
            {
                "rows": rows,
                "repository_id": repository_id,
                "snapshot_id": snapshot_id,
            },
        )

    @staticmethod
    def _symbol_row(
        repository_id: str, commit_sha: str, record: StructuralSymbol
    ) -> dict[str, object]:
        node_type = "File" if record.symbol_type == "file" else _SYMBOL_LABELS[record.symbol_type]
        return {
            "id": record.id,
            "relationship_id": f"{record.snapshot_id}:contains:{record.id}",
            "properties": {
                "id": record.id,
                "node_type": node_type,
                "snapshot_id": record.snapshot_id,
                "repository_id": repository_id,
                "commit_sha": commit_sha,
                "file_path": record.file_path,
                "symbol_name": record.symbol_name,
                "qualified_name": record.qualified_name,
                "symbol_type": record.symbol_type,
                "start_line": record.start_line,
                "end_line": record.end_line,
                "parent_symbol_id": record.parent_symbol_id,
                "is_async": record.is_async,
                "content_hash": record.content_hash,
                "line_count": record.line_count,
            },
        }

    def _query_nodes(self, query: str, parameters: dict[str, object]) -> list[GraphNode]:
        rows = self._execute(query, parameters)
        return [self._node_from_value(row["node"]) for row in rows]

    @staticmethod
    def _node_from_value(value: Any) -> GraphNode:
        properties = dict(value.items())
        return GraphNode.model_validate(properties)

    @staticmethod
    def _relationship_from_value(value: Any) -> GraphRelationship:
        properties = dict(value.items())
        properties["relationship_type"] = value.type
        return GraphRelationship.model_validate(properties)

    def _execute(self, query: str, parameters: dict[str, object]) -> list[dict[str, Any]]:
        try:
            records, _, _ = self._driver.execute_query(
                query,
                parameters_=parameters,
                database_=self._database,
            )
            return [dict(zip(record.keys(), record.values(), strict=True)) for record in records]
        except Neo4jError as error:
            raise GraphStoreError("Neo4j graph operation failed") from error
