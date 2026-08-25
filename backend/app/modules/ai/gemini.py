import re

import httpx
from pydantic import BaseModel, Field, SecretStr, ValidationError

from app.core.errors import ReasoningProviderError
from app.domain.qa import ReasoningOutput, ReasoningRequest
from app.modules.ai.prompt import SYSTEM_INSTRUCTION, build_grounded_prompt

MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class _GeminiPart(BaseModel):
    text: str


class _GeminiContent(BaseModel):
    parts: list[_GeminiPart] = Field(min_length=1)


class _GeminiCandidate(BaseModel):
    content: _GeminiContent


class _GeminiResponse(BaseModel):
    candidates: list[_GeminiCandidate] = Field(min_length=1)


class GeminiReasoningProvider:
    """Gemini REST adapter that returns raw structured text for application validation."""

    def __init__(
        self,
        api_key: SecretStr,
        model_name: str,
        api_base_url: str,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> None:
        normalized_model = model_name.removeprefix("models/")
        if not MODEL_PATTERN.fullmatch(normalized_model):
            raise ReasoningProviderError("Gemini reasoning model name is invalid")
        if not api_key.get_secret_value():
            raise ReasoningProviderError("Gemini API key is missing")
        if timeout_seconds <= 0 or max_output_tokens < 1:
            raise ReasoningProviderError("Gemini reasoning configuration is invalid")
        self._api_key = api_key
        self._model_name = normalized_model
        self._api_base_url = api_base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model_name

    def generate(self, request: ReasoningRequest) -> str:
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": build_grounded_prompt(request)}],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": self._max_output_tokens,
                "responseMimeType": "application/json",
                "responseJsonSchema": ReasoningOutput.model_json_schema(),
            },
        }
        try:
            response = httpx.post(
                f"{self._api_base_url}/models/{self._model_name}:generateContent",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self._api_key.get_secret_value(),
                },
                json=payload,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            envelope = _GeminiResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as error:
            raise ReasoningProviderError("Gemini reasoning request failed") from error
        return "".join(part.text for part in envelope.candidates[0].content.parts)
