from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

resource = Resource.create(
    {
        "service.name": "orders-api",
        "service.version": "1.0.0",
        "deployment.environment": "development",
    }
)

provider = TracerProvider(resource=resource)

import os

otlp_endpoint = os.environ.get("OTEL_COLLECTOR_ENDPOINT", "http://localhost:4317")

processor = BatchSpanProcessor(
    OTLPSpanExporter(
        endpoint=otlp_endpoint,
        insecure=True,
    )
)

provider.add_span_processor(processor)

trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

import logging
from logging.handlers import RotatingFileHandler
from opentelemetry.instrumentation.logging import LoggingInstrumentor

# Initialize Logging Instrumentation to inject trace/span IDs into log records
os.environ["OTEL_PYTHON_LOG_CORRELATION"] = "true"
LoggingInstrumentor().instrument(set_logging_format=False)

# Custom logging filter to guarantee otelTraceID and otelSpanID are always present in the record
class OpenTelemetryFilter(logging.Filter):
    def filter(self, record):
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            record.otelTraceID = trace.format_trace_id(span.get_span_context().trace_id)
            record.otelSpanID = trace.format_span_id(span.get_span_context().span_id)
        else:
            record.otelTraceID = "00000000000000000000000000000000"
            record.otelSpanID = "0000000000000000"
        return True

# Configure logs directory and formatting
os.makedirs("/app/logs", exist_ok=True)
log_format = "%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] - %(message)s"

# Setup root logger handlers: Rotating File and Console Stream
file_handler = RotatingFileHandler(
    "/app/logs/app.log", maxBytes=10*1024*1024, backupCount=5
)
file_handler.addFilter(OpenTelemetryFilter())
file_handler.setFormatter(logging.Formatter(log_format))

console_handler = logging.StreamHandler()
console_handler.addFilter(OpenTelemetryFilter())
console_handler.setFormatter(logging.Formatter(log_format))

logger = logging.getLogger("orders-api")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)