# -*- coding: utf-8 -*-
"""Agent 运行时：工具调用、分层移交、对话记录与有界重试。

用法（从 src 下的页面调用）:
    from engine import run_agent
    reply = run_agent("agent名", messages, on_event)
"""
import importlib.util
import json
import logging
import re
import time

import openai

from settings import config
from network import http_client
from diagnostics import record_failure
from chat_support import image_artifacts, generation_task_key

from project_paths import ROOT, TOOL_SPECS
AGENTS_DIR = ROOT / "agents"
MAX_ROUNDS = 24  # 模型最多连续调 Tool 的圈数
MAX_RETRIES = 3  # 模型网络错误/5xx 的重试次数

_client = openai.OpenAI(api_key=config.DEEPSEEK_API_KEY or "not-configured",
                        base_url=config.DEEPSEEK_BASE_URL, timeout=60, max_retries=0,
                        http_client=http_client(config.DEEPSEEK_BASE_URL))
logger = logging.getLogger(__name__)


def _emit(on_event, *event):
    # A display failure must never break the tool-call/result protocol.
    if on_event:
        try:
            on_event(*event)
        except Exception:
            logger.warning("Progress display failed for %s", event[1])


def _validate_name(name):
    if not isinstance(name, str) or not re.fullmatch(r"[\w-]+", name):
        raise ValueError("Agent / Tool 名称只能包含字母、数字、中文、下划线和短横线")



def _load_agent(agent_name):
    _validate_name(agent_name)
    path = AGENTS_DIR / f"{agent_name}.json"
    if not path.is_file():
        raise ValueError(f"找不到 Agent 配置 agents/{agent_name}.json")
    agent = json.loads(path.read_text(encoding="utf-8"))
    for field in ("name", "modelName", "functionNames"):
        if field not in agent:
            raise ValueError(f"agents/{agent_name}.json 缺少字段: {field}")
    if "system_prompt" not in agent and "system_prompt_file" not in agent:
        raise ValueError(f"agents/{agent_name}.json 缺少 system_prompt 或 system_prompt_file")
    if "system_prompt_file" in agent:  # 提示词另存为文件，每次运行现读（页面上改了下一句就生效）
        prompt_file = ROOT / agent["system_prompt_file"]
        if not prompt_file.is_file():
            raise ValueError(f"找不到提示词文件 {agent['system_prompt_file']}")
        agent["system_prompt"] = prompt_file.read_text(encoding="utf-8")
    mode = agent.get("contextOutputMode", "full")  # 记忆模式：full=带完整历史；none=只带最后一条 user 消息（一次性投喂任务）
    if mode not in ("full", "none"):
        raise ValueError(f"contextOutputMode 暂只支持 full / none，收到: {mode}")
    return agent


def _load_tool_specs(function_names):
    all_tools = json.loads(TOOL_SPECS.read_text(encoding="utf-8"))
    specs = {t["function"]["name"]: t for t in all_tools}
    missing = [n for n in function_names if n not in specs]
    if missing:
        raise ValueError(f"tool_list.json 里缺少这些 Tool 的说明书: {'、'.join(missing)}")
    return [specs[n] for n in function_names]


def _handoff_spec(sub_name, description):
    """把下属 Agent 生成一份移交工具说明书：handoff_to_<下属名>，参数只有 task。"""
    return {
        "type": "function",
        "function": {
            "name": f"handoff_to_{sub_name}",
            "description": description or f"把任务移交给下属 Agent {sub_name} 处理，返回它的最终回复",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "交给该下属的完整任务说明（需包含它所需的全部信息）"},
                },
                "required": ["task"],
            },
        },
    }


def _run_handoff(sub_name, task, on_event, _depth):
    """执行下属 Agent：用它自己的配置跑一遍完整循环，最终回复作为 Tool 结果还给主管。"""
    artifacts, outcomes = [], {}
    def failures():
        return [failure for failure in outcomes.values() if failure is not None]
    try:
        if _depth >= 3:
            return {"ok": False, "error": "Agent 嵌套移交超过 3 层，已阻止"}
        if not isinstance(task, str) or not task.strip():
            return {"ok": False, "error": "task 必填：交给下属的完整任务说明"}
        sub_messages = [{"role": "user", "content": task.strip()}]
        def collect(agent, tool, arguments, result):
            if isinstance(result, dict):
                for path in image_artifacts(tool, result):
                    if not any(a['image_path'] == path for a in artifacts):
                        artifacts.append({'image_path': path, 'tool': 'generate_scene_image', 'kind': 'scene'})
                key = (agent, tool, generation_task_key(arguments))
                if result.get('ok'):
                    outcomes[key] = None
                elif result.get('ok') is False and not result.get('deferred'):
                    outcomes[key] = {'tool': tool, 'arguments': arguments,
                                     'error': result.get('error', '执行失败')}
            _emit(on_event, agent, tool, arguments, result)
        reply = run_agent(sub_name, sub_messages, collect, _depth=_depth + 1)
        return {"ok": not failures(), "agent": sub_name, "reply": reply,
                "artifacts": artifacts, "failures": failures()}
    except Exception as e:
        return {"ok": False, "error": f"移交给 {sub_name} 执行失败: {e}",
                "artifacts": artifacts, "failures": failures()}


def _call_tool(tool_name, arguments):
    """动态加载 tools/<名>.py 并调 run(**参数)；任何意外兜底成失败 dict，绝不抛异常。"""
    try:
        _validate_name(tool_name)
        path = ROOT / "tools" / f"{tool_name}.py"
        if not path.is_file():
            return {"ok": False, "error": f"找不到工具文件 tools/{tool_name}.py"}
        spec = importlib.util.spec_from_file_location(tool_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "run"):
            return {"ok": False, "error": f"tools/{tool_name}.py 没有暴露 run() 函数"}
        return module.run(**arguments)
    except Exception as e:
        return {"ok": False, "error": f"工具 {tool_name} 执行异常: {e}"}


def _chat_with_retry(model, messages, tools):
    """调模型；网络错误或 5xx 等 3/6 秒重试，最多 3 次；4xx（如鉴权失败）重试无意义，直接抛。"""
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            kwargs = {"model": model, "messages": messages,
                      "extra_body": {"thinking": {"type": "disabled"}}}
            if tools:
                kwargs["tools"] = tools
            return _client.chat.completions.create(**kwargs)
        except openai.APIConnectionError as e:  # 网络错误
            last_err = e
        except openai.APIStatusError as e:  # HTTP 错误
            if e.status_code < 500 and e.status_code not in (408, 429):
                raise
            last_err = e
        if attempt < MAX_RETRIES:
            time.sleep(3 * attempt)
    raise last_err


def run_agent(agent_name, messages, on_event=None, _depth=0):
    """跑一轮 Agent 对话，返回本轮最终回复文字。

    - messages: 完整对话记录（含 Tool 调用与结果），本函数直接往里追加；
      system_prompt 不存进去，每次调模型时临时放在最前（页面上改了下一句就生效）。
    - on_event: 每执行一次 Tool 就回调 on_event(agent名, tool名, 参数, 结果)，供页面实时显示；
      下属 Agent 调 Tool 时 agent名 是下属自己的名字。
    - contextOutputMode: full=带完整历史（默认）；none=只带最后一条 user 消息开跑（一次性投喂任务），
      本次往来在结束时仍同步回 messages，保持记录完整。
    - hierarchies: 每个下属 Agent 自动变成 handoff_to_<下属名> 工具（说明书用下属 description，
      参数只有 task），调用时用下属自己的配置跑完整循环。
    """
    if not config.DEEPSEEK_API_KEY:
        raise ValueError("请先在 config/config.py 配置 DEEPSEEK_API_KEY")
    agent = _load_agent(agent_name)
    tools = _load_tool_specs(agent["functionNames"])
    for sub_name in agent.get("hierarchies") or []:  # 下属 Agent 自动成为移交工具
        sub_cfg = _load_agent(sub_name)
        tools.append(_handoff_spec(sub_name, sub_cfg.get("description", "")))

    allowed_tools = {t["function"]["name"] for t in tools}
    if agent.get("contextOutputMode", "full") == "none":
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if not user_msgs:
            raise ValueError("contextOutputMode=none 需要至少一条 user 消息作为任务输入")
        working = [user_msgs[-1]]  # 只带最后一条 user 消息（即投喂的任务内容）
    else:
        working = messages

    try:
        for _ in range(MAX_ROUNDS):
            payload = [{"role": "system", "content": agent["system_prompt"]}] + working
            resp = _chat_with_retry(agent["modelName"], payload, tools)
            if not resp.choices:
                raise RuntimeError("模型未返回候选回复，请稍后重试")
            if resp.choices[0].finish_reason in ("length", "content_filter"):
                raise RuntimeError("模型回复被截断或拦截，请缩小任务后重试")
            msg = resp.choices[0].message
            tool_calls = msg.tool_calls or []

            if not tool_calls:  # 模型不再调 Tool，本轮结束
                reply = (msg.content or "").strip()
                if not reply:
                    raise RuntimeError("模型没有返回内容，请重试本轮")
                working.append({"role": "assistant", "content": reply})
                return reply

            # 把模型的 Tool 调用决定原样追加进对话记录
            working.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })

            pending_question = None
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    arguments = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = None
                if pending_question:
                    result = {"ok": False, "error": "等待用户回答后再执行此工具，尚未执行", "deferred": True}
                elif tool_name not in allowed_tools:
                    result = {"ok": False, "error": f"当前 Agent 未挂载工具 {tool_name}，请使用 tools 中的工具"}
                elif not isinstance(arguments, dict):
                    result = {"ok": False, "error": "Tool 参数不是合法的 JSON 对象"}
                elif tool_name.startswith("handoff_to_"):  # 移交给下属 Agent
                    result = _run_handoff(tool_name[len("handoff_to_"):],
                                          arguments.get("task"), on_event, _depth)
                else:
                    result = _call_tool(tool_name, arguments)
                if not isinstance(result, dict):
                    result = {"ok": False, "error": "工具必须返回 JSON 对象"}
                try:
                    encoded_result = json.dumps(result, ensure_ascii=False)
                except (TypeError, ValueError):
                    result = {"ok": False, "error": "工具结果无法序列化为 JSON"}
                    encoded_result = json.dumps(result, ensure_ascii=False)
                working.append({  # Store the result before any display callback.
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": encoded_result,
                })
                record_failure(agent_name, tool_name, result)
                _emit(on_event, agent_name, tool_name, arguments, result)
                if tool_name == "ask_human" and result.get("ok"):
                    pending_question = result

            if pending_question:  # 问过用户就停下等回答，问题+选项拼成本轮回复
                question = pending_question["question"]
                options = pending_question.get("options") or []
                options_text = " / ".join(options)
                reply = question + (f"（可选：{options_text}）" if options_text else "（请直接回答）")
                working.append({"role": "assistant", "content": reply})
                return reply

        raise RuntimeError(f"本轮已达到 {MAX_ROUNDS} 次处理上限，已完成的图片会保留，可继续处理剩余任务")
    finally:
        # Streamlit's Stop button raises a BaseException. Complete any outstanding
        # call IDs so the next user turn is still a valid API conversation.
        call_index = next((i for i in range(len(working) - 1, -1, -1)
                           if working[i].get("tool_calls")), None)
        if call_index is not None:
            answered = {m.get("tool_call_id") for m in working[call_index + 1:]
                        if m.get("role") == "tool"}
            for call in working[call_index]["tool_calls"]:
                if call["id"] not in answered:
                    working.append({"role": "tool", "tool_call_id": call["id"],
                                    "content": json.dumps({"ok": False, "error": "执行已中断，请检查已完成产物后再继续"}, ensure_ascii=False)})
        if working is not messages:  # none 模式：把本次往来同步回全局记录
            messages.extend(working[1:])


def retry_scene_tasks(tasks, on_event=None):
    """Retry exact failed image jobs; do not rerun recognition, cutout, or successes."""
    results = []
    for arguments in tasks:
        if not isinstance(arguments, dict):
            continue
        result = _call_tool('generate_scene_image', arguments)
        record_failure('psd_generate_agent', 'generate_scene_image', result)
        _emit(on_event, 'psd_generate_agent', 'generate_scene_image', arguments, result)
        results.append(result)
    return results
