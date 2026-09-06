"""gateway — 對外入口（櫃台）。一筆 /checkout 會穿過 catalog 再到 pricing。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from fastapi import FastAPI
from pydantic import BaseModel
from common import setup_logging, instrument, checkout_total

CATALOG_URL = os.getenv("CATALOG_URL", "http://localhost:8001")

log = setup_logging()
app = instrument(FastAPI(), log)
client = httpx.AsyncClient(timeout=30.0)


class Cart(BaseModel):
    items: list[str]


@app.post("/checkout")
async def checkout(cart: Cart):
    try:
        r = await client.post(f"{CATALOG_URL}/items", json={"items": cart.items})
        r.raise_for_status()
        priced = r.json()["items"]
    except Exception as exc:
        checkout_total.labels("error").inc()
        log.error("checkout failed", error=str(exc))
        return {"error": "checkout failed"}

    total = round(sum(i["price"] for i in priced), 2)
    checkout_total.labels("success").inc()
    log.info("checkout priced", item_count=len(priced), total=total)
    return {"total": total, "item_count": len(priced), "items": priced}
