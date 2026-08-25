from typing import Protocol

from app.core.errors import RetrievalIdentityMismatchError
from app.domain.graph import GraphNeighborhood
from app.domain.retrieval import (
    HybridEvidence,
    HybridRetrievalMetadata,
    HybridSearchRequest,
    HybridSearchResponse,
)
from app.domain.vector import VectorSearchRequest, VectorSearchResponse
from app.modules.retrieval.ranking import (
    RankedCandidate,
    deduplicate_candidates,
    rank_candidates,
)


class VectorSearcher(Protocol):
    def search(
        self, repository_id: str, snapshot_id: str, request: VectorSearchRequest
    ) -> VectorSearchResponse: ...


class GraphContextReader(Protocol):
    def get_retrieval_context(
        self,
        repository_id: str,
        snapshot_id: str,
        symbol_ids: list[str],
        max_neighbors_per_symbol: int,
    ) -> GraphNeighborhood: ...


class HybridRetriever:
    """Fuse semantic candidates with bounded structural graph evidence."""

    def __init__(
        self,
        vector_searcher: VectorSearcher,
        graph_reader: GraphContextReader,
        *,
        candidate_multiplier: int = 3,
        max_source_characters: int = 40_000,
        max_graph_seeds: int = 24,
        max_neighbors_per_symbol: int = 12,
        minimum_vector_score: float = 0.0,
    ) -> None:
        if candidate_multiplier < 1:
            raise ValueError("candidate_multiplier must be positive")
        if max_source_characters < 1:
            raise ValueError("max_source_characters must be positive")
        if max_graph_seeds < 1 or max_graph_seeds > 50:
            raise ValueError("max_graph_seeds must be between 1 and 50")
        if max_neighbors_per_symbol < 1 or max_neighbors_per_symbol > 50:
            raise ValueError("max_neighbors_per_symbol must be between 1 and 50")
        self._vector_searcher = vector_searcher
        self._graph_reader = graph_reader
        self._candidate_multiplier = candidate_multiplier
        self._max_source_characters = max_source_characters
        self._max_graph_seeds = max_graph_seeds
        self._max_neighbors_per_symbol = max_neighbors_per_symbol
        self._minimum_vector_score = minimum_vector_score

    def search(
        self,
        repository_id: str,
        snapshot_id: str,
        request: HybridSearchRequest,
    ) -> HybridSearchResponse:
        candidate_count = min(50, request.top_k * self._candidate_multiplier)
        vector_response = self._vector_searcher.search(
            repository_id,
            snapshot_id,
            VectorSearchRequest(query=request.query, top_k=candidate_count),
        )
        self._validate_vector_identity(repository_id, snapshot_id, vector_response)
        vector_results = [
            item for item in vector_response.results if item.score >= self._minimum_vector_score
        ]
        symbol_ids = list(
            dict.fromkeys(item.symbol_id for item in vector_results if item.symbol_id is not None)
        )[: self._max_graph_seeds]
        graph = self._graph_reader.get_retrieval_context(
            repository_id,
            snapshot_id,
            symbol_ids,
            self._max_neighbors_per_symbol,
        )
        self._validate_graph_identity(repository_id, snapshot_id, graph)
        relationships = self._relationships_by_seed(symbol_ids, graph)
        ranked = rank_candidates(request.query, vector_results, relationships)
        deduplicated, duplicate_count = deduplicate_candidates(ranked)
        evidence = self._apply_budget(deduplicated, request.top_k)
        graph_enriched_count = sum(item.graph_contribution > 0 for item in evidence)
        source_characters = sum(len(item.content) for item in evidence)
        return HybridSearchResponse(
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            query=request.query,
            evidence=evidence,
            metadata=HybridRetrievalMetadata(
                outcome="sufficient" if evidence else "insufficient",
                vector_candidate_count=len(vector_results),
                graph_enriched_count=graph_enriched_count,
                deduplicated_count=duplicate_count,
                returned_count=len(evidence),
                source_characters=source_characters,
                candidate_multiplier=self._candidate_multiplier,
                graph_max_depth=1,
                graph_max_neighbors_per_symbol=self._max_neighbors_per_symbol,
                fusion_strategy="weighted_rrf_k60_vector1.0_graph0.7_exact_boost_max0.006",
            ),
        )

    @staticmethod
    def _validate_vector_identity(
        repository_id: str, snapshot_id: str, response: VectorSearchResponse
    ) -> None:
        if response.repository_id != repository_id or response.snapshot_id != snapshot_id:
            raise RetrievalIdentityMismatchError(
                "Vector results do not match the requested repository snapshot"
            )

    @staticmethod
    def _validate_graph_identity(
        repository_id: str, snapshot_id: str, graph: GraphNeighborhood
    ) -> None:
        if any(
            node.repository_id != repository_id or node.snapshot_id != snapshot_id
            for node in graph.nodes
        ) or any(
            relationship.repository_id != repository_id or relationship.snapshot_id != snapshot_id
            for relationship in graph.relationships
        ):
            raise RetrievalIdentityMismatchError(
                "Graph results do not match the requested repository snapshot"
            )

    @staticmethod
    def _relationships_by_seed(
        symbol_ids: list[str], graph: GraphNeighborhood
    ) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        for symbol_id in symbol_ids:
            types: set[str] = {
                str(relationship.relationship_type)
                for relationship in graph.relationships
                if symbol_id in {relationship.source_id, relationship.target_id}
            }
            if types:
                result[symbol_id] = types
        return result

    def _apply_budget(self, candidates: list[RankedCandidate], top_k: int) -> list[HybridEvidence]:
        evidence: list[HybridEvidence] = []
        remaining = self._max_source_characters
        for candidate in candidates:
            if len(evidence) >= top_k or remaining <= 0:
                break
            content = candidate.result.content[:remaining]
            if not content:
                break
            reasons = list(candidate.reasons)
            if len(content) < len(candidate.result.content):
                reasons.append("content_truncated_by_budget")
            evidence.append(
                HybridEvidence(
                    chunk_id=candidate.result.chunk_id,
                    file_path=candidate.result.file_path,
                    symbol_id=candidate.result.symbol_id,
                    symbol_name=candidate.result.symbol_name,
                    qualified_name=candidate.result.qualified_name,
                    symbol_type=candidate.result.symbol_type,
                    start_line=candidate.result.start_line,
                    end_line=candidate.result.end_line,
                    content=content,
                    vector_score=candidate.result.score,
                    graph_contribution=candidate.graph_contribution,
                    final_hybrid_score=candidate.final_score,
                    retrieval_reasons=reasons,
                )
            )
            remaining -= len(content)
        return evidence
