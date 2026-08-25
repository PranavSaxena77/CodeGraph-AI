from datetime import UTC, datetime

import pytest

from app.core.errors import (
    CitationValidationError,
    MalformedReasoningOutputError,
    ReasoningProviderError,
    RetrievalIdentityMismatchError,
)
from app.domain.qa import ReasoningOutput, RepositoryQuestionRequest
from app.domain.repositories import SnapshotMetadata
from app.domain.retrieval import (
    HybridEvidence,
    HybridRetrievalMetadata,
    HybridSearchRequest,
    HybridSearchResponse,
)
from app.modules.ai.fake import DeterministicReasoningProvider
from app.modules.qa.service import RepositoryQuestionService
from tests.fakes import InMemoryMetadataStore


def metadata(outcome: str = "sufficient") -> HybridRetrievalMetadata:
    return HybridRetrievalMetadata(
        outcome=outcome,
        vector_candidate_count=1 if outcome == "sufficient" else 0,
        graph_enriched_count=0,
        deduplicated_count=0,
        returned_count=1 if outcome == "sufficient" else 0,
        source_characters=32 if outcome == "sufficient" else 0,
        candidate_multiplier=3,
        graph_max_depth=1,
        graph_max_neighbors_per_symbol=12,
        fusion_strategy="weighted_rrf",
    )


def evidence(
    chunk_id: str = "chunk-1", *, content: str = "def authenticate(token): return token"
) -> HybridEvidence:
    return HybridEvidence(
        chunk_id=chunk_id,
        file_path="src/auth.py",
        symbol_id="symbol-authenticate",
        symbol_name="authenticate",
        qualified_name="src.auth.authenticate",
        symbol_type="function",
        start_line=10,
        end_line=11,
        content=content,
        vector_score=0.9,
        graph_contribution=0.0,
        final_hybrid_score=0.02,
        retrieval_reasons=["vector_rank:1"],
    )


class StubHybridSearcher:
    def __init__(self, response: HybridSearchResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, str, str, int]] = []

    def search(
        self, repository_id: str, snapshot_id: str, request: HybridSearchRequest
    ) -> HybridSearchResponse:
        self.calls.append(
            (
                repository_id,
                snapshot_id,
                request.query,
                request.top_k,
            )
        )
        return self.response.model_copy(deep=True)


def build_service(
    provider: DeterministicReasoningProvider,
    *,
    response: HybridSearchResponse | None = None,
    max_evidence_characters: int = 30_000,
) -> RepositoryQuestionService:
    store = InMemoryMetadataStore()
    store.save_snapshot(
        SnapshotMetadata(
            id="snapshot-1",
            repository_id="repository-1",
            commit_sha="a" * 40,
            ref="main",
            status="ready",
            discovered_file_count=1,
            created_at=datetime.now(UTC),
        )
    )
    retrieval = response or HybridSearchResponse(
        repository_id="repository-1",
        snapshot_id="snapshot-1",
        query="How is authentication implemented?",
        evidence=[evidence()],
        metadata=metadata(),
    )
    return RepositoryQuestionService(
        snapshot_reader=store,
        hybrid_searcher=StubHybridSearcher(retrieval),
        reasoning_provider=provider,
        max_evidence_characters=max_evidence_characters,
    )


def test_valid_grounded_answer_uses_server_owned_citation_metadata() -> None:
    provider = DeterministicReasoningProvider(
        ReasoningOutput(
            answer="Authentication returns the supplied token.",
            cited_evidence_ids=["E1"],
            limitations=["Token validation is not visible in the selected evidence."],
        ).model_dump_json()
    )
    service = build_service(provider)

    response = service.ask(
        "repository-1",
        "snapshot-1",
        RepositoryQuestionRequest(question="How is authentication implemented?"),
    )

    assert response.outcome == "answered"
    assert response.cited_evidence_ids == ["E1"]
    assert response.commit_sha == "a" * 40
    assert response.evidence[0].file_path == "src/auth.py"
    assert response.evidence[0].symbol_name == "authenticate"
    assert response.evidence[0].start_line == 10
    assert response.evidence[0].snapshot_id == "snapshot-1"
    assert provider.requests[0].evidence[0].evidence_id == "E1"


def test_insufficient_evidence_does_not_call_reasoning_provider() -> None:
    provider = DeterministicReasoningProvider()
    retrieval = HybridSearchResponse(
        repository_id="repository-1",
        snapshot_id="snapshot-1",
        query="unknown",
        metadata=metadata("insufficient"),
    )
    service = build_service(provider, response=retrieval)

    response = service.ask(
        "repository-1",
        "snapshot-1",
        RepositoryQuestionRequest(question="unknown"),
    )

    assert response.outcome == "insufficient_evidence"
    assert response.evidence == []
    assert provider.requests == []


def test_fabricated_or_out_of_context_citation_is_rejected() -> None:
    provider = DeterministicReasoningProvider(
        ReasoningOutput(
            answer="Fabricated answer",
            cited_evidence_ids=["E99"],
        ).model_dump_json()
    )

    with pytest.raises(CitationValidationError, match="not supplied"):
        build_service(provider).ask(
            "repository-1",
            "snapshot-1",
            RepositoryQuestionRequest(question="How does it work?"),
        )


def test_citation_to_retrieved_but_unselected_evidence_is_rejected() -> None:
    provider = DeterministicReasoningProvider(
        ReasoningOutput(
            answer="Outside the bounded context",
            cited_evidence_ids=["E2"],
        ).model_dump_json()
    )
    first = evidence(content="a" * 10)
    second = evidence("chunk-2", content="b" * 10).model_copy(
        update={
            "file_path": "src/other.py",
            "symbol_id": "symbol-other",
            "symbol_name": "other",
            "qualified_name": "src.other.other",
        }
    )
    retrieval = HybridSearchResponse(
        repository_id="repository-1",
        snapshot_id="snapshot-1",
        query="question",
        evidence=[first, second],
        metadata=metadata(),
    )

    with pytest.raises(CitationValidationError, match="not supplied"):
        build_service(
            provider,
            response=retrieval,
            max_evidence_characters=10,
        ).ask(
            "repository-1",
            "snapshot-1",
            RepositoryQuestionRequest(question="How does it work?"),
        )


@pytest.mark.parametrize(
    "raw_output",
    ["not-json", '{"answer":"Missing citations"}', '{"answer":1,"cited_evidence_ids":[]}'],
)
def test_malformed_reasoning_output_is_rejected(raw_output: str) -> None:
    provider = DeterministicReasoningProvider(raw_output)

    with pytest.raises(MalformedReasoningOutputError, match="malformed"):
        build_service(provider).ask(
            "repository-1",
            "snapshot-1",
            RepositoryQuestionRequest(question="How does it work?"),
        )


def test_reasoning_provider_failure_is_propagated() -> None:
    provider = DeterministicReasoningProvider(failure_message="provider unavailable")

    with pytest.raises(ReasoningProviderError, match="provider unavailable"):
        build_service(provider).ask(
            "repository-1",
            "snapshot-1",
            RepositoryQuestionRequest(question="How does it work?"),
        )


def test_retrieval_snapshot_identity_mismatch_is_rejected() -> None:
    retrieval = HybridSearchResponse(
        repository_id="repository-1",
        snapshot_id="snapshot-2",
        query="question",
        evidence=[evidence()],
        metadata=metadata(),
    )

    with pytest.raises(RetrievalIdentityMismatchError, match="Retrieved evidence"):
        build_service(DeterministicReasoningProvider(), response=retrieval).ask(
            "repository-1",
            "snapshot-1",
            RepositoryQuestionRequest(question="How does it work?"),
        )


def test_reasoning_context_has_an_independent_character_budget() -> None:
    provider = DeterministicReasoningProvider()
    service = build_service(provider, max_evidence_characters=10)

    response = service.ask(
        "repository-1",
        "snapshot-1",
        RepositoryQuestionRequest(question="How does it work?"),
    )

    assert response.outcome == "answered"
    assert provider.requests[0].evidence[0].content == "def authen"
    assert response.evidence[0].content == "def authen"
