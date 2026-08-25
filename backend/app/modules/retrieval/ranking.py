import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.domain.vector import VectorSearchResult

RRF_K = 60
VECTOR_WEIGHT = 1.0
GRAPH_WEIGHT = 0.7
MAX_EXACT_BOOST = 0.006


@dataclass(frozen=True)
class RankedCandidate:
    result: VectorSearchResult
    vector_rank: int
    graph_rank: int | None
    graph_relationships: tuple[str, ...]
    graph_contribution: float
    exact_boost: float
    final_score: float
    reasons: tuple[str, ...]


def reciprocal_rank(rank: int, *, weight: float = 1.0, constant: int = RRF_K) -> float:
    if rank < 1:
        raise ValueError("rank must be positive")
    return weight / (constant + rank)


def rank_candidates(
    query: str,
    vector_results: list[VectorSearchResult],
    graph_relationships: dict[str, set[str]],
) -> list[RankedCandidate]:
    graph_order = sorted(
        (
            (result.symbol_id, len(graph_relationships.get(result.symbol_id or "", set())), rank)
            for rank, result in enumerate(vector_results, start=1)
            if result.symbol_id and graph_relationships.get(result.symbol_id)
        ),
        key=lambda item: (-item[1], item[2], item[0]),
    )
    graph_ranks = {symbol_id: rank for rank, (symbol_id, _, _) in enumerate(graph_order, 1)}
    ranked: list[RankedCandidate] = []
    for vector_rank, result in enumerate(vector_results, start=1):
        graph_rank = graph_ranks.get(result.symbol_id or "")
        relationships = tuple(sorted(graph_relationships.get(result.symbol_id or "", set())))
        graph_contribution = (
            reciprocal_rank(graph_rank, weight=GRAPH_WEIGHT) if graph_rank is not None else 0.0
        )
        boost, exact_reasons = exact_match_boost(query, result)
        reasons = [f"vector_rank:{vector_rank}"]
        if relationships:
            reasons.append(f"graph_relationships:{','.join(relationships)}")
        reasons.extend(exact_reasons)
        ranked.append(
            RankedCandidate(
                result=result,
                vector_rank=vector_rank,
                graph_rank=graph_rank,
                graph_relationships=relationships,
                graph_contribution=graph_contribution,
                exact_boost=boost,
                final_score=(
                    reciprocal_rank(vector_rank, weight=VECTOR_WEIGHT) + graph_contribution + boost
                ),
                reasons=tuple(reasons),
            )
        )
    return sorted(
        ranked,
        key=lambda item: (-item.final_score, item.vector_rank, item.result.chunk_id),
    )


def exact_match_boost(query: str, result: VectorSearchResult) -> tuple[float, list[str]]:
    matches: list[tuple[float, str]] = []
    if _contains_exact(query, result.file_path):
        matches.append((0.006, "exact_file_path"))
    filename = PurePosixPath(result.file_path).name
    if filename != result.file_path and _contains_exact(query, filename):
        matches.append((0.003, "exact_filename"))
    if result.qualified_name and _contains_exact(query, result.qualified_name):
        matches.append((0.005, "exact_qualified_name"))
    if result.symbol_name and _contains_exact(query, result.symbol_name):
        matches.append((0.004, "exact_symbol_name"))
    if not matches:
        return 0.0, []
    return min(MAX_EXACT_BOOST, max(value for value, _ in matches)), [
        reason for _, reason in matches
    ]


def deduplicate_candidates(
    candidates: Iterable[RankedCandidate],
) -> tuple[list[RankedCandidate], int]:
    selected: list[RankedCandidate] = []
    duplicate_count = 0
    for candidate in candidates:
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(selected)
                if _same_structural_region(candidate.result, existing.result)
            ),
            None,
        )
        if duplicate_index is None:
            selected.append(candidate)
            continue
        duplicate_count += 1
        existing = selected[duplicate_index]
        combined_reasons = tuple(
            dict.fromkeys(
                (
                    *existing.reasons,
                    *candidate.reasons,
                    f"deduplicated_chunk:{candidate.result.chunk_id}",
                )
            )
        )
        selected[duplicate_index] = RankedCandidate(
            result=existing.result,
            vector_rank=existing.vector_rank,
            graph_rank=existing.graph_rank,
            graph_relationships=tuple(
                sorted(set(existing.graph_relationships) | set(candidate.graph_relationships))
            ),
            graph_contribution=max(existing.graph_contribution, candidate.graph_contribution),
            exact_boost=max(existing.exact_boost, candidate.exact_boost),
            final_score=max(existing.final_score, candidate.final_score),
            reasons=combined_reasons,
        )
    return selected, duplicate_count


def _contains_exact(query: str, value: str) -> bool:
    if not value:
        return False
    pattern = rf"(?<![\w./-]){re.escape(value)}(?![\w./-])"
    return re.search(pattern, query, flags=re.IGNORECASE) is not None


def _same_structural_region(left: VectorSearchResult, right: VectorSearchResult) -> bool:
    if left.file_path != right.file_path:
        return False
    same_identity = (
        left.symbol_id is not None
        and right.symbol_id is not None
        and left.symbol_id == right.symbol_id
    )
    same_span = left.start_line == right.start_line and left.end_line == right.end_line
    overlaps = left.start_line <= right.end_line and right.start_line <= left.end_line
    return same_span or (same_identity and overlaps)
