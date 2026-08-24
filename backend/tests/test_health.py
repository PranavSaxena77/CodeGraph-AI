from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.v1.health import get_readiness_checker
from app.main import app


class StubReadinessChecker:
    def __init__(self, checks: dict[str, bool]) -> None:
        self._checks = checks

    async def check(self) -> dict[str, bool]:
        return self._checks


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_reports_application_status(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "application": "CodeGraph AI",
        "version": "0.1.0",
    }


def test_readiness_reports_ready_without_live_services(client: TestClient) -> None:
    app.dependency_overrides[get_readiness_checker] = lambda: StubReadinessChecker(
        {"mongodb": True, "neo4j": True}
    )

    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {
            "mongodb": {"status": "ready"},
            "neo4j": {"status": "ready"},
        },
    }


def test_readiness_returns_503_for_unavailable_dependency(client: TestClient) -> None:
    app.dependency_overrides[get_readiness_checker] = lambda: StubReadinessChecker(
        {"mongodb": True, "neo4j": False}
    )

    response = client.get("/api/v1/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {
            "mongodb": {"status": "ready"},
            "neo4j": {"status": "unavailable"},
        },
    }
