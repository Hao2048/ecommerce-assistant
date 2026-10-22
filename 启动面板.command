#!/bin/bash
# 双击即可启动「商品场景图平台」，并自动打开两个网页：
#   1) 搭建面板（给 PM 配置 Agent）
#   2) 测试页面（给用户聊天的产品页）
# 用完后：直接关闭弹出的终端窗口即可停止服务。

cd "$(dirname "$0")" || exit 1

PANEL_URL="http://localhost:8501/"
TEST_URL="http://localhost:8501/pages_test"

# 创建本地空配置，不覆盖已有密钥。
if [ ! -f config.py ]; then
  cp config.example.py config.py
  echo "已创建空的 config.py。请填写 DeepSeek、火山方舟凭证后重新启动；复杂背景抠图还需 Pixian 凭证。"
  exit 1
fi

# 1) 首次运行：自动创建虚拟环境并安装依赖
if [ ! -x .venv/bin/streamlit ]; then
  echo "首次运行：正在创建虚拟环境并安装依赖（约 1-2 分钟）…"
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
fi

# 2) 服务已在运行：直接打开两个网页
if curl -s --max-time 2 http://localhost:8501/_stcore/health 2>/dev/null | grep -q ok; then
  echo "服务已在运行，打开两个网页…"
  [ "$NO_OPEN" != "1" ] && open "$PANEL_URL" "$TEST_URL"
  sleep 2
  exit 0
fi

# 3) 启动服务，5 秒后自动打开两个网页
[ "$NO_OPEN" != "1" ] && ( sleep 5; open "$PANEL_URL" "$TEST_URL" ) &
echo "服务启动中… 请保持本窗口开着；用完后直接关闭本窗口即可停止服务。"
exec .venv/bin/streamlit run app.py --server.headless true
