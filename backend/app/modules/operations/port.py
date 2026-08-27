from typing import Protocol

from app.domain.operations import PipelineStage


class OperationReporter(Protocol):
    def start_stage(self, stage: PipelineStage) -> None: ...

    def start_event(self, stage: PipelineStage, message: str) -> str: ...

    def complete_event(
        self,
        event_id: str,
        *,
        metric_key: str | None = None,
        metric_label: str | None = None,
        metric_value: int | None = None,
    ) -> None: ...

    def complete_stage(self, stage: PipelineStage, metrics: dict[str, tuple[str, int]]) -> None: ...

    def fail_stage(self, stage: PipelineStage) -> None: ...


class NullOperationReporter:
    def start_stage(self, stage: PipelineStage) -> None:
        del stage

    def start_event(self, stage: PipelineStage, message: str) -> str:
        del stage, message
        return ""

    def complete_event(
        self,
        event_id: str,
        *,
        metric_key: str | None = None,
        metric_label: str | None = None,
        metric_value: int | None = None,
    ) -> None:
        del event_id, metric_key, metric_label, metric_value

    def complete_stage(self, stage: PipelineStage, metrics: dict[str, tuple[str, int]]) -> None:
        del stage, metrics

    def fail_stage(self, stage: PipelineStage) -> None:
        del stage


NULL_OPERATION_REPORTER = NullOperationReporter()
