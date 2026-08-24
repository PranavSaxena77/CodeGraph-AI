from typing import Protocol

from app.domain.vector import (
    CodeChunk,
    VectorIndexSpec,
    VectorIndexStatus,
    VectorSearchResponse,
)


class VectorIndex(Protocol):
    def get_status(self, spec: VectorIndexSpec) -> VectorIndexStatus | None: ...

    def build_index(
        self,
        spec: VectorIndexSpec,
        chunks: list[CodeChunk],
        vectors: list[list[float]],
    ) -> VectorIndexStatus: ...

    def search(
        self,
        spec: VectorIndexSpec,
        query: str,
        query_vector: list[float],
        top_k: int,
    ) -> VectorSearchResponse: ...
