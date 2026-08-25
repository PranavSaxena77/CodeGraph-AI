from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.retrieval import HybridRetrievalMetadata
from app.domain.vector import ChunkSymbolType


class RepositoryQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("question cannot be blank")
        return normalized


class ReasoningEvidence(BaseModel):
    evidence_id: str
    chunk_id: str
    file_path: str
    symbol_name: str
    qualified_name: str
    symbol_type: ChunkSymbolType
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str


class ReasoningRequest(BaseModel):
    repository_id: str
    snapshot_id: str
    question: str
    evidence: list[ReasoningEvidence] = Field(min_length=1)


class ReasoningOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=20_000)
    cited_evidence_ids: list[str] = Field(min_length=1, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("answer")
    @classmethod
    def strip_answer(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("answer cannot be blank")
        return stripped

    @field_validator("cited_evidence_ids")
    @classmethod
    def validate_unique_citations(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("cited evidence IDs must be unique")
        return value


class AnswerEvidence(BaseModel):
    evidence_id: str
    chunk_id: str
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


class RepositoryAnswerResponse(BaseModel):
    repository_id: str
    snapshot_id: str
    commit_sha: str
    question: str
    outcome: Literal["answered", "insufficient_evidence"]
    answer: str
    cited_evidence_ids: list[str] = Field(default_factory=list)
    evidence: list[AnswerEvidence] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    retrieval_metadata: HybridRetrievalMetadata
