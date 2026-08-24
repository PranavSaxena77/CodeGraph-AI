from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.core.errors import (
    ArchiveLimitError,
    GithubRepositoryNotFoundError,
    GithubServiceError,
    InvalidGithubUrlError,
    MetadataStoreError,
    RepositoryNotFoundError,
    SnapshotNotFoundError,
    UnsafeArchiveError,
)
from app.domain.repositories import (
    RepositoryMetadata,
    RepositoryRegistrationRequest,
    RepositoryRegistrationResponse,
    SnapshotMetadata,
)
from app.modules.github.rest import GithubRestClient
from app.modules.ingestion.archive import SafeZipExtractor
from app.modules.ingestion.service import RepositoryIngestionService
from app.modules.ingestion.store import MongoMetadataStore

router = APIRouter(prefix="/repositories", tags=["repositories"])


@lru_cache
def get_repository_service() -> RepositoryIngestionService:
    settings = get_settings()
    return RepositoryIngestionService(
        github=GithubRestClient(
            api_base_url=settings.github_api_base_url,
            timeout_seconds=settings.github_timeout_seconds,
            max_archive_bytes=settings.max_archive_bytes,
        ),
        store=MongoMetadataStore(settings),
        extractor=SafeZipExtractor(
            max_members=settings.max_archive_members,
            max_extracted_bytes=settings.max_extracted_bytes,
            max_file_bytes=settings.max_archive_member_bytes,
        ),
    )


RepositoryService = Annotated[RepositoryIngestionService, Depends(get_repository_service)]


@router.post(
    "",
    response_model=RepositoryRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_repository(
    request: RepositoryRegistrationRequest,
    service: RepositoryService,
) -> RepositoryRegistrationResponse:
    try:
        return service.register(request)
    except InvalidGithubUrlError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except GithubRepositoryNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (UnsafeArchiveError, ArchiveLimitError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except GithubServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except MetadataStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/{repository_id}", response_model=RepositoryMetadata)
def get_repository(repository_id: str, service: RepositoryService) -> RepositoryMetadata:
    try:
        return service.get_repository(repository_id)
    except RepositoryNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except MetadataStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get(
    "/{repository_id}/snapshots/{snapshot_id}",
    response_model=SnapshotMetadata,
)
def get_snapshot(
    repository_id: str,
    snapshot_id: str,
    service: RepositoryService,
) -> SnapshotMetadata:
    try:
        return service.get_snapshot(repository_id, snapshot_id)
    except SnapshotNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except MetadataStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
