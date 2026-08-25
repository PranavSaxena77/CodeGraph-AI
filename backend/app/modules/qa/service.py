from typing import Protocol

from pydantic import ValidationError

from app.core.errors import (
    CitationValidationError,
    MalformedReasoningOutputError,
    RetrievalIdentityMismatchError,
    SnapshotNotFoundError,
    SnapshotNotReadyError,
)
from app.domain.qa import (
    AnswerEvidence,
    ReasoningEvidence,
    ReasoningOutput,
    ReasoningRequest,
    RepositoryAnswerResponse,
    RepositoryQuestionRequest,
)
from app.domain.repositories import SnapshotMetadata
from app.domain.retrieval import HybridEvidence, HybridSearchRequest, HybridSearchResponse
from app.modules.ai.port import ReasoningProvider


class HybridSearcher(Protocol):
    def search(
        self, repository_id: str, snapshot_id: str, request: HybridSearchRequest
    ) -> HybridSearchResponse: ...


class SnapshotReader(Protocol):
    def get_snapshot(self, repository_id: str, snapshot_id: str) -> SnapshotMetadata | None: ...


class RepositoryQuestionService:
    """Orchestrate retrieval, bounded context, reasoning, and citation validation."""

    def __init__(
        self,
        snapshot_reader: SnapshotReader,
        hybrid_searcher: HybridSearcher,
        reasoning_provider: ReasoningProvider,
        *,
        retrieval_top_k: int = 8,
        max_evidence_characters: int = 30_000,
    ) -> None:
        if retrieval_top_k < 1 or retrieval_top_k > 20:
            raise ValueError("retrieval_top_k must be between 1 and 20")
        if max_evidence_characters < 1:
            raise ValueError("max_evidence_characters must be positive")
        self._snapshot_reader = snapshot_reader
        self._hybrid_searcher = hybrid_searcher
        self._reasoning_provider = reasoning_provider
        self._retrieval_top_k = retrieval_top_k
        self._max_evidence_characters = max_evidence_characters

    def ask(
        self,
        repository_id: str,
        snapshot_id: str,
        request: RepositoryQuestionRequest,
    ) -> RepositoryAnswerResponse:
        snapshot = self._snapshot_reader.get_snapshot(repository_id, snapshot_id)
        if snapshot is None:
            raise SnapshotNotFoundError("Snapshot was not found")
        if snapshot.repository_id != repository_id or snapshot.id != snapshot_id:
            raise RetrievalIdentityMismatchError(
                "Snapshot metadata does not match the requested repository snapshot"
            )
        if snapshot.status not in {"ready", "ready_with_warnings"}:
            raise SnapshotNotReadyError("Snapshot is not ready for repository questions")
        retrieval = self._hybrid_searcher.search(
            repository_id,
            snapshot_id,
            HybridSearchRequest(query=request.question, top_k=self._retrieval_top_k),
        )
        if retrieval.repository_id != repository_id or retrieval.snapshot_id != snapshot_id:
            raise RetrievalIdentityMismatchError(
                "Retrieved evidence does not match the requested repository snapshot"
            )
        selected = self._bounded_evidence(retrieval.evidence)
        if retrieval.metadata.outcome == "insufficient" or not selected:
            return RepositoryAnswerResponse(
                repository_id=repository_id,
                snapshot_id=snapshot_id,
                commit_sha=snapshot.commit_sha,
                question=request.question,
                outcome="insufficient_evidence",
                answer="Insufficient repository evidence was retrieved to answer this question.",
                limitations=["No sufficiently relevant source evidence was available."],
                retrieval_metadata=retrieval.metadata,
            )

        reasoning_evidence = [
            self._reasoning_evidence(index, evidence)
            for index, evidence in enumerate(selected, start=1)
        ]
        raw_output = self._reasoning_provider.generate(
            ReasoningRequest(
                repository_id=repository_id,
                snapshot_id=snapshot_id,
                question=request.question,
                evidence=reasoning_evidence,
            )
        )
        try:
            model_output = ReasoningOutput.model_validate_json(raw_output)
        except ValidationError as error:
            raise MalformedReasoningOutputError(
                "Reasoning provider returned malformed structured output"
            ) from error
        evidence_by_id = {
            reasoning.evidence_id: source
            for reasoning, source in zip(reasoning_evidence, selected, strict=True)
        }
        invalid_ids = [
            evidence_id
            for evidence_id in model_output.cited_evidence_ids
            if evidence_id not in evidence_by_id
        ]
        if invalid_ids:
            raise CitationValidationError("Reasoning provider cited evidence that was not supplied")
        cited_evidence = [
            self._answer_evidence(
                evidence_id,
                evidence_by_id[evidence_id],
                repository_id,
                snapshot,
            )
            for evidence_id in model_output.cited_evidence_ids
        ]
        return RepositoryAnswerResponse(
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            commit_sha=snapshot.commit_sha,
            question=request.question,
            outcome="answered",
            answer=model_output.answer,
            cited_evidence_ids=model_output.cited_evidence_ids,
            evidence=cited_evidence,
            limitations=model_output.limitations,
            retrieval_metadata=retrieval.metadata,
        )

    def _bounded_evidence(self, evidence: list[HybridEvidence]) -> list[HybridEvidence]:
        selected: list[HybridEvidence] = []
        remaining = self._max_evidence_characters
        for item in evidence[: self._retrieval_top_k]:
            if remaining <= 0:
                break
            content = item.content[:remaining]
            if not content:
                break
            selected.append(item.model_copy(update={"content": content}))
            remaining -= len(content)
        return selected

    @staticmethod
    def _reasoning_evidence(index: int, evidence: HybridEvidence) -> ReasoningEvidence:
        return ReasoningEvidence(
            evidence_id=f"E{index}",
            chunk_id=evidence.chunk_id,
            file_path=evidence.file_path,
            symbol_name=evidence.symbol_name,
            qualified_name=evidence.qualified_name,
            symbol_type=evidence.symbol_type,
            start_line=evidence.start_line,
            end_line=evidence.end_line,
            content=evidence.content,
        )

    @staticmethod
    def _answer_evidence(
        evidence_id: str,
        evidence: HybridEvidence,
        repository_id: str,
        snapshot: SnapshotMetadata,
    ) -> AnswerEvidence:
        return AnswerEvidence(
            evidence_id=evidence_id,
            chunk_id=evidence.chunk_id,
            repository_id=repository_id,
            snapshot_id=snapshot.id,
            commit_sha=snapshot.commit_sha,
            file_path=evidence.file_path,
            symbol_id=evidence.symbol_id,
            symbol_name=evidence.symbol_name,
            qualified_name=evidence.qualified_name,
            symbol_type=evidence.symbol_type,
            start_line=evidence.start_line,
            end_line=evidence.end_line,
            content=evidence.content,
        )
