"""讀告警的 agent（Day 25）——把 Alertmanager 的告警翻成人話。

用法：
    export GEMINI_API_KEY=...
    python agent/main.py                    # 問預設問題
    python agent/main.py "pricing 怎麼了"   # 問自己的問題

前提：三個 port-forward 都開著（見 agent/README.md）。
"""
import os
import sys
import time

from google import genai
from google.genai import types
from google.genai import errors

from tools import list_alerts, query_metrics, search_logs

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")  # 釘住版本，不要用 -latest 別名
MAX_TURNS = 8  # 防呆：模型如果一直查下去，最多 8 輪就停

TOOLS = [list_alerts, query_metrics, search_logs]
BY_NAME = {f.__name__: f for f in TOOLS}

SYSTEM_PROMPT = """你是一個維運助手，負責把 Kubernetes 的告警翻譯成值班人員看得懂的說明。

流程：
1. 用 list_alerts 看目前觸發中的告警
2. 用 query_metrics 確認影響範圍——多少比例的請求受影響、目前的數值是多少
3. 需要細節時用 search_logs 撈錯誤訊息

輸出格式：
- 第一句話說明發生什麼事，以及使用者感受得到什麼
- 從何時開始
- 判斷依據：列出你查了哪些指標、數值是多少

規則：
- 回答之前一定要先呼叫工具。不要憑空判斷工具查不查得到，先查了再說。
- 只根據工具回傳的資料回答。查過之後還是查不到，就說查不到，不要推測。
- 每個數字都要說明來自哪一次查詢。
- 不要建議重啟、回滾或靜音告警。你的工作是說明現況，處置由人決定。
- 用繁體中文回答，不要用條列式術語堆疊，寫成人看得懂的句子。
"""


def ask(client, contents, config):
    """送一次請求。

    免費額度會回兩種擋人的錯：503 是模型忙線，429 是每分鐘請求數超標。
    兩種都是等一下就好，所以一起重試。
    """
    waits = (10, 30, 60)
    for attempt in range(len(waits) + 1):
        try:
            return client.models.generate_content(model=MODEL, contents=contents, config=config)
        except (errors.ServerError, errors.ClientError) as e:
            if isinstance(e, errors.ClientError):
                if e.code != 429:
                    raise
                # 429 有兩種：每分鐘超標等一下就好，每日額度用完等到明天也不會好。
                # 後者再重試只是把剩下的額度也燒掉，直接停。
                if "PerDay" in str(e):
                    raise RuntimeError(f"{MODEL} 今天的免費額度用完了，換模型或等明天") from None
            if attempt == len(waits):
                break
            why = "超過每分鐘額度（429）" if isinstance(e, errors.ClientError) else "模型忙線（503）"
            print(f"         {why}，等 {waits[attempt]} 秒重試")
            time.sleep(waits[attempt])
    raise RuntimeError(f"{MODEL} 連續被擋，晚點再試")


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else "目前有什麼告警？影響範圍多大？"

    client = genai.Client()  # 讀環境變數 GEMINI_API_KEY，不要把金鑰寫進程式
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=TOOLS,
        # 關掉自動呼叫。SDK 仍然會從函式簽章和 docstring 產生工具定義，
        # 但「呼叫工具」這一步改成我們自己做——迴圈要看得見，明天才有東西可以量。
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    contents = [types.Content(role="user", parts=[types.Part(text=question)])]

    for turn in range(1, MAX_TURNS + 1):
        resp = ask(client, contents, config)
        contents.append(resp.candidates[0].content)

        calls = resp.function_calls
        if not calls:
            print(f"\n{'=' * 60}\n{resp.text}")
            return

        results = []
        for call in calls:
            args = dict(call.args or {})
            print(f"[第 {turn} 輪] 模型要呼叫 {call.name}({args})")
            try:
                output = BY_NAME[call.name](**args)
            except Exception as e:  # 工具壞掉不要讓整隻 agent 掛掉，把錯誤講給模型聽
                output = f"工具執行失敗：{type(e).__name__}: {e}"
            print(f"         → {output[:120]}{'…' if len(output) > 120 else ''}")
            results.append(types.Part.from_function_response(name=call.name, response={"result": output}))

        contents.append(types.Content(role="user", parts=results))

    print(f"\n跑滿 {MAX_TURNS} 輪還沒有結論，停手。")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        # 免費額度是「每個模型每天 20 次請求」，用完只能等隔天或換模型，
        # 這種情況印一行就好，不要噴一整頁 traceback
        sys.exit(f"\n{e}")
