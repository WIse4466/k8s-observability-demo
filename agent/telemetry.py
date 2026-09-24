"""把 agent 自己接進前面二十五天蓋的觀測系統（Day 26）。

屬性與指標名稱照 OpenTelemetry 的 GenAI 語意慣例。
⚠️ 那份規格 2026-09 查的時候整份還在 Development 階段，名稱會變——
   例如原本的 gen_ai.system 已經改叫 gen_ai.provider.name。

送去哪裡：OTLP gRPC → 叢集裡的 otel-collector（跟其他三個服務同一條路）。
"""
import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
SERVICE = "alert-agent"

# 規格建議的桶。跟 HTTP 請求那組（0.005~10 秒）差很多——
# 模型呼叫動輒好幾秒，用預設桶會全部擠進最後一個。
DURATION_BUCKETS = [
    0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28,
    2.56, 5.12, 10.24, 20.48, 40.96, 81.92,
]

# 這個值不是隨便取的。規格寫明：用 generativelanguage.googleapis.com
# 端點（也就是 AI Studio 的 API）時填 gcp.gemini，走 Vertex 才是 gcp.vertex_ai。
PROVIDER = "gcp.gemini"

_resource = Resource.create({"service.name": SERVICE})

_tracer_provider = TracerProvider(resource=_resource)
_tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=ENDPOINT, insecure=True)))
trace.set_tracer_provider(_tracer_provider)

_meter_provider = MeterProvider(
    resource=_resource,
    metric_readers=[
        PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=ENDPOINT, insecure=True),
            export_interval_millis=5_000,
        )
    ],
    views=[
        View(
            instrument_name="gen_ai.client.operation.duration",
            aggregation=ExplicitBucketHistogramAggregation(DURATION_BUCKETS),
        )
    ],
)
metrics.set_meter_provider(_meter_provider)

tracer = trace.get_tracer(SERVICE)
_meter = metrics.get_meter(SERVICE)

# 慣例是兩個獨立的 counter，不是一個 counter 配 token_type 標籤。
input_tokens = _meter.create_counter(
    "gen_ai.client.inference.usage.input_tokens", unit="{token}", description="輸入 token 數"
)
output_tokens = _meter.create_counter(
    "gen_ai.client.inference.usage.output_tokens", unit="{token}", description="輸出 token 數"
)
operation_duration = _meter.create_histogram(
    "gen_ai.client.operation.duration", unit="s", description="單次模型呼叫耗時"
)


def shutdown() -> None:
    """CLI 跑完就結束，不強制送出的話最後一批資料會跟著行程一起消失。"""
    _tracer_provider.shutdown()
    _meter_provider.shutdown()
