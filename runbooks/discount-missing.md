# DiscountRuleMissing

**severity: ticket ／ team: pricing**

有商品查不到折扣規則。程式接住例外、回傳 0 折扣、狀態碼仍然是 200，
所以**使用者不會收到錯誤，但付的金額是錯的**。

這則是工單不是 page——金額算錯要修，但半夜修跟早上修沒有差別。

## 先確認範圍

```promql
sum by (category) (rate(discount_missing_total[5m]))
```

或從 log 看是哪些商品：

```
{app="pricing"} | json | event="discount rule not found"
```

`sum by (product_id)` 會列出所有缺規則的商品編號。

## 影響多大

```
sum(count_over_time({app="pricing"} | json | event="discount rule not found" [5m]))
  /
sum(count_over_time({app="gateway"} | json | event="checkout priced" [5m]))
```

這個比例是「受影響的訂單佔比」，不是「受影響的商品佔比」——
一筆訂單只要有一件商品缺規則，整筆金額就是錯的。

## 處理

1. 把缺規則的商品編號整理出來，交給負責建折扣規則的人補上
2. 補完之後這則告警會在 15 分鐘內自己解除
3. 如果缺的是整個分類，那通常是規則匯入漏了一批，要回頭查匯入流程
