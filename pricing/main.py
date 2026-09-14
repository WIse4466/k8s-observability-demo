"""pricing — 算價格與折扣（收銀）。

埋了兩個故障：
  BUG_SILENT_DISCOUNT  故障一：查不到折扣規則時，接住例外回傳 0 折扣（Day 16 由 log 查出）
  LEAK_KB_PER_REQUEST  故障三：快取只進不出的記憶體洩漏（Day 24 由告警攔下）
"""
import os, sys, time, itertools, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from pydantic import BaseModel
from common import setup_logging, instrument, discount_missing_total

BUG_SILENT_DISCOUNT = os.getenv("BUG_SILENT_DISCOUNT", "false").lower() == "true"
LEAK_KB_PER_REQUEST = int(os.getenv("LEAK_KB_PER_REQUEST", "0"))
# 模擬查折扣規則要打一次資料庫。真實服務都有這一段，而它正是 N+1 會痛的原因。
DB_LATENCY_MS = float(os.getenv("DB_LATENCY_MS", "60"))

log = setup_logging()
app = instrument(FastAPI(), log)

CATEGORIES = ["shoes", "bags", "hats", "coats", "socks"]
BASE_PRICE = {f"P{i:03d}": 100 + i * 7 for i in range(1, 51)}
# 這兩個商品的折扣規則「忘了建」——故障一的根因
BROKEN = {"P013", "P027"}


def _rules():
    r = {pid: 0.10 for pid in BASE_PRICE}
    if BUG_SILENT_DISCOUNT:
        for pid in BROKEN:
            r.pop(pid, None)
    return r


RULES = _rules()
_cache: dict = {}                      # 故障三：從不淘汰
_seq = itertools.count()               # 保證每次 key 都不同


def _maybe_leak():
    if LEAK_KB_PER_REQUEST > 0:
        _cache[next(_seq)] = "x" * (LEAK_KB_PER_REQUEST * 1024)


def category_of(product_id: str) -> str:
    return CATEGORIES[int(product_id[1:]) % len(CATEGORIES)]


def _price_one_nodb(product_id: str) -> dict:
    """不含資料庫延遲的定價邏輯，批次路徑用。"""
    _maybe_leak()
    _maybe_leak()
    base = BASE_PRICE.get(product_id, 100)
    category = category_of(product_id)
    try:
        discount = RULES[product_id]
    except KeyError:
        # ↓↓↓ 故障一：接住例外、記一行 WARN、回傳 0 折扣繼續跑 ↓↓↓
        log.warning("discount rule not found", product_id=product_id, category=category)
        discount_missing_total.labels(category).inc()
        discount = 0
    return {"product_id": product_id, "category": category,
            "price": round(base * (1 - discount), 2), "discount": discount}


def price_one(product_id: str) -> dict:
    """單筆查詢：每次都要打一次資料庫。"""
    if DB_LATENCY_MS > 0:
        time.sleep(random.uniform(0.8, 1.2) * DB_LATENCY_MS / 1000)
    return _price_one_nodb(product_id)


class Batch(BaseModel):
    product_ids: list[str]


@app.get("/price")
def price(product_id: str):
    return price_one(product_id)


@app.post("/prices")
def prices(body: Batch):
    """批次查詢：一次撈完所有規則，只付一次資料庫成本。"""
    if DB_LATENCY_MS > 0:
        time.sleep(random.uniform(0.8, 1.2) * DB_LATENCY_MS / 1000)
    return {"items": [_price_one_nodb(p) for p in body.product_ids]}


@app.get("/healthz")
def healthz():
    return {"ok": True, "cached_entries": len(_cache)}
