from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PipelineStage = Literal["ingestion", "analysis", "graph", "vector"]
PipelineStageStatus = Literal["pending", "running", "complete", "failed"]
OperationStatus = Literal["running", "complete", "failed"]
OperationEventStatus = Literal["running", "done", "failed"]


class OperationMetric(BaseModel):
    key: str
    label: str
    value: int = Field(ge=0)


class OperationEvent(BaseModel):
    id: str
    sequence: int = Field(ge=1)
    stage: PipelineStage
    status: OperationEventStatus
    message: str
    started_at: datetime
    completed_at: datetime | None = None
    metric: OperationMetric | None = None


class PipelineOperation(BaseModel):
    operation_id: str
    status: OperationStatus
    stages: dict[PipelineStage, PipelineStageStatus]
    events: list[OperationEvent] = Field(default_factory=list)
    metrics: dict[PipelineStage, list[OperationMetric]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
