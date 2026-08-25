from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.core.errors import (
    ArchiveLimitError,
    CitationValidationError,
    EmbeddingProviderError,
    GithubRepositoryNotFoundError,
    GithubServiceError,
    GraphSnapshotNotFoundError,
    GraphStoreError,
    InvalidGithubUrlError,
    MalformedReasoningOutputError,
    MetadataStoreError,
    ReasoningProviderError,
    RepositoryNotFoundError,
    RetrievalIdentityMismatchError,
    SnapshotNotFoundError,
    SnapshotNotReadyError,
    UnsafeArchiveError,
    VectorIndexCorruptError,
    VectorIndexNotFoundError,
    VectorStoreError,
)
from app.domain.analysis import SnapshotAnalysis
from app.domain.graph import GraphPersistenceStatus
from app.domain.qa import RepositoryAnswerResponse, RepositoryQuestionRequest
from app.domain.repositories import (
    RepositoryMetadata,
    RepositoryRegistrationRequest,
    RepositoryRegistrationResponse,
    SnapshotMetadata,
)
from app.domain.retrieval import HybridSearchRequest, HybridSearchResponse
from app.domain.vector import VectorIndexStatus, VectorSearchRequest, VectorSearchResponse
from app.modules.ai.fake import UnavailableReasoningProvider
from app.modules.ai.gemini import GeminiReasoningProvider
from app.modules.ai.port import ReasoningProvider
from app.modules.analysis.chunking import SemanticChunker
from app.modules.analysis.python_ast import PythonAstAnalyzer
from app.modules.analysis.service import SnapshotAnalysisService
from app.modules.embeddings.fake import DeterministicEmbeddingProvider
from app.modules.embeddings.gemini import GeminiEmbeddingProvider
from app.modules.embeddings.port import EmbeddingProvider
from app.modules.github.rest import GithubRestClient
from app.modules.graph.neo4j import Neo4jGraphStore
from app.modules.graph.service import GraphPersistenceService
from app.modules.ingestion.archive import SafeZipExtractor
from app.modules.ingestion.service import RepositoryIngestionService
from app.modules.ingestion.store import MongoMetadataStore
from app.modules.qa.service import RepositoryQuestionService
from app.modules.retrieval.service import HybridRetriever
from app.modules.vector.faiss_store import FaissVectorIndex
from app.modules.vector.service import VectorRetrievalService

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


def _embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider == "deterministic-local":
        return DeterministicEmbeddingProvider(settings.embedding_fake_dimension)
    if settings.embedding_provider == "gemini":
        if settings.gemini_api_key is None or not settings.gemini_api_key.get_secret_value():
            raise HTTPException(status_code=503, detail="GEMINI_API_KEY is required")
        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_embedding_model,
            dimension=settings.gemini_embedding_dimension,
            api_base_url=settings.gemini_api_base_url,
            timeout_seconds=settings.gemini_timeout_seconds,
            batch_size=settings.embedding_batch_size,
        )
    raise HTTPException(status_code=503, detail="Configured embedding provider is unsupported")


@lru_cache
def get_vector_service() -> VectorRetrievalService:
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
    return VectorRetrievalService(
        metadata_store=metadata_store,
        analyzer=analysis_service,
        chunker=SemanticChunker(settings.max_chunk_chars),
        embedding_provider=_embedding_provider(),
        vector_index=FaissVectorIndex(settings.vector_index_root),
    )


VectorService = Annotated[VectorRetrievalService, Depends(get_vector_service)]


@lru_cache
def get_hybrid_retriever() -> HybridRetriever:
    settings = get_settings()
    return HybridRetriever(
        vector_searcher=get_vector_service(),
        graph_reader=get_graph_service(),
        candidate_multiplier=settings.hybrid_candidate_multiplier,
        max_source_characters=settings.hybrid_max_source_characters,
        max_graph_seeds=settings.hybrid_max_graph_seeds,
        max_neighbors_per_symbol=settings.hybrid_max_neighbors_per_symbol,
    )


HybridService = Annotated[HybridRetriever, Depends(get_hybrid_retriever)]


def _reasoning_provider() -> ReasoningProvider:
    settings = get_settings()
    if settings.gemini_api_key is None or not settings.gemini_api_key.get_secret_value():
        return UnavailableReasoningProvider()
    return GeminiReasoningProvider(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_reasoning_model,
        api_base_url=settings.gemini_api_base_url,
        timeout_seconds=settings.gemini_timeout_seconds,
        max_output_tokens=settings.gemini_max_output_tokens,
    )


@lru_cache
def get_question_service() -> RepositoryQuestionService:
    settings = get_settings()
    return RepositoryQuestionService(
        snapshot_reader=MongoMetadataStore(settings),
        hybrid_searcher=get_hybrid_retriever(),
        reasoning_provider=_reasoning_provider(),
        retrieval_top_k=settings.qa_retrieval_top_k,
        max_evidence_characters=settings.qa_max_evidence_characters,
    )


QuestionService = Annotated[RepositoryQuestionService, Depends(get_question_service)]


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


@router.post(
    "/{repository_id}/snapshots/{snapshot_id}/vector-index",
    response_model=VectorIndexStatus,
)
def build_snapshot_vector_index(
    repository_id: str,
    snapshot_id: str,
    service: VectorService,
) -> VectorIndexStatus:
    try:
        return service.build_index(repository_id, snapshot_id)
    except (RepositoryNotFoundError, SnapshotNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SnapshotNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (UnsafeArchiveError, ArchiveLimitError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except GithubRepositoryNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (GithubServiceError, EmbeddingProviderError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (MetadataStoreError, VectorStoreError, VectorIndexCorruptError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get(
    "/{repository_id}/snapshots/{snapshot_id}/vector-index",
    response_model=VectorIndexStatus,
)
def get_snapshot_vector_index_status(
    repository_id: str,
    snapshot_id: str,
    service: VectorService,
) -> VectorIndexStatus:
    try:
        return service.get_status(repository_id, snapshot_id)
    except (
        RepositoryNotFoundError,
        SnapshotNotFoundError,
        VectorIndexNotFoundError,
    ) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (MetadataStoreError, VectorStoreError, VectorIndexCorruptError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post(
    "/{repository_id}/snapshots/{snapshot_id}/vector-search",
    response_model=VectorSearchResponse,
)
def search_snapshot_vector_index(
    repository_id: str,
    snapshot_id: str,
    request: VectorSearchRequest,
    service: VectorService,
) -> VectorSearchResponse:
    try:
        return service.search(repository_id, snapshot_id, request)
    except (
        RepositoryNotFoundError,
        SnapshotNotFoundError,
        VectorIndexNotFoundError,
    ) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except EmbeddingProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (MetadataStoreError, VectorStoreError, VectorIndexCorruptError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post(
    "/{repository_id}/snapshots/{snapshot_id}/hybrid-search",
    response_model=HybridSearchResponse,
)
def hybrid_search_snapshot(
    repository_id: str,
    snapshot_id: str,
    request: HybridSearchRequest,
    service: HybridService,
) -> HybridSearchResponse:
    try:
        return service.search(repository_id, snapshot_id, request)
    except (
        RepositoryNotFoundError,
        SnapshotNotFoundError,
        VectorIndexNotFoundError,
    ) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RetrievalIdentityMismatchError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SnapshotNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except EmbeddingProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (
        MetadataStoreError,
        VectorStoreError,
        VectorIndexCorruptError,
        GraphStoreError,
    ) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post(
    "/{repository_id}/snapshots/{snapshot_id}/ask",
    response_model=RepositoryAnswerResponse,
)
def ask_repository_question(
    repository_id: str,
    snapshot_id: str,
    request: RepositoryQuestionRequest,
    service: QuestionService,
) -> RepositoryAnswerResponse:
    try:
        return service.ask(repository_id, snapshot_id, request)
    except (
        RepositoryNotFoundError,
        SnapshotNotFoundError,
        VectorIndexNotFoundError,
    ) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RetrievalIdentityMismatchError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SnapshotNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (
        ReasoningProviderError,
        MalformedReasoningOutputError,
        CitationValidationError,
        EmbeddingProviderError,
    ) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (
        MetadataStoreError,
        VectorStoreError,
        VectorIndexCorruptError,
        GraphStoreError,
    ) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
