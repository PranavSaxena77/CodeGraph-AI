from collections import OrderedDict
from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from app.domain.operations import (
    OperationEvent,
    OperationMetric,
    PipelineOperation,
    PipelineStage,
)

_STAGES: tuple[PipelineStage, ...] = ("ingestion", "analysis", "graph", "vector")


class InMemoryOperationStore:
    """Bounded, thread-safe operation state for the single-process v1 backend."""

    def __init__(self, max_operations: int = 200) -> None:
        self._max_operations = max_operations
        self._operations: OrderedDict[str, PipelineOperation] = OrderedDict()
        self._lock = RLock()

    def reporter(self, operation_id: str) -> "BoundOperationReporter":
        with self._lock:
            if operation_id not in self._operations:
                now = datetime.now(UTC)
                self._operations[operation_id] = PipelineOperation(
                    operation_id=operation_id,
                    status="running",
                    stages={stage: "pending" for stage in _STAGES},
                    created_at=now,
                    updated_at=now,
                )
                while len(self._operations) > self._max_operations:
                    self._operations.popitem(last=False)
            else:
                self._operations.move_to_end(operation_id)
        return BoundOperationReporter(self, operation_id)

    def get(self, operation_id: str) -> PipelineOperation | None:
        with self._lock:
            operation = self._operations.get(operation_id)
            return deepcopy(operation) if operation is not None else None

    def _mutate(self, operation_id: str, mutation: object) -> None:
        with self._lock:
            operation = self._operations[operation_id]
            mutation(operation)  # type: ignore[operator]
            operation.updated_at = datetime.now(UTC)


class BoundOperationReporter:
    def __init__(self, store: InMemoryOperationStore, operation_id: str) -> None:
        self._store = store
        self._operation_id = operation_id

    def start_stage(self, stage: PipelineStage) -> None:
        def mutation(operation: PipelineOperation) -> None:
            operation.status = "running"
            operation.stages[stage] = "running"

        self._store._mutate(self._operation_id, mutation)

    def start_event(self, stage: PipelineStage, message: str) -> str:
        event_id = uuid4().hex

        def mutation(operation: PipelineOperation) -> None:
            operation.events.append(
                OperationEvent(
                    id=event_id,
                    sequence=len(operation.events) + 1,
                    stage=stage,
                    status="running",
                    message=message,
                    started_at=datetime.now(UTC),
                )
            )

        self._store._mutate(self._operation_id, mutation)
        return event_id

    def complete_event(
        self,
        event_id: str,
        *,
        metric_key: str | None = None,
        metric_label: str | None = None,
        metric_value: int | None = None,
    ) -> None:
        def mutation(operation: PipelineOperation) -> None:
            event = next(item for item in operation.events if item.id == event_id)
            event.status = "done"
            event.completed_at = datetime.now(UTC)
            if metric_key is not None and metric_label is not None and metric_value is not None:
                event.metric = OperationMetric(
                    key=metric_key,
                    label=metric_label,
                    value=metric_value,
                )

        self._store._mutate(self._operation_id, mutation)

    def complete_stage(self, stage: PipelineStage, metrics: dict[str, tuple[str, int]]) -> None:
        def mutation(operation: PipelineOperation) -> None:
            operation.stages[stage] = "complete"
            operation.metrics[stage] = [
                OperationMetric(key=key, label=label, value=value)
                for key, (label, value) in metrics.items()
            ]
            if stage == "vector":
                operation.status = "complete"

        self._store._mutate(self._operation_id, mutation)

    def fail_stage(self, stage: PipelineStage) -> None:
        def mutation(operation: PipelineOperation) -> None:
            operation.status = "failed"
            operation.stages[stage] = "failed"
            for event in reversed(operation.events):
                if event.stage == stage and event.status == "running":
                    event.status = "failed"
                    event.completed_at = datetime.now(UTC)
                    break

        self._store._mutate(self._operation_id, mutation)
