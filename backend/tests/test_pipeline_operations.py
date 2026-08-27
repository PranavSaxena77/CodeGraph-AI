from fastapi import Request

from app.api.v1.operations import get_operation_store
from app.main import create_app
from app.modules.operations.store import InMemoryOperationStore


def test_operation_store_isolates_operations_and_failure_state() -> None:
    store = InMemoryOperationStore()
    failed = store.reporter("failed-operation")
    healthy = store.reporter("healthy-operation")

    failed.start_stage("graph")
    event_id = failed.start_event("graph", "Persisting graph data")
    failed.fail_stage("graph")
    healthy.start_stage("analysis")
    healthy_event = healthy.start_event("analysis", "Parsing Python ASTs")
    healthy.complete_event(
        healthy_event,
        metric_key="symbols",
        metric_label="Symbols",
        metric_value=7,
    )
    healthy.complete_stage("analysis", {"symbols": ("Symbols", 7)})

    failed_state = store.get("failed-operation")
    healthy_state = store.get("healthy-operation")
    assert failed_state is not None
    assert healthy_state is not None
    assert failed_state.status == "failed"
    assert failed_state.stages["graph"] == "failed"
    assert failed_state.stages["vector"] == "pending"
    assert failed_state.events[0].id == event_id
    assert failed_state.events[0].status == "failed"
    assert healthy_state.status == "running"
    assert healthy_state.stages["analysis"] == "complete"
    assert healthy_state.metrics["analysis"][0].value == 7
    assert {event.message for event in failed_state.events} == {"Persisting graph data"}
    assert {event.message for event in healthy_state.events} == {"Parsing Python ASTs"}


def test_operation_store_returns_defensive_snapshots() -> None:
    store = InMemoryOperationStore()
    reporter = store.reporter("operation")
    reporter.start_stage("ingestion")

    snapshot = store.get("operation")
    assert snapshot is not None
    snapshot.stages["ingestion"] = "failed"

    persisted = store.get("operation")
    assert persisted is not None
    assert persisted.stages["ingestion"] == "running"


def test_operation_store_dependency_is_application_scoped() -> None:
    application = create_app()
    request = Request({"type": "http", "app": application})

    first_resolution = get_operation_store(request)
    second_resolution = get_operation_store(request)

    assert first_resolution is second_resolution
    assert first_resolution is application.state.operation_store
