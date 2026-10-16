from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from .config import settings

log = logging.getLogger(__name__)
_backend: str | None = None


def init_telemetry(service_name: str, console: bool = False) -> str:
    """Configure tracing once. Returns backend: 'a365', 'azure-monitor', 'otlp', 'console' or 'none'."""
    global _backend
    if _backend is not None:
        return _backend
    cfg = settings()

    if not cfg.is_mock:
        try:
            # Agent 365 observability SDK (preview); API surface may change between releases.
            from microsoft_agents_a365.observability.core import configure  # type: ignore

            configure(service_name=service_name, service_namespace="fsi-kyc")
            _backend = "a365"
            return _backend
        except Exception as exc:
            log.info("Agent 365 observability not available (%s); falling back", exc)
        if cfg.appinsights_connection_string:
            try:
                from azure.monitor.opentelemetry import configure_azure_monitor  # type: ignore

                configure_azure_monitor(connection_string=cfg.appinsights_connection_string)
                _backend = "azure-monitor"
                return _backend
            except Exception as exc:
                log.info("azure-monitor-opentelemetry not available (%s)", exc)

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    backend = "none"
    if cfg.otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # type: ignore

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=cfg.otlp_endpoint)))
            backend = "otlp"
        except Exception as exc:
            log.info("OTLP exporter not available (%s)", exc)
    if console:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        backend = "console" if backend == "none" else backend
    trace.set_tracer_provider(provider)
    _backend = backend
    return backend


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[trace.Span]:
    tracer = trace.get_tracer("fsi-kyc")
    with tracer.start_as_current_span(name) as s:
        for k, v in attrs.items():
            if v is not None:
                s.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else str(v))
        yield s


def current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None
