# PodMemoryWillExhaustLimit

**severity: ticket ／ team: platform**

某個容器照目前的記憶體成長趨勢，四小時內會撞到 limit。
撞到的後果是 OOMKilled——Pod 被殺掉重啟，進行中的請求會失敗。

這則告警的特別之處：**現在還沒有任何症狀**。使用者沒受影響、SLI 是滿分。
四小時是刻意留的緩衝，所以這是工單不是 page。

## 先確認是不是真的洩漏

```promql
container_memory_working_set_bytes{namespace="default", container="pricing"}
```

把時間拉到 6 小時以上，看那條線的形狀：

- **一路往上、不回頭** → 洩漏。重啟只能重置計時器，問題還在
- **鋸齒狀、會掉下來** → 正常的配置與回收，可能只是流量變大
- **階梯狀跳上去之後平了** → 一次性載入了某個東西，不是洩漏

## 找洩漏在哪

1. 看這個容器最近有沒有部署過：`kubectl rollout history deploy/<name>`
2. 有的話，比對前後版本的差異，找「只進不出」的資料結構——
   快取沒有上限、全域的 list 一直 append、連線沒關
3. 這個示範服務的 `pricing` 就是故意寫了一個從不淘汰的快取（`_cache`）

## 緩解

- **重啟可以拖時間，但不是修好**：`kubectl rollout restart deploy/<name>`
- 真正的修法是給快取一個上限（LRU）或加上 TTL
- 如果短期內修不了，調高 memory limit 只是把 OOM 往後推，記得把這則告警的
  `predict_linear` 視窗一起拉長，不然它會一直響
