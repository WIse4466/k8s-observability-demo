# k8s-observability-demo

iThome 鐵人賽 2026「30 天在自架 K8s 上實踐可觀測性與告警」的示範服務。

這不是一個正常的服務，是一個**故意做壞的**服務。而且三個故障沒有一個是「服務掛掉」——
掛掉最好查，Pod 變紅一眼就看到。真實世界裡難查的都是另一種：還活著，但是不對。

## 架構

```
loadgen ──▶ gateway ──▶ catalog ──▶ pricing
（機器人）  （櫃台）    （倉庫）    （收銀）
```

| 服務 | 做什麼 |
| --- | --- |
| `gateway` | 對外入口，接收 `/checkout` |
| `catalog` | 查購物車裡有哪些商品 |
| `pricing` | 算價格與折扣 |
| `loadgen` | 不停送假請求的機器人，每秒 10 筆，購物車大小 8 成小車 / 2 成大車 |

前三個是 FastAPI 寫的網頁服務，`loadgen` 是一支一直跑的程式。

## 三個故障

用環境變數控制，預設全部關閉。

| 開關 | 故障 | 症狀 |
| --- | --- | --- |
| `BUG_SILENT_DISCOUNT=true` | 查不到折扣規則時接住例外、回傳 0 折扣 | 算錯價，但回 200、速度正常 |
| `BUG_N_PLUS_ONE=true` | 購物車超過 5 件時逐一呼叫 pricing | P95 惡化，P50 不動，錯誤率 0 |
| `LEAK_KB_PER_REQUEST=64` | 快取只進不出 | 記憶體持續上升，最後 OOMKilled 重啟 |

另有 `DB_LATENCY_MS`（預設 60）模擬 pricing 查折扣規則的資料庫成本。
沒有它，N+1 在本機快到看不出差別。

## 在 Kubernetes 上跑

需要 kind 叢集，叢集怎麼開見系列文章。

```bash
# 1. build
docker build --build-arg SERVICE=pricing -t pricing:0.1 .
docker build --build-arg SERVICE=catalog -t catalog:0.1 .
docker build --build-arg SERVICE=gateway -t gateway:0.1 .
docker build -f Dockerfile.loadgen -t loadgen:0.1 .

# 2. 載進 kind（節點看不到本機的映像檔，少這步會 ErrImagePull）
kind load docker-image pricing:0.1 catalog:0.1 gateway:0.1 loadgen:0.1 --name obs

# 3. 部署
kubectl apply -f k8s/
kubectl get pods
```

`k8s/servicemonitors.yaml` 需要 Prometheus Operator 的 CRD，還沒裝的話 `apply` 會噴
`no matches for kind "ServiceMonitor"`，這是正常的，其他資源照樣建得起來。

驗證：

```bash
kubectl port-forward svc/gateway 8080:80          # 開著別關
curl -s localhost:8080/checkout \
  -H 'content-type: application/json' \
  -d '{"items":["P001","P002","P003"]}'
```

每一筆的 `discount` 有值就代表故障都還關著。

## 在本機直接跑（不用 Docker / Kubernetes）

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run-local.sh          # log 在 .logs/
./stop-local.sh
```

## 環境

Dockerfile 三個服務共用，用 `--build-arg SERVICE=xxx` 指定打包哪一支。
`common.py` 是三支共用的 log 與指標設定，**所以 build 的位置必須是專案根目錄**，
寫成 `docker build ./gateway` 會 `ModuleNotFoundError`。
