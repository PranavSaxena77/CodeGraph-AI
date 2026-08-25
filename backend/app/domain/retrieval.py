from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.vector import ChunkSymbolType


class HybridSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=8, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("query cannot be blank")
        return normalized


class HybridEvidence(BaseModel):
    chunk_id: str
    file_path: str
    symbol_id: str | None = None
    symbol_name: str
    qualified_name: str
    symbol_type: ChunkSymbolType
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str
    vector_score: float
    graph_contribution: float = Field(ge=0)
    final_hybrid_score: float
    retrieval_reasons: list[str] = Field(default_factory=list)


class HybridRetrievalMetadata(BaseModel):
    outcome: Literal["sufficient", "insufficient"]
    vector_candidate_count: int = Field(ge=0)
    graph_enriched_count: int = Field(ge=0)
    deduplicated_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    source_characters: int = Field(ge=0)
    candidate_multiplier: int = Field(ge=1)
    graph_max_depth: int = Field(ge=1)
    graph_max_neighbors_per_symbol: int = Field(ge=1)
    fusion_strategy: str


class HybridSearchResponse(BaseModel):
    repository_id: str
    snapshot_id: str
    query: str
    evidence: list[HybridEvidence] = Field(default_factory=list)
    metadata: HybridRetrievalMetadata
