from typing import Literal

from pydantic import BaseModel, Field, field_validator

ChunkSymbolType = Literal["file", "class", "function", "method"]


class CodeChunk(BaseModel):
    id: str
    repository_id: str
    snapshot_id: str
    commit_sha: str
    file_path: str
    symbol_id: str | None = None
    symbol_name: str
    qualified_name: str
    symbol_type: ChunkSymbolType
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str
    part_index: int = Field(default=0, ge=0)
    chunking_version: str


class VectorIndexSpec(BaseModel):
    repository_id: str
    snapshot_id: str
    commit_sha: str
    embedding_provider: str
    embedding_model: str
    vector_dimension: int = Field(ge=1)
    chunking_version: str
    index_version: str


class VectorIndexManifest(VectorIndexSpec):
    index_id: str
    chunk_count: int = Field(ge=0)
    index_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class VectorIndexStatus(BaseModel):
    repository_id: str
    snapshot_id: str
    status: Literal["ready"] = "ready"
    index_id: str
    chunk_count: int = Field(ge=0)
    vector_dimension: int = Field(ge=1)
    embedding_provider: str
    embedding_model: str
    chunking_version: str
    index_version: str
    idempotent: bool = False


class VectorSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("query cannot be blank")
        return normalized


class VectorSearchResult(BaseModel):
    score: float
    chunk_id: str
    file_path: str
    symbol_id: str | None = None
    symbol_name: str
    qualified_name: str
    symbol_type: ChunkSymbolType
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str


class VectorSearchResponse(BaseModel):
    repository_id: str
    snapshot_id: str
    query: str
    results: list[VectorSearchResult] = Field(default_factory=list)
