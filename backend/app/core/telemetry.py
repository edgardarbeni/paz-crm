"""OpenTelemetry traces and metrics. Exporting is enabled only when an OTLP endpoint is
configured; otherwise spans are still created (for log correlation) but not exported."""

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings

_configured = False


def configure_telemetry(app: FastAPI, engine: AsyncEngine, settings: Settings) -> None:
    global _configured  # noqa: PLW0603 - providers are process-wide singletons
    if not _configured:
        resource = Resource.create(
            {"service.name": settings.service_name, "deployment.environment": settings.environment}
        )
        tracer_provider = TracerProvider(resource=resource)
        readers = []
        if settings.otel_exporter_otlp_endpoint:
            endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/")
            tracer_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
            )
            readers.append(
                PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"))
            )
        trace.set_tracer_provider(tracer_provider)
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=readers))
        RedisInstrumentor().instrument()
        _configured = True

    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready")
