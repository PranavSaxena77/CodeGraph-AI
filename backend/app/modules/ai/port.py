from typing import Protocol

from app.domain.qa import ReasoningRequest


class ReasoningProvider(Protocol):
    """Generate an untrusted structured answer from server-selected evidence."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def generate(self, request: ReasoningRequest) -> str: ...
