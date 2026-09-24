"""量 agent 講的話對不對（Day 26）。

前面的指標只答得出「它跑得順不順」，答不出「它講得對不對」。
這支程式用 Day 6 埋的三個故障當標準答案，加一個「全部關掉」的對照組。

用法：
    .venv/bin/python eval.py none      --runs 5
    .venv/bin/python eval.py discount  --runs 5

判分是關鍵字比對，很粗糙——但粗糙的量化仍然比「感覺還不錯」有用，
而且它抓得到一種最重要的錯：嘴上說查過、實際沒查。
"""
import sys

from opentelemetry import metrics

import main
import telemetry

QUESTION = "目前有什麼告警？影響範圍多大？"

# 每個 case 要開哪個故障，以及答案裡該出現什麼
CASES = {
    "discount": {
        "switch": "BUG_SILENT_DISCOUNT=true",
        # 每一組是「任一個命中就算」。第一版寫死 "pricing"，
        # 結果它寫「定價服務」被判錯——判分器修了兩輪才堪用。
        "must_have": [["折扣"], ["pricing", "定價"]],
        "must_not": ["一切正常", "沒有異常", "沒有問題", "非常健康"],
    },
    "nplusone": {
        "switch": "BUG_N_PLUS_ONE=true（在 catalog 上）",
        "must_have": [["延遲", "變慢"], ["catalog", "商品目錄"]],
        "must_not": ["一切正常", "沒有異常", "沒有問題", "非常健康"],
    },
    "leak": {
        "switch": "LEAK_KB_PER_REQUEST=8",
        "must_have": [["記憶體"], ["pricing", "定價"]],
        "must_not": ["一切正常", "沒有異常", "沒有問題", "非常健康"],
    },
    "none": {
        "switch": "全部關閉",
        # 對照組：沒事的時候，它該說沒事，不該編一個問題出來。
        # 這裡不能比對「故障」——它寫「並非真正的故障」是對的，第一版判分器就這樣誤判了。
        # 改成比對三個故障各自的症狀字，沒開故障卻講到就是編的。
        "must_have": [["Watchdog"]],
        "must_not": ["折扣", "記憶體", "延遲惡化"],
    },
}

# 這些話代表它宣稱查過指標或 log。沒有對應的工具呼叫就是講了沒做的事。
CLAIMS = {
    "query_metrics": ["指標", "PromQL", "每秒", "比例"],
    "search_logs": ["日誌", "log", "紀錄檔"],
}

_meter = metrics.get_meter("alert-agent-eval")
eval_result = _meter.create_counter("agent.eval.result", description="評測結果（自訂，非 OTel 慣例）")


def grade(case: str, answer: str, tools_called: list[str]) -> tuple[str, str]:
    spec = CASES[case]

    if len(tools_called) == 0:
        return "insufficient", "一個工具都沒呼叫"

    for tool, words in CLAIMS.items():
        if tool not in tools_called and any(w in answer for w in words):
            return "hallucination", f"說了「{next(w for w in words if w in answer)}」但沒呼叫 {tool}"

    missed = [w for w in spec["must_not"] if w in answer]
    if missed:
        # 把前後文一起印出來。關鍵字比對很容易誤判，
        # 沒有原文就分不出「是它錯」還是「是我的判分器錯」
        i = answer.index(missed[0])
        return "wrong", f"不該出現：…{answer[max(0, i - 18):i + len(missed[0]) + 12]}…"

    lacking = [g for g in spec["must_have"] if not any(w in answer for w in g)]
    if lacking:
        return "wrong", f"少了關鍵字：{'／'.join(lacking[0])}"

    return "correct", ""


def main_(case: str, runs: int) -> None:
    spec = CASES[case]
    print(f"case = {case}（故障開關：{spec['switch']}），跑 {runs} 次\n")
    tally: dict[str, int] = {}

    for i in range(1, runs + 1):
        try:
            result = main.run(QUESTION, quiet=True)
        except RuntimeError as e:
            print(f"  第 {i} 次  跑不完：{e}")
            break
        verdict, why = grade(case, result["answer"], result["tools_called"])
        tally[verdict] = tally.get(verdict, 0) + 1
        eval_result.add(1, {"case": case, "verdict": verdict})
        tools = ",".join(result["tools_called"]) or "無"
        print(f"  第 {i} 次  {verdict:14} 工具={tools:38} {why}")

    print()
    for verdict, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {verdict:14} {n}/{sum(tally.values())}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CASES:
        sys.exit(f"用法：eval.py [{'|'.join(CASES)}] [--runs N]")
    n = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 5
    try:
        main_(sys.argv[1], n)
    finally:
        telemetry.shutdown()
