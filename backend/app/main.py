from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.modules.operations.store import InMemoryOperationStore


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the FastAPI application with its HTTP-layer dependencies."""
    active_settings = settings or get_settings()
    application = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
    )
    application.state.operation_store = InMemoryOperationStore()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CodeGraph-Operation-ID"],
    )
    application.include_router(api_router, prefix="/api/v1")
    return application


app = create_app()
