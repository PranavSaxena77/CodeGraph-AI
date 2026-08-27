from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.domain.operations import PipelineOperation
from app.modules.operations.store import InMemoryOperationStore

router = APIRouter(prefix="/operations", tags=["operations"])


def get_operation_store(request: Request) -> InMemoryOperationStore:
    """Resolve the single operation registry owned by this FastAPI application."""
    return cast(InMemoryOperationStore, request.app.state.operation_store)


OperationStore = Annotated[InMemoryOperationStore, Depends(get_operation_store)]


@router.get("/{operation_id}", response_model=PipelineOperation)
def get_operation(operation_id: str, store: OperationStore) -> PipelineOperation:
    operation = store.get(operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="Pipeline operation was not found")
    return operation
