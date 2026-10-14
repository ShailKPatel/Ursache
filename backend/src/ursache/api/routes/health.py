from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from ursache.api.health import HealthReport, HealthService

router = APIRouter(tags=["ops"])


def get_health_service(request: Request) -> HealthService:
    service: HealthService = request.app.state.health_service
    return service


@router.get("/health", response_model=HealthReport)
async def health(
    response: Response,
    service: Annotated[HealthService, Depends(get_health_service)],
) -> HealthReport:
    report = await service.check()
    if report.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report
