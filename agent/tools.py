"""agent 的三個工具（Day 25）。

三個都只是 HTTP GET，打的是 kubectl port-forward 開在本機的埠。
agent 跑在自己電腦上，不進叢集。

回傳一律是字串，因為模型只看得懂文字。原始 JSON 太大（一則 Alertmanager
告警含註解與 fingerprint 大約 800 字），所以每個工具都先挑掉用不到的欄位——
省下來的是 token，也是錢。
"""
import json
import os
import time

import httpx

ALERTMANAGER = os.getenv("ALERTMANAGER_URL", "http://localhost:9093")
PROMETHEUS = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
LOKI = os.getenv("LOKI_URL", "http://localhost:3100")

TIMEOUT = 15.0


def list_alerts() -> str:
    """列出 Alertmanager 目前正在觸發（firing）的告警。

    回傳每則告警的名稱、嚴重度、負責團隊、摘要、runbook 連結與開始時間。
    不需要任何參數，想知道「現在有什麼問題」就先呼叫這個。
    """
    r = httpx.get(f"{ALERTMANAGER}/api/v2/alerts", params={"active": "true"}, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for a in r.json():
        labels = a.get("labels", {})
        ann = a.get("annotations", {})
        out.append(
            {
                "alertname": labels.get("alertname"),
                "severity": labels.get("severity"),
                "team": labels.get("team"),
                "namespace": labels.get("namespace"),
                "pod": labels.get("pod"),
                "summary": ann.get("summary"),
                "description": ann.get("description"),
                "runbook_url": ann.get("runbook_url"),
                "startsAt": a.get("startsAt"),
            }
        )
    if not out:
        return "目前沒有任何觸發中的告警。"
    return json.dumps(out, ensure_ascii=False)


def query_metrics(promql: str) -> str:
    """對 Prometheus 執行一段 PromQL 即時查詢，用來確認影響範圍有多大。

    這套系統有的指標，以及它們的標籤：

    - http_requests_total：請求數。標籤 service（gateway/catalog/pricing）、path、status
    - http_request_duration_seconds_bucket：延遲直方圖。標籤同上，另有 le
    - checkout_total：結帳次數
    - discount_missing_total：查不到折扣規則的次數

    服務名稱的標籤在 Prometheus 是 service，不是 app——app 是 Loki 那邊才有的。

    Args:
        promql: PromQL 查詢字串。例如
            sum(rate(http_requests_total{service="pricing"}[5m]))
            算出 pricing 每秒的請求數。
    """
    r = httpx.get(f"{PROMETHEUS}/api/v1/query", params={"query": promql}, timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    if body.get("status") != "success":
        return f"查詢失敗：{body.get('error', '未知錯誤')}"
    result = body["data"]["result"]
    if not result:
        return "查詢成功，但沒有任何資料符合。這段 PromQL 可能指標名稱或標籤寫錯了。"
    out = [{"labels": s["metric"], "value": s["value"][1]} for s in result[:20]]
    return json.dumps(out, ensure_ascii=False)


def search_logs(logql: str, minutes: int = 30) -> str:
    """對 Loki 執行一段 LogQL 查詢，用來找出指標上看不到的細節。

    可以用的標籤只有 app、namespace、pod、container，服務名稱請用 app。
    四個應用服務是 gateway、catalog、pricing、loadgen，都在 default namespace。

    每一行 log 是一個 JSON，除了 event、level、timestamp、trace_id 之外，
    還會帶當下的欄位，例如 pricing 查不到折扣規則時會記 product_id 和 category。
    指標只有數字，要知道「是哪一筆」一定得撈 log。

    Args:
        logql: LogQL 查詢字串，一定要有大括號的標籤選擇器。例如
            {app="pricing"} |= "error"
            撈出 pricing 這個服務含有 error 字樣的 log。
        minutes: 往回撈幾分鐘，預設 30。
    """
    now = time.time()
    r = httpx.get(
        f"{LOKI}/loki/api/v1/query_range",
        params={
            "query": logql,
            "start": int((now - minutes * 60) * 1e9),
            "end": int(now * 1e9),
            "limit": 20,
            "direction": "backward",
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        return f"查詢失敗：{r.text[:300]}"
    streams = r.json()["data"]["result"]
    if not streams:
        return (
            "查詢成功，但這段時間沒有符合的 log。"
            "可以用的標籤只有 app、namespace、pod、container——"
            "標籤名稱寫錯不會報錯，只會查到空的。"
        )
    lines = []
    for s in streams:
        for _ts, line in s["values"]:
            lines.append(line[:500])
    return "\n".join(lines[:20])
