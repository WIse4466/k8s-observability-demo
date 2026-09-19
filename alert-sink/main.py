"""alert-sink — 接住 Alertmanager 的 webhook（Day 22）。

只做兩件事：
  1. 把每則告警寫成一行結構化 log，讓它跟其他服務的 log 一起進 Loki
  2. 存在記憶體裡，供 /alerts 查詢——後面那隻讀告警的 agent 要用
"""
import os, sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from common import setup_logging, instrument

log = setup_logging()
app = instrument(FastAPI(), log)

# 只留最近 200 則。這是示範環境，真的要保存請寫進資料庫
recent: deque = deque(maxlen=200)


@app.post("/alerts")
async def receive(request: Request):
    body = await request.json()
    alerts = body.get("alerts", [])
    for a in alerts:
        labels = a.get("labels", {})
        ann = a.get("annotations", {})
        entry = {
            "status": a.get("status"),
            "alertname": labels.get("alertname"),
            "severity": labels.get("severity"),
            "team": labels.get("team"),
            "summary": ann.get("summary"),
            "runbook_url": ann.get("runbook_url"),
            "startsAt": a.get("startsAt"),
        }
        recent.append(entry)
        log.info("alert received", **entry)
    return {"received": len(alerts)}


@app.get("/alerts")
def list_alerts():
    return {"count": len(recent), "alerts": list(recent)}


@app.get("/healthz")
def healthz():
    return {"ok": True}
