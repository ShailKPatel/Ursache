from __future__ import annotations

import base64
import logging

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from ursache.config import Settings

logger = logging.getLogger(__name__)


def configure_tracing(settings: Settings, app: FastAPI | None = None) -> TracerProvider | None:
    """Export spans to Langfuse over OTLP/HTTP. No-op when Langfuse keys are unset."""
    if settings.langfuse_public_key is None or settings.langfuse_secret_key is None:
        logger.info("tracing disabled: Langfuse keys not set")
        return None

    credentials = (
        f"{settings.langfuse_public_key.get_secret_value()}:"
        f"{settings.langfuse_secret_key.get_secret_value()}"
    )
    exporter = OTLPSpanExporter(
        endpoint=settings.langfuse_otlp_endpoint,
        headers={
            "Authorization": f"Basic {base64.b64encode(credentials.encode()).decode()}",
            "x-langfuse-ingestion-version": "4",
        },
    )
    provider = TracerProvider(
        resource=Resource.create(
            {
                SERVICE_NAME: settings.otel_service_name,
                "deployment.environment": settings.environment,
            }
        )
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    if app is not None:
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls="health")
    logger.info("tracing enabled", extra={"endpoint": settings.langfuse_otlp_endpoint})
    return provider
