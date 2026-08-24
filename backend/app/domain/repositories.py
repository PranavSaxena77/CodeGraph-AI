from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SnapshotStatus = Literal["indexing", "ready", "ready_with_warnings", "failed"]


class RepositoryMetadata(BaseModel):
    id: str
    owner: str
    name: str
    github_url: str
    default_branch: str
    created_at: datetime


class SnapshotMetadata(BaseModel):
    id: str
    repository_id: str
    commit_sha: str
    ref: str
    status: SnapshotStatus
    discovered_file_count: int = Field(ge=0)
    created_at: datetime
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class RepositoryRegistrationRequest(BaseModel):
    github_url: str = Field(min_length=1, max_length=500)
    ref: str | None = Field(default=None, max_length=255)

    @field_validator("github_url")
    @classmethod
    def strip_github_url(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("github_url cannot be blank")
        return stripped

    @field_validator("ref")
    @classmethod
    def strip_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class RepositoryRegistrationResponse(BaseModel):
    repository: RepositoryMetadata
    snapshot: SnapshotMetadata
    idempotent: bool
