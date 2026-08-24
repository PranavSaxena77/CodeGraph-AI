from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.core.errors import (
    ArchiveLimitError,
    GithubRepositoryNotFoundError,
    GithubServiceError,
    GraphSnapshotNotFoundError,
    GraphStoreError,
    InvalidGithubUrlError,
    MetadataStoreError,
    RepositoryNotFoundError,
    SnapshotNotFoundError,
    SnapshotNotReadyError,
    UnsafeArchiveError,
)
from app.domain.analysis import SnapshotAnalysis
from app.domain.graph import GraphPersistenceStatus
from app.domain.repositories import (
    RepositoryMetadata,
    RepositoryRegistrationRequest,
    RepositoryRegistrationResponse,
    SnapshotMetadata,
)
from app.modules.analysis.python_ast import PythonAstAnalyzer
from app.modules.analysis.service import SnapshotAnalysisService
from app.modules.github.rest import GithubRestClient
from app.modules.graph.neo4j import Neo4jGraphStore
from app.modules.graph.service import GraphPersistenceService
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


@lru_cache
def get_analysis_service() -> SnapshotAnalysisService:
    settings = get_settings()
    return SnapshotAnalysisService(
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
        analyzer=PythonAstAnalyzer(),
    )


AnalysisService = Annotated[SnapshotAnalysisService, Depends(get_analysis_service)]


@lru_cache
def get_graph_service() -> GraphPersistenceService:
    settings = get_settings()
    metadata_store = MongoMetadataStore(settings)
    analysis_service = SnapshotAnalysisService(
        github=GithubRestClient(
            api_base_url=settings.github_api_base_url,
            timeout_seconds=settings.github_timeout_seconds,
            max_archive_bytes=settings.max_archive_bytes,
        ),
        store=metadata_store,
        extractor=SafeZipExtractor(
            max_members=settings.max_archive_members,
            max_extracted_bytes=settings.max_extracted_bytes,
            max_file_bytes=settings.max_archive_member_bytes,
        ),
        analyzer=PythonAstAnalyzer(),
    )
    try:
        graph_store = Neo4jGraphStore(settings)
    except GraphStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return GraphPersistenceService(
        metadata_store=metadata_store,
        analyzer=analysis_service,
        graph_store=graph_store,
    )


GraphService = Annotated[GraphPersistenceService, Depends(get_graph_service)]


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


@router.post(
    "/{repository_id}/snapshots/{snapshot_id}/analysis",
    response_model=SnapshotAnalysis,
)
def analyze_snapshot(
    repository_id: str,
    snapshot_id: str,
    service: AnalysisService,
) -> SnapshotAnalysis:
    try:
        return service.analyze_snapshot(repository_id, snapshot_id)
    except (RepositoryNotFoundError, SnapshotNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SnapshotNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (UnsafeArchiveError, ArchiveLimitError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except GithubRepositoryNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except GithubServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except MetadataStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post(
    "/{repository_id}/snapshots/{snapshot_id}/graph",
    response_model=GraphPersistenceStatus,
)
def persist_snapshot_graph(
    repository_id: str,
    snapshot_id: str,
    service: GraphService,
) -> GraphPersistenceStatus:
    try:
        return service.analyze_and_persist(repository_id, snapshot_id)
    except (RepositoryNotFoundError, SnapshotNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SnapshotNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (UnsafeArchiveError, ArchiveLimitError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except GithubRepositoryNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except GithubServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (MetadataStoreError, GraphStoreError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get(
    "/{repository_id}/snapshots/{snapshot_id}/graph",
    response_model=GraphPersistenceStatus,
)
def get_snapshot_graph_status(
    repository_id: str,
    snapshot_id: str,
    service: GraphService,
) -> GraphPersistenceStatus:
    try:
        return service.get_status(repository_id, snapshot_id)
    except (RepositoryNotFoundError, SnapshotNotFoundError, GraphSnapshotNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (MetadataStoreError, GraphStoreError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
