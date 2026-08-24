import hashlib
import math
import re

TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")


class DeterministicEmbeddingProvider:
    """Dependency-free hashed-token embeddings for deterministic tests and local development."""

    def __init__(self, dimension: int = 128) -> None:
        if dimension < 1:
            raise ValueError("dimension must be positive")
        self._dimension = dimension

    @property
    def provider_name(self) -> str:
        return "deterministic-local"

    @property
    def model_name(self) -> str:
        return "hashed-token-v1"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        for token in TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], "big") % self._dimension
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            return [value / norm for value in vector]
        return vector
