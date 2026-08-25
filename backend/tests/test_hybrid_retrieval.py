from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.core.errors import RetrievalIdentityMismatchError
from app.domain.graph import GraphNeighborhood, GraphNode, GraphRelationship
from app.domain.retrieval import HybridSearchRequest
from app.domain.vector import VectorSearchRequest, VectorSearchResponse, VectorSearchResult
from app.modules.retrieval.ranking import (
    MAX_EXACT_BOOST,
    deduplicate_candidates,
    rank_candidates,
    reciprocal_rank,
)
from app.modules.retrieval.service import HybridRetriever


def result(
    chunk_id: str,
    *,
    score: float = 0.9,
    file_path: str = "src/service.py",
    symbol_id: str | None = "symbol-service",
    symbol_name: str = "run",
    qualified_name: str = "src.service.run",
    start_line: int = 10,
    end_line: int = 15,
    content: str = "def run():\n    return helper()",
) -> VectorSearchResult:
    return VectorSearchResult(
        score=score,
        chunk_id=chunk_id,
        file_path=file_path,
        symbol_id=symbol_id,
        symbol_name=symbol_name,
        qualified_name=qualified_name,
        symbol_type="function",
        start_line=start_line,
        end_line=end_line,
        content=content,
    )


class FakeVectorSearcher:
    def __init__(self, results: list[VectorSearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, str, int]] = []
        self.response_repository_id = "repository-1"
        self.response_snapshot_id = "snapshot-1"

    def search(
        self, repository_id: str, snapshot_id: str, request: VectorSearchRequest
    ) -> VectorSearchResponse:
        top_k = request.top_k
        self.calls.append((repository_id, snapshot_id, top_k))
        return VectorSearchResponse(
            repository_id=self.response_repository_id,
            snapshot_id=self.response_snapshot_id,
            query=request.query,
            results=deepcopy(self.results[:top_k]),
        )


class FakeGraphReader:
    def __init__(self, neighborhood: GraphNeighborhood | None = None) -> None:
        self.neighborhood = neighborhood or GraphNeighborhood()
        self.calls: list[tuple[str, str, list[str], int]] = []

    def get_retrieval_context(
        self,
        repository_id: str,
        snapshot_id: str,
        symbol_ids: list[str],
        max_neighbors_per_symbol: int,
    ) -> GraphNeighborhood:
        self.calls.append((repository_id, snapshot_id, symbol_ids, max_neighbors_per_symbol))
        return deepcopy(self.neighborhood)


def graph_for(symbol_id: str = "symbol-helper") -> GraphNeighborhood:
    return GraphNeighborhood(
        nodes=[
            GraphNode(
                id=symbol_id,
                node_type="Function",
                repository_id="repository-1",
                snapshot_id="snapshot-1",
                file_path="src/helper.py",
                symbol_name="helper",
                qualified_name="src.helper.helper",
                symbol_type="function",
                start_line=1,
                end_line=2,
            ),
            GraphNode(
                id="symbol-target",
                node_type="Function",
                repository_id="repository-1",
                snapshot_id="snapshot-1",
                file_path="src/target.py",
                symbol_name="target",
                qualified_name="src.target.target",
                symbol_type="function",
                start_line=1,
                end_line=2,
            ),
        ],
        relationships=[
            GraphRelationship(
                id="call-1",
                relationship_type="CALLS",
                source_id=symbol_id,
                target_id="symbol-target",
                repository_id="repository-1",
                snapshot_id="snapshot-1",
            )
        ],
    )


def test_reciprocal_rank_fusion_is_deterministic() -> None:
    candidates = [result("first"), result("second", symbol_id="symbol-helper")]

    first = rank_candidates("how does this work", candidates, {"symbol-helper": {"CALLS"}})
    second = rank_candidates("how does this work", candidates, {"symbol-helper": {"CALLS"}})

    assert first == second
    assert first[0].result.chunk_id == "second"
    assert first[0].final_score == pytest.approx(
        reciprocal_rank(2) + reciprocal_rank(1, weight=0.7)
    )


def test_exact_symbol_and_qualified_name_boost_is_bounded() -> None:
    ranked = rank_candidates(
        "Explain src.service.run and run",
        [result("exact"), result("other", symbol_id="other", symbol_name="other")],
        {},
    )

    assert ranked[0].result.chunk_id == "exact"
    assert ranked[0].exact_boost <= MAX_EXACT_BOOST
    assert "exact_symbol_name" in ranked[0].reasons
    assert "exact_qualified_name" in ranked[0].reasons


def test_exact_filename_and_path_boosts() -> None:
    filename = rank_candidates("Explain service.py", [result("filename")], {})[0]
    path = rank_candidates("Explain src/service.py", [result("path")], {})[0]

    assert "exact_filename" in filename.reasons
    assert "exact_file_path" not in filename.reasons
    assert "exact_file_path" in path.reasons
    assert path.exact_boost > filename.exact_boost


def test_vector_only_candidates_remain_available() -> None:
    vector = FakeVectorSearcher(
        [result("first"), result("second", symbol_id=None, file_path="src/other.py")]
    )
    graph = FakeGraphReader()
    retriever = HybridRetriever(vector, graph)

    response = retriever.search(
        "repository-1", "snapshot-1", HybridSearchRequest(query="behavior", top_k=2)
    )

    assert [item.chunk_id for item in response.evidence] == ["first", "second"]
    assert all(item.graph_contribution == 0 for item in response.evidence)
    assert vector.calls == [("repository-1", "snapshot-1", 6)]


def test_graph_enrichment_reranks_and_is_bounded() -> None:
    vector = FakeVectorSearcher(
        [result("vector-first"), result("connected", symbol_id="symbol-helper")]
    )
    graph = FakeGraphReader(graph_for())
    retriever = HybridRetriever(vector, graph, max_graph_seeds=2, max_neighbors_per_symbol=4)

    response = retriever.search(
        "repository-1", "snapshot-1", HybridSearchRequest(query="behavior", top_k=2)
    )

    assert response.evidence[0].chunk_id == "connected"
    assert response.evidence[0].graph_contribution > 0
    assert "graph_relationships:CALLS" in response.evidence[0].retrieval_reasons
    assert graph.calls == [
        (
            "repository-1",
            "snapshot-1",
            ["symbol-service", "symbol-helper"],
            4,
        )
    ]
    assert response.metadata.graph_max_depth == 1


def test_repeated_hybrid_queries_return_identical_results() -> None:
    retriever = HybridRetriever(
        FakeVectorSearcher(
            [result("vector-first"), result("connected", symbol_id="symbol-helper")]
        ),
        FakeGraphReader(graph_for()),
    )
    request = HybridSearchRequest(query="behavior", top_k=2)

    first = retriever.search("repository-1", "snapshot-1", request)
    second = retriever.search("repository-1", "snapshot-1", request)

    assert first == second


def test_deduplicates_overlapping_symbol_regions_and_preserves_provenance() -> None:
    candidates = rank_candidates(
        "behavior",
        [
            result("part-1", start_line=10, end_line=20),
            result("part-2", start_line=18, end_line=30),
        ],
        {},
    )

    deduplicated, count = deduplicate_candidates(candidates)

    assert count == 1
    assert [item.result.chunk_id for item in deduplicated] == ["part-1"]
    assert "vector_rank:2" in deduplicated[0].reasons
    assert "deduplicated_chunk:part-2" in deduplicated[0].reasons


def test_context_budget_limits_items_and_source_characters() -> None:
    vector = FakeVectorSearcher(
        [
            result("large", content="a" * 15),
            result("unused", symbol_id="other", content="b" * 15),
        ]
    )
    retriever = HybridRetriever(vector, FakeGraphReader(), max_source_characters=10)

    response = retriever.search(
        "repository-1", "snapshot-1", HybridSearchRequest(query="behavior", top_k=2)
    )

    assert len(response.evidence) == 1
    assert response.evidence[0].content == "a" * 10
    assert response.metadata.source_characters == 10
    assert "content_truncated_by_budget" in response.evidence[0].retrieval_reasons


def test_top_k_validation() -> None:
    with pytest.raises(ValidationError):
        HybridSearchRequest(query="query", top_k=0)
    with pytest.raises(ValidationError):
        HybridSearchRequest(query="query", top_k=21)


def test_vector_snapshot_mismatch_is_rejected() -> None:
    vector = FakeVectorSearcher([result("candidate")])
    vector.response_snapshot_id = "snapshot-2"
    retriever = HybridRetriever(vector, FakeGraphReader())

    with pytest.raises(RetrievalIdentityMismatchError, match="Vector"):
        retriever.search("repository-1", "snapshot-1", HybridSearchRequest(query="behavior"))


def test_graph_repository_or_snapshot_mismatch_is_rejected() -> None:
    graph = graph_for()
    graph.nodes[0] = graph.nodes[0].model_copy(update={"snapshot_id": "snapshot-2"})
    retriever = HybridRetriever(
        FakeVectorSearcher([result("candidate", symbol_id="symbol-helper")]),
        FakeGraphReader(graph),
    )

    with pytest.raises(RetrievalIdentityMismatchError, match="Graph"):
        retriever.search("repository-1", "snapshot-1", HybridSearchRequest(query="behavior"))


def test_insufficient_evidence_is_explicit() -> None:
    response = HybridRetriever(
        FakeVectorSearcher([result("irrelevant", score=-0.1)]), FakeGraphReader()
    ).search("repository-1", "snapshot-1", HybridSearchRequest(query="unknown behavior"))

    assert response.evidence == []
    assert response.metadata.outcome == "insufficient"
    assert response.metadata.returned_count == 0
