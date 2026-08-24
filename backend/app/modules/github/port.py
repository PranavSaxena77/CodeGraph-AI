from typing import Protocol

from pydantic import BaseModel


class GithubRepository(BaseModel):
    owner: str
    name: str
    html_url: str
    default_branch: str
    is_private: bool = False


class GithubClient(Protocol):
    def get_repository(self, owner: str, name: str) -> GithubRepository:
        """Return public repository metadata."""
        ...

    def resolve_ref(self, owner: str, name: str, ref: str) -> str:
        """Resolve a branch, tag, or commit-like ref to an immutable commit SHA."""
        ...

    def download_archive(self, owner: str, name: str, commit_sha: str) -> bytes:
        """Download a bounded ZIP source archive for an immutable commit."""
        ...
