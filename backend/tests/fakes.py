from copy import deepcopy

from app.domain.repositories import RepositoryMetadata, SnapshotMetadata
from app.modules.github.port import GithubRepository


class FakeGithubClient:
    def __init__(self, archive: bytes) -> None:
        self.archive = archive
        self.repository = GithubRepository(
            owner="octocat",
            name="hello-python",
            html_url="https://github.com/octocat/hello-python",
            default_branch="main",
        )
        self.commit_sha = "a" * 40
        self.resolved_refs: list[str] = []
        self.download_count = 0

    def get_repository(self, owner: str, name: str) -> GithubRepository:
        assert owner.lower() == "octocat"
        assert name.lower() == "hello-python"
        return self.repository

    def resolve_ref(self, owner: str, name: str, ref: str) -> str:
        assert owner == self.repository.owner
        assert name == self.repository.name
        self.resolved_refs.append(ref)
        return self.commit_sha

    def download_archive(self, owner: str, name: str, commit_sha: str) -> bytes:
        assert owner == self.repository.owner
        assert name == self.repository.name
        assert commit_sha == self.commit_sha
        self.download_count += 1
        return self.archive


class InMemoryMetadataStore:
    def __init__(self) -> None:
        self.repositories: dict[str, RepositoryMetadata] = {}
        self.snapshots: dict[str, SnapshotMetadata] = {}

    def get_repository(self, repository_id: str) -> RepositoryMetadata | None:
        repository = self.repositories.get(repository_id)
        return deepcopy(repository)

    def get_repository_by_slug(self, owner: str, name: str) -> RepositoryMetadata | None:
        for repository in self.repositories.values():
            if (
                repository.owner.lower() == owner.lower()
                and repository.name.lower() == name.lower()
            ):
                return deepcopy(repository)
        return None

    def save_repository(self, repository: RepositoryMetadata) -> RepositoryMetadata:
        self.repositories.setdefault(repository.id, deepcopy(repository))
        return deepcopy(self.repositories[repository.id])

    def get_snapshot(self, repository_id: str, snapshot_id: str) -> SnapshotMetadata | None:
        snapshot = self.snapshots.get(snapshot_id)
        if snapshot is None or snapshot.repository_id != repository_id:
            return None
        return deepcopy(snapshot)

    def get_snapshot_by_commit(
        self, repository_id: str, commit_sha: str
    ) -> SnapshotMetadata | None:
        for snapshot in self.snapshots.values():
            if snapshot.repository_id == repository_id and snapshot.commit_sha == commit_sha:
                return deepcopy(snapshot)
        return None

    def save_snapshot(self, snapshot: SnapshotMetadata) -> SnapshotMetadata:
        self.snapshots[snapshot.id] = deepcopy(snapshot)
        return deepcopy(snapshot)
