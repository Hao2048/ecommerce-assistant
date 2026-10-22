# -*- coding: utf-8 -*-
"""面板入口：顶部导航 + 「搭建面板」页。

启动: .venv/bin/streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="商品图工作室", layout="wide")  # 宽屏

nav = st.navigation(
    [
        st.Page("pages_build.py", title="搭建配置", icon=":material/tune:", default=True),
        st.Page("pages_test.py", title="商品图工作室", icon=":material/photo_camera:"),
    ],
    position="top",  # 页面切换放在左上角
)
nav.run()
