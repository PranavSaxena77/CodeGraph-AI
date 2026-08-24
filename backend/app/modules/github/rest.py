import re
from collections.abc import Iterator
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ValidationError

from app.core.errors import GithubRepositoryNotFoundError, GithubServiceError
from app.modules.github.port import GithubRepository


class _GithubOwnerResponse(BaseModel):
    login: str


class _GithubRepositoryResponse(BaseModel):
    owner: _GithubOwnerResponse
    name: str
    html_url: str
    default_branch: str
    private: bool


class GithubRestClient:
    """Read-only adapter for the public GitHub REST API."""

    def __init__(self, api_base_url: str, timeout_seconds: float, max_archive_bytes: int) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_archive_bytes = max_archive_bytes
        self._headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "CodeGraph-AI/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_repository(self, owner: str, name: str) -> GithubRepository:
        payload = self._get_json(f"/repos/{quote(owner)}/{quote(name)}")
        try:
            validated = _GithubRepositoryResponse.model_validate(payload)
            repository = GithubRepository(
                owner=validated.owner.login,
                name=validated.name,
                html_url=validated.html_url,
                default_branch=validated.default_branch,
                is_private=validated.private,
            )
        except ValidationError as error:
            raise GithubServiceError("GitHub returned malformed repository metadata") from error
        if repository.is_private:
            raise GithubRepositoryNotFoundError("Only public GitHub repositories are supported")
        return repository

    def resolve_ref(self, owner: str, name: str, ref: str) -> str:
        encoded_ref = quote(ref, safe="")
        payload = self._get_json(f"/repos/{quote(owner)}/{quote(name)}/commits/{encoded_ref}")
        commit_sha = payload.get("sha")
        if not isinstance(commit_sha, str) or re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha) is None:
            raise GithubServiceError("GitHub returned an invalid commit SHA")
        return commit_sha

    def download_archive(self, owner: str, name: str, commit_sha: str) -> bytes:
        path = f"/repos/{quote(owner)}/{quote(name)}/zipball/{quote(commit_sha)}"
        try:
            with (
                httpx.Client(
                    base_url=self._api_base_url,
                    headers=self._headers,
                    timeout=self._timeout_seconds,
                    follow_redirects=True,
                ) as client,
                client.stream("GET", path) as response,
            ):
                self._raise_for_status(response)
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > self._max_archive_bytes:
                    raise GithubServiceError("Repository archive exceeds the configured limit")
                return b"".join(self._bounded_chunks(response.iter_bytes()))
        except GithubServiceError:
            raise
        except (httpx.HTTPError, ValueError) as error:
            raise GithubServiceError("GitHub archive download failed") from error

    def _bounded_chunks(self, chunks: Iterator[bytes]) -> Iterator[bytes]:
        total = 0
        for chunk in chunks:
            total += len(chunk)
            if total > self._max_archive_bytes:
                raise GithubServiceError("Repository archive exceeds the configured limit")
            yield chunk

    def _get_json(self, path: str) -> dict[str, object]:
        try:
            with httpx.Client(
                base_url=self._api_base_url,
                headers=self._headers,
                timeout=self._timeout_seconds,
            ) as client:
                response = client.get(path)
            self._raise_for_status(response)
            payload = response.json()
        except GithubRepositoryNotFoundError:
            raise
        except GithubServiceError:
            raise
        except (httpx.HTTPError, ValueError) as error:
            raise GithubServiceError("GitHub API request failed") from error
        if not isinstance(payload, dict):
            raise GithubServiceError("GitHub returned an unexpected response")
        return payload

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 404:
            raise GithubRepositoryNotFoundError("GitHub repository or ref was not found")
        if response.is_error:
            raise GithubServiceError(
                f"GitHub API request failed with status {response.status_code}"
            )
