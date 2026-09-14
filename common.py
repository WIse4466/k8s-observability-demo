"""三個服務共用的 log 與指標設定。

刻意保持精簡——文章裡要能整段貼出來。
"""
import logging, os, sys, time
import structlog
from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

SERVICE = os.getenv("SERVICE_NAME", "unknown")

# --- 結構化日誌（Day 14）------------------------------------------------
def setup_logging():
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )
    return structlog.get_logger(service=SERVICE)


# --- 指標（Day 8 / Day 13）----------------------------------------------
requests_total = Counter(
    "http_requests_total", "HTTP 請求數", ["service", "path", "status"],
)
request_duration = Histogram(
    "http_request_duration_seconds", "HTTP 請求耗時", ["service", "path"],
    # 桶圍繞延遲 SLO 300ms 設，兩側都留刻度（Day 13）
    buckets=[0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0],
)
checkout_total = Counter("checkout_total", "結帳請求數", ["status"])
discount_missing_total = Counter(
    "discount_missing_total", "查不到折扣規則的次數", ["category"],
)


def instrument(app, log):
    """掛上 /metrics，並記錄每筆請求的耗時與狀態。"""
    @app.middleware("http")
    async def _mw(request, call_next):
        # 監控端點不計入自己的指標，否則每次抓取都會製造一筆假流量
        if request.url.path.startswith("/metrics"):
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        path = request.url.path
        requests_total.labels(SERVICE, path, str(response.status_code)).inc()
        request_duration.labels(SERVICE, path).observe(elapsed)
        log.info("request", path=path, status=response.status_code,
                 duration_ms=round(elapsed * 1000, 1))
        return response

    # 用一般路由而不是 app.mount()——mount 會讓 /metrics 變成 307 轉址到
    # /metrics/，而 Prometheus 抓的是不帶斜線的路徑。
    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
