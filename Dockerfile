# 三個服務共用這一份，用 --build-arg SERVICE=xxx 指定要打包哪一個
FROM python:3.12-slim

WORKDIR /app

ARG SERVICE
ENV SERVICE_NAME=${SERVICE}

# 先裝相依套件再複製程式碼——這樣改程式碼時不用重裝套件，build 快很多
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common.py .
COPY ${SERVICE}/ ./${SERVICE}/

# --- 追蹤（Day 19）---
# 服務名跟著 build-arg 走；只送 trace，metrics 繼續給 Prometheus、log 繼續給 Loki
ENV OTEL_SERVICE_NAME=${SERVICE} \
    OTEL_TRACES_EXPORTER=otlp \
    OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_PYTHON_FASTAPI_EXCLUDED_URLS="metrics,healthz"
# Collector 在哪，由 k8s manifest 用 OTEL_EXPORTER_OTLP_ENDPOINT 決定，image 不寫死

EXPOSE 8000
# opentelemetry-instrument 會在程式啟動前把 FastAPI、httpx 換成會產生 span 的版本
CMD ["sh", "-c", "opentelemetry-instrument python -m uvicorn ${SERVICE_NAME}.main:app --host 0.0.0.0 --port 8000"]
