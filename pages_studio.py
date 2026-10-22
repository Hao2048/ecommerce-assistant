# -*- coding: utf-8 -*-
"""Customer-facing scene studio; model history and display history are kept separate."""
import html
import json

import streamlit as st

import config
from chat_support import (clean_reply, error_message, image_artifacts, local_image, save_upload,
                          deliverable_paths, retry_tasks_from_results, generation_task_key)
from engine import run_agent, retry_scene_tasks
from diagnostics import capture_history

PAGE_CSS = """
<style>
:root { --accent:#0071e3; --ink:#20242b; --muted:#596471; --line:#dfe4eb; }
html, body, button, input, textarea { font-family: -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; }
[data-testid="stAppViewContainer"] { background:#f6f7f9; color:var(--ink); }
[data-testid="stHeader"] { background:#f6f7f9; }
[data-testid="stMainBlockContainer"] { max-width:1040px; padding:3rem 2.5rem 6rem; }
[data-testid="stSidebar"] { background:#fff; border-right:1px solid var(--line); }
h1 { font-size:2.3rem !important; font-weight:650 !important; letter-spacing:-.03em; }
.studio-description { color:var(--muted); font-size:1rem; line-height:1.8; max-width:48ch; margin:0 0 2rem; }
.studio-welcome { padding:2rem 0 1rem; }
.studio-welcome h2 { font-size:1.65rem; font-weight:600; letter-spacing:-.02em; }
.studio-welcome p { color:var(--muted); line-height:1.85; max-width:55ch; }
.workflow { display:flex; gap:1.6rem; color:var(--muted); font-size:.85rem; padding:1rem 0; margin:1rem 0 2rem; border-top:1px solid var(--line); border-bottom:1px solid var(--line); }
[data-testid="stChatMessage"] { background:transparent; padding:1rem 0; }
[data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"] { display:none; }
[data-testid="stChatMessageContent"] { min-width:0; padding:.25rem 0; }
[data-testid="stChatMessage"]:has(.m-user) [data-testid="stChatMessageContent"] { background:#e8eff9; border-radius:14px; padding:1rem 1.25rem; margin-left:12%; }
.m-user { display:none; }
[data-testid="stChatMessage"] img { border-radius:12px; }
[data-testid="stStatus"] { background:#fff; border-color:var(--line); border-radius:12px; }
[data-testid="stBottom"] { background:#f6f7f9; }
[data-testid="stBottomBlockContainer"] { max-width:1040px; padding:1rem 2.5rem; }
[data-testid="stChatInput"] { border:1px solid #c2ccd9; border-radius:14px; background:#fff; }
[data-testid="stChatInput"]:focus-within { border-color:var(--accent); }
.stButton button, .stDownloadButton button { border-radius:10px; min-height:44px; }
button:focus-visible, a:focus-visible { outline:2px solid var(--accent) !important; outline-offset:3px; }
::selection { background:#c9dfff; color:#183957; }
textarea { caret-color:var(--accent); }
a { text-underline-offset:3px; }
@media (max-width:640px) {
 [data-testid="stMainBlockContainer"] { padding:1.5rem 1rem 5rem; }
 [data-testid="stBottomBlockContainer"] { padding:.75rem 1rem; }
 h1 { font-size:1.9rem !important; }
 .workflow { gap:.75rem; flex-wrap:wrap; }
 [data-testid="stChatMessage"]:has(.m-user) [data-testid="stChatMessageContent"] { margin-left:4%; }
}
</style>
"""

TOOL_LABELS = {
    'caption_image': '识别商品', 'remove_background': '处理商品背景',
    'generate_scene_image': '生成场景图片', 'ask_human': '确认你的需求',
    'handoff_to_psd_proposal_agent': '制定拍摄方案',
    'handoff_to_psd_generate_agent': '执行拍摄方案',
}


def image_wall(paths, prefix):
    paths = deliverable_paths(paths)
    for row in range(0, len(paths), 2):
        columns = st.columns(min(2, len(paths) - row))
        for offset, (column, path) in enumerate(zip(columns, paths[row:row + 2])):
            with column:
                try:
                    file = local_image(path)
                    st.image(str(file), width='stretch')
                    st.download_button('下载原图', file.read_bytes(), file_name=file.name,
                                       mime='image/png', icon=':material/download:',
                                       key=f'download_{prefix}_{row + offset}', width='stretch',
                                       on_click='ignore')
                except (ValueError, OSError):
                    st.warning('这张图片已不可用，请重新生成。')


def send_user_message(text, image_path=None):
    st.session_state.messages.append({'role': 'user', 'content': text, 'image': image_path})
    combined = text + (f'\n[商品图路径] {image_path}' if image_path else '')
    st.session_state.agent_messages.append({'role': 'user', 'content': combined})
    st.session_state.need_reply = True
    st.rerun()


for key in ('messages', 'agent_messages'):
    if key not in st.session_state:
        st.session_state[key] = []

if st.session_state.get('diagnosed_history_length') != len(st.session_state.agent_messages):
    capture_history(st.session_state.agent_messages)
    st.session_state.diagnosed_history_length = len(st.session_state.agent_messages)
st.markdown(PAGE_CSS, unsafe_allow_html=True)
with st.sidebar:
    st.title('商品图工作室')
    st.caption('从一张商品图，开始一组场景创作。')
    if st.button('开始新对话', icon=':material/add:', width='stretch'):
        for key in ('messages', 'agent_messages'):
            st.session_state[key] = []
        st.session_state.need_reply = False
        st.session_state.pop('chat_composer', None)
        st.rerun()
    st.divider()
    st.subheader('准备一张清晰商品图')
    st.write('尽量完整展示商品，避免遮挡。白底或透明背景可以直接用于创作。')
    st.caption('JPG / PNG / WebP · 单张不超过 20MB')
    st.subheader('告诉我你想怎么拍')
    st.write('描述场景、图片比例和数量。也可以先上传图片，逐步确认需求。')
    st.caption('支持比例：1:1、3:4、4:3、9:16、16:9')
    uploaded = [m['image'] for m in st.session_state.messages if m.get('image')]
    if uploaded:
        st.divider()
        st.subheader('当前商品')
        try:
            st.image(str(local_image(uploaded[-1])), width='stretch')
        except ValueError:
            st.caption('原图已不可用，请重新上传。')

st.title('让商品，走进真实场景')
st.markdown('<p class="studio-description">上传商品图片，一起确定拍摄方向。识别、构思、生成，在同一段对话里完成。</p>', unsafe_allow_html=True)

if not st.session_state.messages:
    st.markdown('<div class="workflow"><span>上传商品</span><span>确认需求</span><span>规划场景</span><span>生成与下载</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="studio-welcome"><h2>今天，想为哪件商品拍摄？</h2><p>点输入框旁的附件按钮上传图片，再描述你的想法。你可以先从下面的场景开始，上传图片后再发送。</p></div>', unsafe_allow_html=True)
    choices = [('日常生活场景', '拍2张日常生活场景图，3:4竖版，纯商品展示'),
               ('品牌展示场景', '拍2张高端展台场景图，1:1正方形，纯商品展示'),
               ('人物使用场景', '拍2张人物使用场景图，3:4竖版')]
    for col, (label, example) in zip(st.columns(3), choices):
        if col.button(label, width='stretch'):
            st.session_state['chat_composer'] = example
            st.rerun()

for index, message in enumerate(st.session_state.messages):
    with st.chat_message(message['role']):
        if message['role'] == 'user':
            st.markdown('<span class="m-user"></span>', unsafe_allow_html=True)
            st.markdown(html.escape(message.get('content') or '').replace('\n', '<br>'), unsafe_allow_html=True)
            if message.get('image'):
                try:
                    st.image(str(local_image(message['image'])), width=240)
                except ValueError:
                    st.caption('上传图片已不可用，请重新上传。')
        else:
            if message.get('events'):
                with st.expander(f"处理记录 · {len(message['events'])} 个步骤", expanded=False):
                    for event in message['events']:
                        st.write(event)
            # Legacy messages may contain cutouts and a model-written path summary.
            visible_images = deliverable_paths(message.get('images') or [])
            if message.get('error') and visible_images:
                st.markdown(f'已生成 {len(visible_images)} 张场景图，可预览并下载。')
                st.warning('还有场景未完成，可以继续处理剩余图片。')
            elif message.get('error'):
                st.error(message['content'])
            elif message.get('content'):
                st.markdown(message['content'])
            if message.get('images'):
                image_wall(message['images'], f'history_{index}')
            if index == len(st.session_state.messages) - 1:
                for option_index, option in enumerate(message.get('options') or []):
                    if st.button(option, key=f'option_{index}_{option_index}'):
                        send_user_message(option)
                if message.get('error'):
                    retry_label = '重试未完成图片' if message.get('retry_tasks') else ('继续未完成部分' if visible_images else '重试本轮')
                    if st.button(retry_label, icon=':material/refresh:'):
                        if message.get('retry_tasks'):
                            st.session_state.pending_retry_tasks = message['retry_tasks']
                        elif visible_images:
                            st.session_state.agent_messages.append({'role': 'user', 'content':
                                '只继续上轮未完成的场景，不要重新识别、抠图或重做成功图片。已成功图片：' +
                                json.dumps(visible_images, ensure_ascii=False)})
                        st.session_state.need_reply = True
                        st.rerun()

if st.session_state.get('need_reply'):
    st.session_state.need_reply = False
    images, events, results = [], [], []
    outcomes = {}
    pending_jobs = st.session_state.pop('pending_retry_tasks', [])
    ask = {}
    with st.chat_message('assistant'):
        status = st.status('正在理解需求…', expanded=True)
        preview = st.container()
        def on_event(agent, tool, arguments, result):
            label = TOOL_LABELS.get(tool, '处理任务')
            success = isinstance(result, dict) and result.get('ok') is True
            line = ('已完成 · ' if success else '未完成 · ') + label
            events.append(line)
            status.write(line)
            status.update(label=label)
            results.append((tool, arguments, result))
            if isinstance(result, dict) and not result.get('deferred'):
                key = (agent, tool, generation_task_key(arguments))
                outcomes[key] = not success
            if tool == 'ask_human' and success:
                ask.update(result)
            new_images = [p for p in image_artifacts(tool, result) if p not in images]
            for path in new_images:
                images.append(path)
                with preview:
                    image_wall([path], f'live_{len(st.session_state.messages)}_{len(images)}')
        failed = False
        try:
            if pending_jobs:
                retry_results = retry_scene_tasks(pending_jobs, on_event)
                reply = ''
                st.session_state.agent_messages.append({'role': 'user', 'content':
                    '仅重试以下失败生图任务：' + json.dumps(pending_jobs, ensure_ascii=False)})
                st.session_state.agent_messages.append({'role': 'assistant', 'content':
                    '补图工具的实际结果：' + json.dumps(retry_results, ensure_ascii=False)})
            else:
                reply = run_agent(config.MAIN_AGENT, st.session_state.agent_messages, on_event)
            failed = any(outcomes.values()) and not ask
            status.update(label='等待你确认' if ask else ('部分步骤未完成' if failed else '本轮已完成'),
                          state='error' if failed else 'complete', expanded=False)
        except Exception as exc:
            reply = error_message(exc)
            failed = True
            ask.clear()
            status.update(label='本轮未完成，支持重试', state='error', expanded=False)
    content = clean_reply(ask.get('question', reply), bool(ask))
    if images and not ask:
        # Delivery copy is based on actual tool results, not model claims or file paths.
        content = f'已生成 {len(images)} 张场景图，可预览并下载。'
    elif failed and not ask:
        content = '本轮图片未生成成功。商品和需求已保留，可以重试未完成的任务。'
    elif not content:
        content = '请继续补充你的需求。'
    st.session_state.messages.append({'role': 'assistant', 'content': content, 'images': images,
                                      'events': events, 'options': ask.get('options', []), 'error': failed,
                                      'retry_tasks': retry_tasks_from_results(results)})
    st.rerun()

prompt = st.chat_input('上传商品图，描述你想要的场景…', accept_file=True,
                       file_type=['jpg', 'jpeg', 'png', 'webp'], key='chat_composer')
if prompt is not None:
    text = (prompt.text or '').strip()
    try:
        image_path = save_upload(prompt.files[0]) if prompt.files else None
        if text or image_path:
            send_user_message(text or '我上传了一张商品图', image_path)
    except ValueError as exc:
        st.error(str(exc))
