"""loadgen — 假裝成客人的機器人。沒有流量就沒有遙測資料可看。"""
import asyncio, os, random, sys, time
import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
RPS = float(os.getenv("RPS", "10"))
MAX_CART = int(os.getenv("MAX_CART", "12"))
PRODUCTS = [f"P{i:03d}" for i in range(1, 51)]


async def main():
    sent = ok = 0
    async with httpx.AsyncClient(timeout=30.0) as c:
        while True:
            # 購物車大小偏斜：8 成是小車、2 成是大車。真實電商就是這個形狀，
            # 而這正是「長尾」的來源——只有那 2 成會踩到故障二。
            size = random.randint(1, 5) if random.random() < 0.8 else random.randint(6, MAX_CART)
            items = random.sample(PRODUCTS, size)
            try:
                r = await c.post(f"{GATEWAY_URL}/checkout", json={"items": items})
                ok += 1 if r.status_code == 200 else 0
            except Exception as exc:
                print(f"[loadgen] {exc}", file=sys.stderr)
            sent += 1
            if sent % 50 == 0:
                print(f"[loadgen] sent={sent} ok={ok}", flush=True)
            await asyncio.sleep(1 / RPS)


if __name__ == "__main__":
    asyncio.run(main())
