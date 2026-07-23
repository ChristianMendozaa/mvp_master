import os

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import AsyncEngine


def configure_observability(app: FastAPI, engine: AsyncEngine, *, service_name: str) -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    resource = Resource.create(
        {
            "service.name": service_name,
            "deployment.environment": os.getenv("ENVIRONMENT", "development"),
        }
    )
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True)
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        excluded_urls="health/live,health/ready",
    )
    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine,
        tracer_provider=tracer_provider,
    )
