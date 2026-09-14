"""catalog — 查商品資料（倉庫）。

埋了一個故障：
  BUG_N_PLUS_ONE  故障二：購物車超過 5 件時，改成逐一呼叫 pricing（Day 20 由 trace 查出）
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from fastapi import FastAPI
from opentelemetry import trace
from pydantic import BaseModel
from common import setup_logging, instrument

BUG_N_PLUS_ONE = os.getenv("BUG_N_PLUS_ONE", "false").lower() == "true"
PRICING_URL = os.getenv("PRICING_URL", "http://localhost:8002")
N_PLUS_ONE_THRESHOLD = 5

log = setup_logging()
app = instrument(FastAPI(), log)
client = httpx.AsyncClient(timeout=10.0)


class Cart(BaseModel):
    items: list[str]


@app.post("/items")
async def items(cart: Cart):
    n = len(cart.items)
    # Day 19 手動埋點：把「這筆請求的購物車有幾件」掛到自動埋點開好的 HTTP span 上。
    # 故障二只在 n > 5 時發生，沒有這個屬性，看到 12 個 span 也只能猜。
    span = trace.get_current_span()
    span.set_attribute("cart.item_count", n)

    if BUG_N_PLUS_ONE and n > N_PLUS_ONE_THRESHOLD:
        # ↓↓↓ 故障二：N+1，每件商品各發一次請求 ↓↓↓
        priced = []
        for pid in cart.items:
            r = await client.get(f"{PRICING_URL}/price", params={"product_id": pid})
            priced.append(r.json())
        span.set_attribute("pricing.mode", "n_plus_one")
        log.info("priced items", item_count=n, mode="n_plus_one", calls=n)
    else:
        r = await client.post(f"{PRICING_URL}/prices", json={"product_ids": cart.items})
        priced = r.json()["items"]
        span.set_attribute("pricing.mode", "batch")
        log.info("priced items", item_count=n, mode="batch", calls=1)

    return {"items": priced, "item_count": n}
