# -*- coding: utf-8 -*-
"""搭建面板：给 PM 可视化配置主 Agent 与子 Agent（不做对话测试）。

由 app.py 通过 st.navigation 挂载为「搭建面板」页面。
布局：左栏（sidebar）= 主 Agent 配置 + 子 Agent 区；右栏 = 主 Agent System Prompt；右上角 = 保存。
"""
import json
from pathlib import Path

import streamlit as st

from settings import config

from project_paths import ROOT, TOOL_SPECS
AGENTS_DIR = ROOT / "agents"
MODELS = ["deepseek-flash"]


def read_json(path, default=None):
    path = Path(path)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tool_names():
    return [t["function"]["name"] for t in read_json(TOOL_SPECS, [])]


def model_options(current=None):
    """下拉选项 = 默认模型；当前配置用了其他模型时附加在后面，避免加载即崩/保存时被静默改掉。"""
    return MODELS + ([current] if current and current not in MODELS else [])


def default_main_cfg(name):
    return {
        "name": name,
        "description": "",
        "modelName": MODELS[0],
        "functionNames": [],
        "mcpServerList": {},
        "contextOutputMode": "full",
        "hierarchies": [],
    }


def get_prompt(cfg):
    """提示词按约定另存：有 system_prompt_file 就读那个文件，否则读内联 system_prompt。"""
    if cfg.get("system_prompt_file"):
        f = ROOT / cfg["system_prompt_file"]
        if f.is_file():
            return f.read_text(encoding="utf-8")
    return cfg.get("system_prompt", "")


def apply_prompt(cfg, prompt_text):
    """把提示词写回：有 system_prompt_file 就写对应文件并保留指向；否则内联进 JSON。"""
    if cfg.get("system_prompt_file"):
        (ROOT / cfg["system_prompt_file"]).write_text(prompt_text, encoding="utf-8")
        cfg.pop("system_prompt", None)  # 避免两份不同步
    else:
        cfg["system_prompt"] = prompt_text
    return cfg


def clear_sub_widget_state():
    for k in ("sub_name", "sub_desc", "sub_model", "sub_prompt", "sub_tools"):
        st.session_state.pop(k, None)


def sub_dialog(existing, old_name=None):
    """子 Agent 弹窗：existing 为空 = 新建，否则编辑 old_name 对应的子 Agent。"""
    is_new = existing is None
    base = existing or {"name": "", "description": "", "modelName": MODELS[0],
                        "functionNames": [], "system_prompt": ""}

    @st.dialog("新建子 Agent" if is_new else f"编辑子 Agent：{old_name}", width="large")
    def _dialog():
        st.text_input("Agent Name", key="sub_name", value=base.get("name", ""))
        st.text_input("一句话职责（主 Agent 靠它决定什么时候交给这个子 Agent）",
                      key="sub_desc", value=base.get("description", ""))
        model_opts = model_options(base.get("modelName"))
        st.selectbox("模型选择", model_opts, key="sub_model",
                     index=model_opts.index(base["modelName"]) if base.get("modelName") in model_opts else 0)
        st.text_area("System Prompt", key="sub_prompt", value=get_prompt(base), height=240)
        st.multiselect("Tool 挂载", tool_names(), key="sub_tools", default=base.get("functionNames", []))

        col_cancel, col_ok = st.columns(2)
        if col_cancel.button("取消", use_container_width=True):
            st.session_state["sub_dialog"] = None
            st.rerun()
        if col_ok.button("创建" if is_new else "保存", type="primary", use_container_width=True):
            name = (st.session_state.get("sub_name") or "").strip()
            if not name or "/" in name:
                st.error("Agent Name 必填，且不能包含 /")
                return
            if name != old_name and (AGENTS_DIR / f"{name}.json").is_file():
                st.error(f"agents/{name}.json 已存在，换个名字，避免覆盖已有 Agent 的配置")
                return
            cfg = {
                "name": name,
                "description": (st.session_state.get("sub_desc") or "").strip(),
                "modelName": st.session_state.get("sub_model"),
                "functionNames": st.session_state.get("sub_tools", []),
                "mcpServerList": base.get("mcpServerList", {}),
                "contextOutputMode": base.get("contextOutputMode", "full"),
                "hierarchies": base.get("hierarchies", []),
            }
            if base.get("system_prompt_file"):  # 沿用提示词另存约定
                cfg["system_prompt_file"] = base["system_prompt_file"]
            apply_prompt(cfg, st.session_state.get("sub_prompt", ""))
            write_json(AGENTS_DIR / f"{name}.json", cfg)

            # 自动挂进主 Agent 的 hierarchies：编辑保持原位置，新建追加到末尾
            main_name = (st.session_state.get("main_name") or config.MAIN_AGENT).strip()
            main_cfg = read_json(AGENTS_DIR / f"{main_name}.json", default_main_cfg(main_name))
            hier = list(main_cfg.get("hierarchies", []))
            if old_name and old_name in hier:
                hier = [name if h == old_name else h for h in hier]  # 原位替换，顺序不变
            elif name not in hier:
                hier.append(name)
            main_cfg["hierarchies"] = hier
            write_json(AGENTS_DIR / f"{main_name}.json", main_cfg)
            st.session_state["sub_dialog"] = None
            st.rerun()

    _dialog()


# ---------- 顶部标题栏 + 右上角按钮 ----------
head_l, head_m, head_r = st.columns([7.6, 1.2, 1.2])
with head_l:
    st.subheader("🛠️ 搭建面板")
with head_m:
    reload_clicked = st.button("🔄 重新加载", key="reload_main", use_container_width=True,
                               help="丢弃页面上的改动，从 agents/ 磁盘文件重新读取配置")
with head_r:
    save_clicked = st.button("💾 保存", key="save_main", use_container_width=True)

if reload_clicked:  # 从磁盘重读，防止旧页面保存时覆盖新配置
    for k in ("loaded_main", "main_model", "main_tools", "main_prompt", "sub_dialog",
              "sub_name", "sub_desc", "sub_model", "sub_prompt", "sub_tools"):
        st.session_state.pop(k, None)
    st.rerun()

# ---------- 左栏：主 Agent 配置 ----------
with st.sidebar:
    st.header("主 Agent")
    main_name = st.text_input("Name", key="main_name", value=config.MAIN_AGENT).strip() or config.MAIN_AGENT
    main_cfg = read_json(AGENTS_DIR / f"{main_name}.json", default_main_cfg(main_name))

    if (st.session_state.get("loaded_main") != main_name or
            st.session_state.get("main_model") not in model_options(main_cfg.get("modelName"))):  # 切换了主 Agent，刷新其余控件默认值
        st.session_state["loaded_main"] = main_name
        st.session_state["main_model"] = main_cfg.get("modelName", MODELS[0])
        st.session_state["main_tools"] = main_cfg.get("functionNames", [])
        st.session_state["main_prompt"] = get_prompt(main_cfg)

    st.selectbox("模型选择", model_options(main_cfg.get("modelName")), key="main_model")
    st.multiselect("Tool 挂载", tool_names(), key="main_tools")
    handoff_tools = [f"handoff_to_{s}" for s in main_cfg.get("hierarchies", [])]
    if handoff_tools:  # 子 Agent 自动变成的移交工具，只展示，不需要手动挂载
        st.caption("🤝 移交工具（随下方子 Agent 自动挂载）：" + "、".join(handoff_tools))

    st.divider()
    st.header("子 Agent")
    st.caption("点子 Agent 名片可编辑；主 Agent 靠「一句话职责」决定什么时候交给它")
    for sub_name in main_cfg.get("hierarchies", []):
        sub_path = AGENTS_DIR / f"{sub_name}.json"
        sub_cfg = read_json(sub_path, {"name": sub_name, "description": "（配置文件缺失，保存后将新建）",
                                       "modelName": MODELS[0], "functionNames": [], "system_prompt": ""})
        with st.container(border=True):
            st.markdown(f"**{sub_name}**")
            st.caption(sub_cfg.get("description", ""))
            if st.button("编辑", key=f"edit_{sub_name}", use_container_width=True):
                clear_sub_widget_state()
                st.session_state["sub_dialog"] = {"mode": "edit", "name": sub_name}
    if st.button("＋ 新建子 Agent", use_container_width=True):
        clear_sub_widget_state()
        st.session_state["sub_dialog"] = {"mode": "new", "name": None}

# ---------- 保存：写回 agents/<主Agent名>.json ----------
if save_clicked:
    name = (st.session_state.get("main_name") or config.MAIN_AGENT).strip() or config.MAIN_AGENT
    cfg = read_json(AGENTS_DIR / f"{name}.json", default_main_cfg(name))
    cfg["name"] = name
    cfg["modelName"] = st.session_state.get("main_model")
    cfg["functionNames"] = st.session_state.get("main_tools", [])
    apply_prompt(cfg, st.session_state.get("main_prompt", ""))  # 有另存文件就写文件
    write_json(AGENTS_DIR / f"{name}.json", cfg)
    st.success(f"已保存到 agents/{name}.json" + ("（提示词同步写回 " + cfg["system_prompt_file"] + "）" if cfg.get("system_prompt_file") else ""))

# ---------- 右栏：主 Agent System Prompt ----------
st.text_area(
    "主 Agent System Prompt",
    key="main_prompt",
    height=640,
    help="若该 Agent 配置了 system_prompt_file（提示词另存），保存时直接写回对应文件；否则内联存进 JSON",
)

# ---------- 子 Agent 弹窗（由 session_state 触发，页面重跑后仍保持打开） ----------
pending = st.session_state.get("sub_dialog")
if pending:
    if pending["mode"] == "edit":
        sub_name = pending["name"]
        cfg_e = read_json(AGENTS_DIR / f"{sub_name}.json") or {
            "name": sub_name, "description": "", "modelName": MODELS[0],
            "functionNames": [], "system_prompt": "",
        }
        sub_dialog(existing=cfg_e, old_name=sub_name)
    else:
        sub_dialog(existing=None)
