from datetime import UTC, datetime
from pathlib import Path

from app.domain.repositories import RepositoryMetadata, SnapshotMetadata
from app.modules.analysis.chunking import SemanticChunker
from app.modules.analysis.python_ast import PythonAstAnalyzer
from app.modules.embeddings.fake import DeterministicEmbeddingProvider


def _metadata() -> tuple[RepositoryMetadata, SnapshotMetadata]:
    repository = RepositoryMetadata(
        id="repository-1",
        owner="example",
        name="project",
        github_url="https://github.com/example/project",
        default_branch="main",
        created_at=datetime.now(UTC),
    )
    snapshot = SnapshotMetadata(
        id="snapshot-1",
        repository_id=repository.id,
        commit_sha="a" * 40,
        ref="main",
        status="ready",
        discovered_file_count=1,
        created_at=datetime.now(UTC),
    )
    return repository, snapshot


def _chunks(tmp_path: Path, source: str, max_chunk_chars: int = 8_000):
    path = tmp_path / "app.py"
    path.write_text(source, encoding="utf-8")
    analysis = PythonAstAnalyzer().analyze("snapshot-1", tmp_path, [Path("app.py")])
    repository, snapshot = _metadata()
    return SemanticChunker(max_chunk_chars).build_chunks(
        repository,
        snapshot,
        analysis,
        {"app.py": source},
    )


def test_symbol_chunks_are_deterministic_and_preserve_source_lines(tmp_path: Path) -> None:
    source = """\"\"\"Module documentation.\"\"\"

class Greeter:
    def greet(self, name: str):
        return f\"Hello {name}\"

def run():
    return Greeter().greet(\"world\")
"""

    first = _chunks(tmp_path, source)
    second = _chunks(tmp_path, source)

    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]
    assert {chunk.symbol_type for chunk in first} == {"file", "class", "method", "function"}
    greet = next(chunk for chunk in first if chunk.qualified_name == "app.Greeter.greet")
    assert greet.symbol_id is not None
    assert (greet.start_line, greet.end_line) == (4, 5)
    assert greet.content == '    def greet(self, name: str):\n        return f"Hello {name}"'
    assert all(chunk.repository_id == "repository-1" for chunk in first)
    assert all(chunk.snapshot_id == "snapshot-1" for chunk in first)


def test_oversized_symbol_split_is_deterministic_and_keeps_parent_identity(
    tmp_path: Path,
) -> None:
    source = """def calculate():
    first_value = 1111111111
    second_value = 2222222222
    third_value = 3333333333
    return first_value + second_value + third_value
"""

    chunks = _chunks(tmp_path, source, max_chunk_chars=45)

    assert len(chunks) > 1
    assert len({chunk.symbol_id for chunk in chunks}) == 1
    assert [chunk.part_index for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].start_line == 1
    assert chunks[-1].end_line == 5
    assert all(len(chunk.content) <= 45 for chunk in chunks)


def test_fake_embeddings_are_deterministic_and_have_configured_dimension() -> None:
    provider = DeterministicEmbeddingProvider(dimension=32)

    first = provider.embed_query("repository symbol lookup")
    second = provider.embed_query("repository symbol lookup")
    different = provider.embed_query("database transaction")

    assert first == second
    assert first != different
    assert len(first) == 32
    assert provider.embed_documents(["alpha", "beta"])[0] == provider.embed_query("alpha")
