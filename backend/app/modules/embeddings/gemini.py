import re

import httpx
from pydantic import BaseModel, SecretStr, ValidationError

from app.core.errors import EmbeddingProviderError

MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class _EmbeddingPayload(BaseModel):
    values: list[float]


class _BatchEmbeddingResponse(BaseModel):
    embeddings: list[_EmbeddingPayload]


class _EmbeddingResponse(BaseModel):
    embedding: _EmbeddingPayload


class GeminiEmbeddingProvider:
    """Gemini REST embedding adapter configured only through runtime settings."""

    def __init__(
        self,
        api_key: SecretStr,
        model_name: str,
        dimension: int,
        api_base_url: str,
        timeout_seconds: float,
        batch_size: int,
    ) -> None:
        normalized_model = model_name.removeprefix("models/")
        if not MODEL_PATTERN.fullmatch(normalized_model):
            raise EmbeddingProviderError("Gemini embedding model name is invalid")
        if dimension < 1 or batch_size < 1:
            raise EmbeddingProviderError("Gemini embedding configuration is invalid")
        self._api_key = api_key
        self._model_name = normalized_model
        self._dimension = dimension
        self._api_base_url = api_base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._batch_size = batch_size

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            embeddings.extend(self._embed_batch(texts[start : start + self._batch_size]))
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        payload = {
            "content": {"parts": [{"text": text}]},
            "taskType": "CODE_RETRIEVAL_QUERY",
            "outputDimensionality": self._dimension,
        }
        raw_response = self._post(f"models/{self._model_name}:embedContent", payload)
        try:
            response = _EmbeddingResponse.model_validate(raw_response)
        except ValidationError as error:
            raise EmbeddingProviderError("Gemini returned malformed embedding data") from error
        return self._validate_vector(response.embedding.values)

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        model_resource = f"models/{self._model_name}"
        requests = [
            {
                "model": model_resource,
                "content": {"parts": [{"text": text}]},
                "taskType": "RETRIEVAL_DOCUMENT",
                "outputDimensionality": self._dimension,
            }
            for text in texts
        ]
        raw_response = self._post(
            f"{model_resource}:batchEmbedContents",
            {"requests": requests},
        )
        try:
            response = _BatchEmbeddingResponse.model_validate(raw_response)
        except ValidationError as error:
            raise EmbeddingProviderError("Gemini returned malformed embedding data") from error
        if len(response.embeddings) != len(texts):
            raise EmbeddingProviderError("Gemini returned an unexpected embedding count")
        return [self._validate_vector(item.values) for item in response.embeddings]

    def _post(self, path: str, payload: dict[str, object]) -> object:
        try:
            response = httpx.post(
                f"{self._api_base_url}/{path}",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self._api_key.get_secret_value(),
                },
                json=payload,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise EmbeddingProviderError("Gemini embedding request failed") from error

    def _validate_vector(self, vector: list[float]) -> list[float]:
        if len(vector) != self._dimension:
            raise EmbeddingProviderError("Gemini returned an unexpected embedding dimension")
        return vector
