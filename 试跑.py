# -*- coding: utf-8 -*-
"""试跑：在终端里和某个 Agent 多轮对话，验收 engine.py。

用法:
  .venv/bin/python 试跑.py <agent名>

每调一次 Tool 打印一行 [Tool] 记录；输入 exit / 退出 结束对话。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import run_agent  # noqa: E402


def on_event(agent_name, tool_name, arguments, result):
    args_text = json.dumps(arguments, ensure_ascii=False)
    result_text = json.dumps(result, ensure_ascii=False)
    if len(result_text) > 120:
        result_text = result_text[:120] + "…"
    print(f"  [Tool] {agent_name} 调用 {tool_name} 参数={args_text} 结果={result_text}")


def list_agents():
    return sorted(p.stem for p in (ROOT / "agents").glob("*.json"))


def main():
    if len(sys.argv) < 2:
        print("用法: .venv/bin/python 试跑.py <agent名>   当前可用: " + (", ".join(list_agents()) or "（agents/ 里还没有 Agent）"))
        sys.exit(1)
    agent_name = sys.argv[1]
    cfg_path = ROOT / "agents" / f"{agent_name}.json"
    if not cfg_path.is_file():
        print(f"找不到 agents/{agent_name}.json，当前可用: " + (", ".join(list_agents()) or "（agents/ 里还没有 Agent）"))
        sys.exit(1)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    handoffs = [f"handoff_to_{s}" for s in cfg.get("hierarchies", [])]
    print(f"已加载 Agent「{cfg.get('name', agent_name)}」（模型: {cfg.get('modelName')}，"
          f"工具: {', '.join(cfg.get('functionNames', []))}"
          + (f"，移交: {', '.join(handoffs)}" if handoffs else "") + "）")
    print("开始对话（输入 exit 或 退出 结束）")

    messages = []
    while True:
        try:
            user_text = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n对话结束")
            return
        if not user_text:
            continue
        if user_text.lower() in ("exit", "quit", "退出"):
            print("对话结束")
            return
        messages.append({"role": "user", "content": user_text})
        try:
            reply = run_agent(agent_name, messages, on_event)
        except Exception as e:
            print(f"  [出错] {e}")
            continue
        print(f"Agent> {reply}")


if __name__ == "__main__":
    main()
