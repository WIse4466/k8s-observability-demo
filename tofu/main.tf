# Day 28：用 OpenTofu 管 Grafana 裡面的東西。
#
# 為什麼是 OpenTofu 不是 Terraform：Terraform 從 2023 年起授權改成 BUSL，
# OpenTofu 是社群接手的 MPL 分支。語法、指令、provider 全部共用，
# 這份檔案兩邊都跑得起來，換個指令名而已。
#
# 為什麼需要它：Helm 裝得了 Grafana 這個程式，但管不到 Grafana 資料庫裡
# 存的東西。儀表板、資料夾、使用者都不是 Kubernetes 資源。

terraform {
  required_version = ">= 1.6"
  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "~> 4.0" # 鎖大版本：4.x 可以，5.0 不行
    }
  }
}

# 走 kubectl port-forward 開在本機的埠，跟 agent 一樣不進叢集。
# auth 從環境變數 GRAFANA_AUTH 來，格式是「帳號:密碼」。
# 密碼不寫進檔案，也不進 git。
provider "grafana" {
  url = "http://localhost:3000"
}

# 分工：資料夾歸這裡管，儀表板不歸。
#
# 我一開始兩個都寫在這裡，apply 直接被 Grafana 擋下來：
#
#   Error: [POST /dashboards/db][400] {"message":"Cannot save provisioned dashboard"}
#
# 因為那兩張圖是 sidecar 從 ConfigMap 送進去的，Grafana 把它們標成
# provisioned，而 provider 設定裡 allowUiUpdates 是 false，
# 所以網頁改不了、API 改不了、Terraform 也改不了。
#
# 這不是限制，是 Grafana 直接在源頭禁止「兩個權威來源」。
# 所以儀表板留給 ConfigMap，這裡只管 sidecar 做不到的事。
resource "grafana_folder" "observability" {
  title = "可觀測性"
  uid   = "observability"
}

# 儀表板的 ConfigMap 上有 grafana_folder: "可觀測性" 這個註記，
# sidecar 會照著把圖放進上面這個資料夾。兩個工具靠這個名字接起來。
