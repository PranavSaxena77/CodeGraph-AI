from datetime import UTC, datetime
from pathlib import Path

from app.domain.analysis import SnapshotAnalysis
from app.domain.repositories import RepositoryMetadata, SnapshotMetadata
from app.modules.analysis.python_ast import PythonAstAnalyzer
from app.modules.graph.service import GraphPersistenceService
from tests.fake_graph import FakeGraphStore
from tests.fakes import InMemoryMetadataStore


class FakeSnapshotAnalyzer:
    def __init__(self, analysis: SnapshotAnalysis) -> None:
        self.analysis = analysis
        self.calls = 0

    def analyze_snapshot(self, repository_id: str, snapshot_id: str) -> SnapshotAnalysis:
        self.calls += 1
        assert repository_id == "repository-1"
        assert snapshot_id == self.analysis.snapshot_id
        return self.analysis


def build_analysis(tmp_path: Path, snapshot_id: str = "snapshot-1") -> SnapshotAnalysis:
    sources = {
        "app.py": """import utils

class Base:
    pass

class Service(Base):
    def run(self):
        helper()
        self.cleanup()
        utils.utility()
        missing()

    def cleanup(self):
        pass

def helper():
    return 1
""",
        "utils.py": """def utility():
    return 2
""",
    }
    files: list[Path] = []
    for file_path, source in sources.items():
        relative_path = Path(file_path)
        (tmp_path / relative_path).write_text(source, encoding="utf-8")
        files.append(relative_path)
    return PythonAstAnalyzer().analyze(snapshot_id, tmp_path, files)


def build_graph_service(
    tmp_path: Path,
) -> tuple[GraphPersistenceService, FakeGraphStore, FakeSnapshotAnalyzer]:
    metadata = InMemoryMetadataStore()
    metadata.save_repository(
        RepositoryMetadata(
            id="repository-1",
            owner="example",
            name="project",
            github_url="https://github.com/example/project",
            default_branch="main",
            created_at=datetime.now(UTC),
        )
    )
    metadata.save_snapshot(
        SnapshotMetadata(
            id="snapshot-1",
            repository_id="repository-1",
            commit_sha="a" * 40,
            ref="main",
            status="ready",
            discovered_file_count=2,
            created_at=datetime.now(UTC),
        )
    )
    analyzer = FakeSnapshotAnalyzer(build_analysis(tmp_path))
    graph = FakeGraphStore()
    return (
        GraphPersistenceService(metadata, analyzer, graph),
        graph,
        analyzer,
    )


def test_graph_persistence_schema_and_idempotency(tmp_path: Path) -> None:
    service, graph, analyzer = build_graph_service(tmp_path)

    first = service.analyze_and_persist("repository-1", "snapshot-1")
    second = service.analyze_and_persist("repository-1", "snapshot-1")

    assert first.idempotent is False
    assert second.idempotent is True
    assert first.node_count == second.node_count == 10
    assert first.relationship_count == second.relationship_count == 13
    assert graph.persist_count == 1
    assert analyzer.calls == 1

    node_types = {node.node_type for node in graph._snapshot_nodes("snapshot-1")}
    relationship_types = {
        relationship.relationship_type
        for relationship in graph._snapshot_relationships("snapshot-1")
    }
    assert node_types == {"Repository", "Snapshot", "File", "Class", "Function", "Method"}
    assert relationship_types == {
        "HAS_SNAPSHOT",
        "CONTAINS",
        "DECLARES",
        "IMPORTS",
        "INHERITS",
        "CALLS",
    }


def test_graph_excludes_unresolved_reference_edges(tmp_path: Path) -> None:
    service, graph, analyzer = build_graph_service(tmp_path)
    service.analyze_and_persist("repository-1", "snapshot-1")

    unresolved_call_ids = {
        call.id for call in analyzer.analysis.calls if call.resolution == "unresolved"
    }
    persisted_relationship_ids = {
        relationship.id for relationship in graph._snapshot_relationships("snapshot-1")
    }

    assert unresolved_call_ids
    assert unresolved_call_ids.isdisjoint(persisted_relationship_ids)


def test_graph_query_operations_are_snapshot_scoped(tmp_path: Path) -> None:
    service, graph, analyzer = build_graph_service(tmp_path)
    service.analyze_and_persist("repository-1", "snapshot-1")
    symbols = {
        symbol.qualified_name: symbol
        for symbol in analyzer.analysis.symbols
        if symbol.symbol_type != "file"
    }
    files = {
        symbol.file_path: symbol
        for symbol in analyzer.analysis.symbols
        if symbol.symbol_type == "file"
    }
    run = symbols["app.Service.run"]
    cleanup = symbols["app.Service.cleanup"]
    helper = symbols["app.helper"]
    service_class = symbols["app.Service"]
    base = symbols["app.Base"]

    assert service.get_symbol("repository-1", "snapshot-1", run.id) is not None
    assert service.get_symbol("repository-1", "different-snapshot", run.id) is None
    assert {
        node.id for node in service.get_containment("repository-1", "snapshot-1", service_class.id)
    } == {
        run.id,
        cleanup.id,
    }
    assert [node.id for node in service.get_callers("repository-1", "snapshot-1", helper.id)] == [
        run.id
    ]
    assert {node.id for node in service.get_callees("repository-1", "snapshot-1", run.id)} == {
        helper.id,
        cleanup.id,
    }
    assert [
        node.id for node in service.get_imports("repository-1", "snapshot-1", files["app.py"].id)
    ] == [files["utils.py"].id]
    assert [
        node.id for node in service.get_dependencies("repository-1", "snapshot-1", service_class.id)
    ] == [base.id]

    neighborhood = service.get_neighbors("repository-1", "snapshot-1", run.id, 1)
    assert run.id in {node.id for node in neighborhood.nodes}
    assert helper.id in {node.id for node in neighborhood.nodes}
    assert all(
        relationship.snapshot_id == "snapshot-1" for relationship in neighborhood.relationships
    )
