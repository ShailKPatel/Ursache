from fastapi.testclient import TestClient

from ursache.api.health import DependencyStatus, HealthReport
from ursache.api.main import create_app
from ursache.api.routes.health import get_health_service
from ursache.config import Settings


class StubHealthService:
    def __init__(self, report: HealthReport) -> None:
        self.report = report

    async def check(self) -> HealthReport:
        return self.report


def report(*, postgres: bool, qdrant: bool) -> HealthReport:
    return HealthReport(
        status="ok" if postgres and qdrant else "degraded",
        postgres=DependencyStatus(ok=postgres, latency_ms=1.0),
        qdrant=DependencyStatus(ok=qdrant, latency_ms=1.0),
        quota_remaining={"gemini/flash": 3} if postgres else None,
    )


def client_with(stub: StubHealthService) -> TestClient:
    app = create_app(Settings(_env_file=None))  # type: ignore[call-arg]
    app.dependency_overrides[get_health_service] = lambda: stub
    return TestClient(app)


def test_health_ok_returns_200() -> None:
    with client_with(StubHealthService(report(postgres=True, qdrant=True))) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["quota_remaining"] == {"gemini/flash": 3}


def test_health_degraded_returns_503() -> None:
    with client_with(StubHealthService(report(postgres=True, qdrant=False))) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_cors_allows_configured_origin() -> None:
    with client_with(StubHealthService(report(postgres=True, qdrant=True))) as client:
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
