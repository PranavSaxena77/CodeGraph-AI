from app.core.errors import ReasoningProviderError
from app.domain.qa import ReasoningOutput, ReasoningRequest


class DeterministicReasoningProvider:
    """Configurable deterministic reasoning adapter for unit and API tests."""

    def __init__(
        self,
        raw_response: str | None = None,
        failure_message: str | None = None,
    ) -> None:
        self._raw_response = raw_response
        self._failure_message = failure_message
        self.requests: list[ReasoningRequest] = []

    @property
    def provider_name(self) -> str:
        return "deterministic-fake"

    @property
    def model_name(self) -> str:
        return "grounded-answer-v1"

    def generate(self, request: ReasoningRequest) -> str:
        self.requests.append(request.model_copy(deep=True))
        if self._failure_message is not None:
            raise ReasoningProviderError(self._failure_message)
        if self._raw_response is not None:
            return self._raw_response
        first = request.evidence[0]
        return ReasoningOutput(
            answer=f"The selected evidence is in {first.file_path}.",
            cited_evidence_ids=[first.evidence_id],
        ).model_dump_json()


class UnavailableReasoningProvider:
    """Defer missing runtime credential errors until reasoning is actually needed."""

    @property
    def provider_name(self) -> str:
        return "unavailable"

    @property
    def model_name(self) -> str:
        return "unconfigured"

    def generate(self, request: ReasoningRequest) -> str:
        del request
        raise ReasoningProviderError("GEMINI_API_KEY is required")
