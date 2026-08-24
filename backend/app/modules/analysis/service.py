import tokenize
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

from app.core.errors import (
    RepositoryNotFoundError,
    SnapshotNotFoundError,
    SnapshotNotReadyError,
)
from app.domain.analysis import SnapshotAnalysis
from app.domain.repositories import RepositoryMetadata, SnapshotMetadata
from app.modules.github.port import GithubClient
from app.modules.ingestion.archive import SafeZipExtractor, discover_python_files
from app.modules.ingestion.store import MetadataStore


class StructuralAnalyzer(Protocol):
    def analyze(
        self, snapshot_id: str, repository_root: Path, files: list[Path]
    ) -> SnapshotAnalysis: ...


@dataclass(frozen=True, slots=True)
class AnalyzedSnapshotSource:
    repository: RepositoryMetadata
    snapshot: SnapshotMetadata
    analysis: SnapshotAnalysis
    sources: dict[str, str]


class SnapshotAnalysisService:
    """Coordinate analysis of an immutable, already-ingested repository snapshot."""

    def __init__(
        self,
        github: GithubClient,
        store: MetadataStore,
        extractor: SafeZipExtractor,
        analyzer: StructuralAnalyzer,
    ) -> None:
        self._github = github
        self._store = store
        self._extractor = extractor
        self._analyzer = analyzer

    def analyze_snapshot(self, repository_id: str, snapshot_id: str) -> SnapshotAnalysis:
        return self.analyze_snapshot_source(repository_id, snapshot_id).analysis

    def analyze_snapshot_source(
        self, repository_id: str, snapshot_id: str
    ) -> AnalyzedSnapshotSource:
        repository = self._store.get_repository(repository_id)
        if repository is None:
            raise RepositoryNotFoundError("Repository was not found")

        snapshot = self._store.get_snapshot(repository_id, snapshot_id)
        if snapshot is None:
            raise SnapshotNotFoundError("Snapshot was not found")
        if snapshot.status not in {"ready", "ready_with_warnings"}:
            raise SnapshotNotReadyError("Snapshot is not ready for analysis")

        archive = self._github.download_archive(
            repository.owner,
            repository.name,
            snapshot.commit_sha,
        )
        with TemporaryDirectory(prefix="codegraph-analysis-") as temporary_directory:
            repository_root = self._extractor.extract(archive, Path(temporary_directory))
            files = discover_python_files(repository_root)
            analysis = self._analyzer.analyze(snapshot.id, repository_root, files)
            sources = self._read_sources(repository_root, files)
            return AnalyzedSnapshotSource(repository, snapshot, analysis, sources)

    @staticmethod
    def _read_sources(repository_root: Path, files: list[Path]) -> dict[str, str]:
        sources: dict[str, str] = {}
        for relative_path in files:
            try:
                raw_source = (repository_root / relative_path).read_bytes()
                encoding, _ = tokenize.detect_encoding(BytesIO(raw_source).readline)
                sources[relative_path.as_posix()] = raw_source.decode(encoding)
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
        return sources
