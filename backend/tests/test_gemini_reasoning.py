from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.core.errors import ReasoningProviderError
from app.domain.qa import ReasoningEvidence, ReasoningRequest
from app.modules.ai.gemini import GeminiReasoningProvider


class StubResponse:
    def __init__(self, payload: object, *, raises: bool = False) -> None:
        self.payload = payload
        self.raises = raises

    def raise_for_status(self) -> None:
        if self.raises:
            raise httpx.HTTPStatusError(
                "failed",
                request=httpx.Request("POST", "https://example.test"),
                response=httpx.Response(503),
            )

    def json(self) -> object:
        return self.payload


def request() -> ReasoningRequest:
    return ReasoningRequest(
        repository_id="repository-1",
        snapshot_id="snapshot-1",
        question="How does authentication work?",
        evidence=[
            ReasoningEvidence(
                evidence_id="E1",
                chunk_id="chunk-1",
                file_path="auth.py",
                symbol_name="authenticate",
                qualified_name="auth.authenticate",
                symbol_type="function",
                start_line=1,
                end_line=2,
                content="def authenticate(): pass",
            )
        ],
    )


def provider() -> GeminiReasoningProvider:
    return GeminiReasoningProvider(
        api_key=SecretStr("secret-key"),
        model_name="gemini-2.5-flash",
        api_base_url="https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds=10,
        max_output_tokens=512,
    )


def test_gemini_provider_sends_only_grounded_request_and_returns_raw_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> StubResponse:
        captured.update({"url": url, **kwargs})
        return StubResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": ('{"answer":"Grounded","cited_evidence_ids":["E1"]}')}
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    raw = provider().generate(request())

    assert raw == '{"answer":"Grounded","cited_evidence_ids":["E1"]}'
    assert captured["url"].endswith("/models/gemini-2.5-flash:generateContent")
    payload = captured["json"]
    prompt = payload["contents"][0]["parts"][0]["text"]
    assert "chunk-1" in prompt
    assert "def authenticate(): pass" in prompt
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseJsonSchema" in payload["generationConfig"]


@pytest.mark.parametrize(
    "response",
    [StubResponse({"candidates": []}), StubResponse({}, raises=True)],
)
def test_gemini_provider_translates_malformed_or_failed_responses(
    monkeypatch: pytest.MonkeyPatch, response: StubResponse
) -> None:
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response)

    with pytest.raises(ReasoningProviderError, match="request failed"):
        provider().generate(request())
