from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import NAMESPACE_URL, uuid5

from app.core.errors import (
    ApplicationError,
    RepositoryNotFoundError,
    SnapshotNotFoundError,
)
from app.domain.repositories import (
    RepositoryMetadata,
    RepositoryRegistrationRequest,
    RepositoryRegistrationResponse,
    SnapshotMetadata,
)
from app.modules.github.port import GithubClient
from app.modules.ingestion.archive import SafeZipExtractor, discover_python_files
from app.modules.ingestion.store import MetadataStore
from app.modules.ingestion.url import parse_github_repository_url


class RepositoryIngestionService:
    def __init__(
        self,
        github: GithubClient,
        store: MetadataStore,
        extractor: SafeZipExtractor,
    ) -> None:
        self._github = github
        self._store = store
        self._extractor = extractor

    def register(self, request: RepositoryRegistrationRequest) -> RepositoryRegistrationResponse:
        location = parse_github_repository_url(request.github_url)
        github_repository = self._github.get_repository(location.owner, location.name)
        resolved_ref = request.ref or github_repository.default_branch
        commit_sha = self._github.resolve_ref(
            github_repository.owner, github_repository.name, resolved_ref
        )

        repository_id = str(uuid5(NAMESPACE_URL, github_repository.html_url.lower()))
        repository = self._store.get_repository_by_slug(
            github_repository.owner, github_repository.name
        )
        if repository is None:
            repository = self._store.save_repository(
                RepositoryMetadata(
                    id=repository_id,
                    owner=github_repository.owner,
                    name=github_repository.name,
                    github_url=github_repository.html_url,
                    default_branch=github_repository.default_branch,
                    created_at=datetime.now(UTC),
                )
            )

        existing_snapshot = self._store.get_snapshot_by_commit(repository.id, commit_sha)
        if existing_snapshot is not None:
            return RepositoryRegistrationResponse(
                repository=repository,
                snapshot=existing_snapshot,
                idempotent=True,
            )

        snapshot = SnapshotMetadata(
            id=str(uuid5(NAMESPACE_URL, f"{repository.id}:{commit_sha}")),
            repository_id=repository.id,
            commit_sha=commit_sha,
            ref=resolved_ref,
            status="indexing",
            discovered_file_count=0,
            created_at=datetime.now(UTC),
        )
        snapshot = self._store.save_snapshot(snapshot)

        try:
            archive = self._github.download_archive(
                github_repository.owner, github_repository.name, commit_sha
            )
            with TemporaryDirectory(prefix="codegraph-ingestion-") as temporary_directory:
                repository_root = self._extractor.extract(archive, Path(temporary_directory))
                discovered_files = discover_python_files(repository_root)
            snapshot = snapshot.model_copy(
                update={
                    "status": "ready",
                    "discovered_file_count": len(discovered_files),
                }
            )
            snapshot = self._store.save_snapshot(snapshot)
        except ApplicationError as error:
            failed_snapshot = snapshot.model_copy(
                update={"status": "failed", "errors": [str(error)]}
            )
            self._store.save_snapshot(failed_snapshot)
            raise

        return RepositoryRegistrationResponse(
            repository=repository,
            snapshot=snapshot,
            idempotent=False,
        )

    def get_repository(self, repository_id: str) -> RepositoryMetadata:
        repository = self._store.get_repository(repository_id)
        if repository is None:
            raise RepositoryNotFoundError("Repository was not found")
        return repository

    def get_snapshot(self, repository_id: str, snapshot_id: str) -> SnapshotMetadata:
        snapshot = self._store.get_snapshot(repository_id, snapshot_id)
        if snapshot is None:
            raise SnapshotNotFoundError("Snapshot was not found")
        return snapshot
