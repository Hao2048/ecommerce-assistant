# -*- coding: utf-8 -*-
"""面板入口：顶部导航 + 「搭建面板」页。

启动: .venv/bin/streamlit run src/app.py
"""
import sys
from pathlib import Path

# Streamlit executes pages as scripts; keep sibling modules importable.
source_dir = str(Path(__file__).resolve().parent)
if source_dir not in sys.path:
    sys.path.insert(0, source_dir)

import streamlit as st

st.set_page_config(page_title="商品图工作室", layout="wide")  # 宽屏

nav = st.navigation(
    [
        st.Page("pages_build.py", title="搭建配置", icon=":material/tune:", default=True),
        st.Page("pages_studio.py", title="商品图工作室", icon=":material/photo_camera:", url_path="studio"),
    ],
    position="top",  # 页面切换放在左上角
)
nav.run()
