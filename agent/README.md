# agent — 把告警翻成人話（Day 25）

一隻 tool-calling agent，讀 Alertmanager 的告警，查 Prometheus 與 Loki 佐證，
輸出一段值班的人看得懂的說明。**它只讀資料、只輸出文字**，不做任何處置。

跑在自己電腦上，不進叢集——它要查的三個服務都靠 `kubectl port-forward` 接出來。

## 準備

```bash
python3 -m venv agent/.venv
agent/.venv/bin/pip install -r agent/requirements.txt
export GEMINI_API_KEY=你的金鑰          # 不要寫進程式碼
```

三個 port-forward，各佔一個終端機視窗：

```bash
kubectl port-forward -n monitoring svc/kps-kube-prometheus-stack-alertmanager 9093:9093
kubectl port-forward -n monitoring svc/kps-kube-prometheus-stack-prometheus 9090:9090
kubectl port-forward -n monitoring svc/loki-gateway 3100:80
```

## 跑

```bash
cd agent
.venv/bin/python main.py
.venv/bin/python main.py "pricing 的記憶體怎麼了"
```

## 環境變數

| 變數 | 預設 | 說明 |
| --- | --- | --- |
| `GEMINI_API_KEY` | 無，必填 | Gemini API 金鑰 |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | 換模型用 |
| `ALERTMANAGER_URL` | `http://localhost:9093` | |
| `PROMETHEUS_URL` | `http://localhost:9090` | |
| `LOKI_URL` | `http://localhost:3100` | |
