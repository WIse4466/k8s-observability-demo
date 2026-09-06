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

EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn ${SERVICE_NAME}.main:app --host 0.0.0.0 --port 8000"]
