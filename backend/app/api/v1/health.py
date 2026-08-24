from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.domain.health import DependencyHealth, HealthResponse, ReadinessResponse
from app.services.readiness import ReadinessChecker, SocketReadinessChecker

router = APIRouter(tags=["system"])


def get_readiness_checker(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadinessChecker:
    """Build the default dependency checker at the API boundary."""
    return SocketReadinessChecker.from_settings(settings)


@router.get("/health", response_model=HealthResponse)
async def get_health(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    """Report process health without contacting external services."""
    return HealthResponse(
        status="healthy",
        application=settings.app_name,
        version=settings.app_version,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def get_readiness(
    checker: Annotated[ReadinessChecker, Depends(get_readiness_checker)],
) -> ReadinessResponse | JSONResponse:
    """Report whether the application's required data services are reachable."""
    checks = await checker.check()
    dependencies = {
        name: DependencyHealth(status="ready" if available else "unavailable")
        for name, available in checks.items()
    }
    is_ready = all(checks.values())
    response = ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        dependencies=dependencies,
    )
    if not is_ready:
        return JSONResponse(status_code=503, content=response.model_dump(mode="json"))
    return response
