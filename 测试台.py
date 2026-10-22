# -*- coding: utf-8 -*-
"""工具测试台：单独验证一个 Tool 能否正常工作。

用法:
  .venv/bin/python 测试台.py <tool名> '<JSON参数>'   # 调用 tools/<tool名>.py 的 run(**参数)，打印返回 dict
  .venv/bin/python 测试台.py --list                  # 列出 tool_list.json 里所有 Tool 的名字和说明

约定: run() 永远返回 dict（成功 {"ok": true, ...}，失败 {"ok": false, "error": "中文原因"}），
退出码 0 = ok，1 = 失败，方便脚本和 CI 判断。
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS_DIR = ROOT / "tools"
TOOL_LIST = ROOT / "tool_list.json"


def load_run(tool_name: str):
    """按文件名加载 tools/<tool名>.py，返回其 run 函数。"""
    path = TOOLS_DIR / f"{tool_name}.py"
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"找不到工具文件 tools/{tool_name}.py"}, ensure_ascii=False))
        sys.exit(1)
    spec = importlib.util.spec_from_file_location(tool_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "run"):
        print(json.dumps({"ok": False, "error": f"tools/{tool_name}.py 没有暴露 run() 函数"}, ensure_ascii=False))
        sys.exit(1)
    return module.run


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--list":
        items = json.loads(TOOL_LIST.read_text(encoding="utf-8")) if TOOL_LIST.exists() else []
        if not items:
            print("tool_list.json 里还没有任何 Tool")
            return
        for item in items:
            fn = item.get("function", {})
            print(f"{fn.get('name', '?')}  {fn.get('description', '')}")
        return

    tool_name = sys.argv[1]
    raw_args = sys.argv[2] if len(sys.argv) > 2 else "{}"
    try:
        params = json.loads(raw_args)
        if not isinstance(params, dict):
            raise ValueError("JSON 参数必须是对象")
    except (json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"ok": False, "error": f"JSON 参数不合法: {e}"}, ensure_ascii=False))
        sys.exit(1)

    run = load_run(tool_name)
    try:
        result = run(**params)
    except Exception as e:  # 工具按约定不该抛异常，这里兜底保证测试台自身可用
        print(json.dumps({"ok": False, "error": f"工具调用出现未捕获异常: {e}"}, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if isinstance(result, dict) and result.get("ok") is True else 1)


if __name__ == "__main__":
    main()
