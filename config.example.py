# -*- coding: utf-8 -*-
"""复制为 config.py 后填写密钥。config.py 已被 Git 忽略。"""

# DeepSeek 官方 API：主对话、两个子 Agent、商品图片识别
DEEPSEEK_API_KEY = ""
DEEPSEEK_BASE_URL = 'https://api.deepseek.com'
DEEPSEEK_MODEL = 'deepseek-flash'
CAPTION_MODEL = 'deepseek-flash'

# 火山方舟：参考图生成最终商品场景图
ARK_API_KEY = ""
ARK_BASE_URL = 'https://ark.cn-beijing.volces.com/api/v3'
IMAGE_MODEL = 'doubao-seedream-5-0-flash-260915'

# Pixian 抠图（内部素材，不展示给用户）
PIXIAN_API_ID = ""
PIXIAN_API_SECRET = ""
MAIN_AGENT = 'product_scene_design_agent'

# 可选：默认读取环境变量及 macOS 系统代理。
# OUTBOUND_PROXY = 'http://127.0.0.1:7897'
# OUTBOUND_PROXY = ''  # 强制直连
