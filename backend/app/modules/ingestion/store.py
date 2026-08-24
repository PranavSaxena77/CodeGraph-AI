from collections.abc import Callable
from typing import Protocol

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.core.config import Settings
from app.core.errors import MetadataStoreError
from app.domain.repositories import RepositoryMetadata, SnapshotMetadata


class MetadataStore(Protocol):
    def get_repository(self, repository_id: str) -> RepositoryMetadata | None: ...

    def get_repository_by_slug(self, owner: str, name: str) -> RepositoryMetadata | None: ...

    def save_repository(self, repository: RepositoryMetadata) -> RepositoryMetadata: ...

    def get_snapshot(self, repository_id: str, snapshot_id: str) -> SnapshotMetadata | None: ...

    def get_snapshot_by_commit(
        self, repository_id: str, commit_sha: str
    ) -> SnapshotMetadata | None: ...

    def save_snapshot(self, snapshot: SnapshotMetadata) -> SnapshotMetadata: ...


class MongoMetadataStore:
    """MongoDB adapter for repository and immutable snapshot metadata."""

    def __init__(self, settings: Settings) -> None:
        client: MongoClient[dict[str, object]] = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=int(settings.dependency_timeout_seconds * 1000),
        )
        database: Database[dict[str, object]] = client[settings.mongodb_database]
        self._repositories: Collection[dict[str, object]] = database["repositories"]
        self._snapshots: Collection[dict[str, object]] = database["snapshots"]
        self._indexes_ready = False

    def get_repository(self, repository_id: str) -> RepositoryMetadata | None:
        document = self._run(lambda: self._repositories.find_one({"_id": repository_id}))
        return self._repository_from_document(document)

    def get_repository_by_slug(self, owner: str, name: str) -> RepositoryMetadata | None:
        document = self._run(
            lambda: self._repositories.find_one(
                {"owner_normalized": owner.lower(), "name_normalized": name.lower()}
            )
        )
        return self._repository_from_document(document)

    def save_repository(self, repository: RepositoryMetadata) -> RepositoryMetadata:
        self._ensure_indexes()
        document: dict[str, object] = {
            "_id": repository.id,
            "owner": repository.owner,
            "owner_normalized": repository.owner.lower(),
            "name": repository.name,
            "name_normalized": repository.name.lower(),
            "github_url": repository.github_url,
            "default_branch": repository.default_branch,
            "created_at": repository.created_at,
        }
        self._run(
            lambda: self._repositories.update_one(
                {"_id": repository.id}, {"$setOnInsert": document}, upsert=True
            )
        )
        stored = self.get_repository(repository.id)
        if stored is None:
            raise MetadataStoreError("Repository metadata could not be persisted")
        return stored

    def get_snapshot(self, repository_id: str, snapshot_id: str) -> SnapshotMetadata | None:
        document = self._run(
            lambda: self._snapshots.find_one({"_id": snapshot_id, "repository_id": repository_id})
        )
        return self._snapshot_from_document(document)

    def get_snapshot_by_commit(
        self, repository_id: str, commit_sha: str
    ) -> SnapshotMetadata | None:
        document = self._run(
            lambda: self._snapshots.find_one(
                {"repository_id": repository_id, "commit_sha": commit_sha}
            )
        )
        return self._snapshot_from_document(document)

    def save_snapshot(self, snapshot: SnapshotMetadata) -> SnapshotMetadata:
        self._ensure_indexes()
        document: dict[str, object] = {
            "_id": snapshot.id,
            "repository_id": snapshot.repository_id,
            "commit_sha": snapshot.commit_sha,
            "ref": snapshot.ref,
            "status": snapshot.status,
            "discovered_file_count": snapshot.discovered_file_count,
            "created_at": snapshot.created_at,
            "warnings": snapshot.warnings,
            "errors": snapshot.errors,
        }
        self._run(lambda: self._snapshots.replace_one({"_id": snapshot.id}, document, upsert=True))
        stored = self.get_snapshot(snapshot.repository_id, snapshot.id)
        if stored is None:
            raise MetadataStoreError("Snapshot metadata could not be persisted")
        return stored

    def _ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        self._run(
            lambda: self._repositories.create_index(
                [("owner_normalized", ASCENDING), ("name_normalized", ASCENDING)],
                unique=True,
                name="repository_slug_unique",
            )
        )
        self._run(
            lambda: self._snapshots.create_index(
                [("repository_id", ASCENDING), ("commit_sha", ASCENDING)],
                unique=True,
                name="repository_commit_unique",
            )
        )
        self._indexes_ready = True

    @staticmethod
    def _repository_from_document(
        document: dict[str, object] | None,
    ) -> RepositoryMetadata | None:
        if document is None:
            return None
        return RepositoryMetadata.model_validate(
            {
                "id": str(document["_id"]),
                "owner": document["owner"],
                "name": document["name"],
                "github_url": document["github_url"],
                "default_branch": document["default_branch"],
                "created_at": document["created_at"],
            }
        )

    @staticmethod
    def _snapshot_from_document(
        document: dict[str, object] | None,
    ) -> SnapshotMetadata | None:
        if document is None:
            return None
        return SnapshotMetadata.model_validate(
            {
                "id": str(document["_id"]),
                "repository_id": document["repository_id"],
                "commit_sha": document["commit_sha"],
                "ref": document["ref"],
                "status": document["status"],
                "discovered_file_count": document["discovered_file_count"],
                "created_at": document["created_at"],
                "warnings": document.get("warnings", []),
                "errors": document.get("errors", []),
            }
        )

    @staticmethod
    def _run[T](operation: Callable[[], T]) -> T:
        try:
            return operation()
        except PyMongoError as error:
            raise MetadataStoreError("MongoDB metadata operation failed") from error
