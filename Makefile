# 一鍵重建（Day 30）。
# 叢集定義就在這個 repo 裡（Day 30 之前它在外面，別人 clone 下來第一步就做不了）
CLUSTER := obs
TAG := 0.3

.PHONY: up down images load charts services grafana verify

## 砍掉整個叢集。只移除 Helm release 是不夠的——CRD 和 PVC 會留下來
down:
	kind delete cluster --name $(CLUSTER)

## 從零重建
up: cluster images load charts services grafana
	@echo "重建完成。驗收請跑 make verify"

cluster:
	kind create cluster --config kind-config.yaml

images:
	docker build --build-arg SERVICE=pricing -t pricing:$(TAG) .
	docker build --build-arg SERVICE=catalog -t catalog:$(TAG) .
	docker build --build-arg SERVICE=gateway -t gateway:$(TAG) .
	docker build --build-arg SERVICE=alert-sink -t alert-sink:0.1 .
	docker build -f Dockerfile.loadgen -t loadgen:0.1 .

## kind 的節點看不到本機的映像檔，少這步會 ErrImagePull
load:
	kind load docker-image pricing:$(TAG) catalog:$(TAG) gateway:$(TAG) \
	  alert-sink:0.1 loadgen:0.1 --name $(CLUSTER)

## 全新叢集上不能直接 diff：helm-diff 要把 chart 渲染後對照叢集的 API，
## 但 Alertmanager / ServiceMonitor 這些 CRD 這時還不存在，渲染就先失敗。
## --skip-diff-on-install 讓「第一次安裝」的 release 跳過 diff，直接裝。
charts:
	helmfile apply --skip-diff-on-install

## ServiceMonitor 需要 Operator 的 CRD，所以一定要在 charts 之後
services:
	kubectl apply -f k8s/
	kubectl apply -f grafana/

## Terraform 要打 Grafana 的 API，所以要等 Grafana 起來、還要開 port-forward
grafana:
	kubectl wait --for=condition=ready pod \
	  -l app.kubernetes.io/name=grafana -n monitoring --timeout=600s
	@echo "接下來要手動開 port-forward 再跑 tofu apply，見 README"

verify:
	@echo "--- 節點 ---";        kubectl get nodes --no-headers | wc -l | xargs echo "  Ready 節點數:"
	@echo "--- 監控元件 ---";    kubectl -n monitoring get pods --no-headers | grep -c Running | xargs echo "  Running:"
	@echo "--- 示範服務 ---";    kubectl get pods --no-headers | grep -c Running | xargs echo "  Running:"
	@echo "--- 自訂指標 ---";    curl -s --get localhost:9090/api/v1/query --data-urlencode 'query=checkout_total' | python3 -c "import json,sys;print('  checkout_total 序列數:',len(json.load(sys.stdin)['data']['result']))"
	@echo "--- 告警規則 ---";    curl -s localhost:9090/api/v1/rules | python3 -c "import json,sys;gs=json.load(sys.stdin)['data']['groups'];mine=[r for g in gs if g['name'] in ('checkout','checkout-burn-rate','memory-trend') for r in g['rules']];print('  我寫的規則:',len(mine),'/ 全部:',sum(len(g['rules']) for g in gs))"
	@echo "--- exemplar ---";     curl -s --get localhost:9090/api/v1/query_exemplars --data-urlencode 'query=http_request_duration_seconds_bucket{job="gateway"}' --data-urlencode "start=$$(( $$(date +%s)-600 ))" --data-urlencode "end=$$(date +%s)" | python3 -c "import json,sys;print('  exemplar 數:',sum(len(x.get('exemplars',[])) for x in json.load(sys.stdin).get('data',[])))"
