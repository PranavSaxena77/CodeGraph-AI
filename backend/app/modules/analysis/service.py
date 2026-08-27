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
from app.modules.operations.port import NULL_OPERATION_REPORTER, OperationReporter


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

    def analyze_snapshot(
        self,
        repository_id: str,
        snapshot_id: str,
        reporter: OperationReporter | None = None,
    ) -> SnapshotAnalysis:
        active_reporter = reporter or NULL_OPERATION_REPORTER
        if reporter is not None:
            active_reporter.start_stage("analysis")
        try:
            analyzed = self.analyze_snapshot_source(
                repository_id,
                snapshot_id,
                reporter=active_reporter,
            )
        except Exception:
            if reporter is not None:
                active_reporter.fail_stage("analysis")
            raise
        if reporter is not None:
            active_reporter.complete_stage("analysis", self._metrics(analyzed.analysis))
        return analyzed.analysis

    def analyze_snapshot_source(
        self,
        repository_id: str,
        snapshot_id: str,
        reporter: OperationReporter | None = None,
    ) -> AnalyzedSnapshotSource:
        active_reporter = reporter or NULL_OPERATION_REPORTER
        snapshot_event = active_reporter.start_event(
            "analysis", "Loading immutable repository snapshot"
        )
        repository = self._store.get_repository(repository_id)
        if repository is None:
            raise RepositoryNotFoundError("Repository was not found")

        snapshot = self._store.get_snapshot(repository_id, snapshot_id)
        if snapshot is None:
            raise SnapshotNotFoundError("Snapshot was not found")
        if snapshot.status not in {"ready", "ready_with_warnings"}:
            raise SnapshotNotReadyError("Snapshot is not ready for analysis")
        active_reporter.complete_event(snapshot_event)

        archive_event = active_reporter.start_event("analysis", "Downloading snapshot archive")
        archive = self._github.download_archive(
            repository.owner,
            repository.name,
            snapshot.commit_sha,
        )
        active_reporter.complete_event(archive_event)
        with TemporaryDirectory(prefix="codegraph-analysis-") as temporary_directory:
            extraction_event = active_reporter.start_event(
                "analysis", "Validating and extracting snapshot archive"
            )
            repository_root = self._extractor.extract(archive, Path(temporary_directory))
            active_reporter.complete_event(extraction_event)
            discovery_event = active_reporter.start_event("analysis", "Discovering Python files")
            files = discover_python_files(repository_root)
            active_reporter.complete_event(
                discovery_event,
                metric_key="python_files",
                metric_label="Python files",
                metric_value=len(files),
            )
            analysis_event = active_reporter.start_event(
                "analysis", "Parsing Python ASTs and extracting structural records"
            )
            analysis = self._analyzer.analyze(snapshot.id, repository_root, files)
            active_reporter.complete_event(
                analysis_event,
                metric_key="symbols",
                metric_label="Symbols",
                metric_value=len(analysis.symbols),
            )
            source_event = active_reporter.start_event("analysis", "Reading bounded source records")
            sources = self._read_sources(repository_root, files)
            active_reporter.complete_event(source_event)
            return AnalyzedSnapshotSource(repository, snapshot, analysis, sources)

    @staticmethod
    def _metrics(analysis: SnapshotAnalysis) -> dict[str, tuple[str, int]]:
        symbol_counts = {
            symbol_type: sum(symbol.symbol_type == symbol_type for symbol in analysis.symbols)
            for symbol_type in ("file", "class", "function", "method")
        }
        return {
            "python_files": ("Python files", symbol_counts["file"]),
            "classes": ("Classes", symbol_counts["class"]),
            "functions": ("Functions", symbol_counts["function"]),
            "methods": ("Methods", symbol_counts["method"]),
            "imports": ("Imports", len(analysis.imports)),
            "inheritances": ("Inheritance records", len(analysis.inheritances)),
            "resolved_calls": (
                "Resolved calls",
                sum(call.resolution == "resolved" for call in analysis.calls),
            ),
            "diagnostics": ("Diagnostics", len(analysis.diagnostics)),
        }

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
