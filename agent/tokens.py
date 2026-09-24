"""量一次問答花掉多少 token（Day 25 的成本那節）。

跟 main.py 是同一個迴圈，只是每輪多印一行用量。
    .venv/bin/python tokens.py
"""
from google import genai
from google.genai import types

import main as m

# gemini-3.1-flash-lite 付費價，每百萬 token（2026-09 查）
USD_IN, USD_OUT = 0.25, 1.50


def run(question: str = "目前有什麼告警？影響範圍多大？") -> None:
    client = genai.Client()
    config = types.GenerateContentConfig(
        system_instruction=m.SYSTEM_PROMPT,
        tools=m.TOOLS,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    total_in = total_out = 0

    for turn in range(1, m.MAX_TURNS + 1):
        resp = m.ask(client, contents, config)
        used = resp.usage_metadata
        tin, tout = used.prompt_token_count, used.candidates_token_count or 0
        print(f"第 {turn} 輪   輸入 {tin:6,}   輸出 {tout:5,}")
        total_in += tin
        total_out += tout

        contents.append(resp.candidates[0].content)
        calls = resp.function_calls
        if not calls:
            break

        parts = []
        for call in calls:
            output = m.BY_NAME[call.name](**dict(call.args or {}))
            parts.append(types.Part.from_function_response(name=call.name, response={"result": output}))
        contents.append(types.Content(role="user", parts=parts))

    cost = total_in / 1e6 * USD_IN + total_out / 1e6 * USD_OUT
    print(f"\n合計     輸入 {total_in:6,}   輸出 {total_out:5,}")
    print(f"這次花了 US$ {cost:.6f}")


if __name__ == "__main__":
    run()
