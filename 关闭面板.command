#!/bin/bash
# 双击即可关闭「商品场景图平台」服务。
# 搭建面板和测试页面都由同一个服务提供，停止它即可；浏览器里的标签页手动关掉就行。

PID=$(lsof -nP -iTCP:8501 -sTCP:LISTEN -t | head -1)
if [ -z "$PID" ]; then
  echo "服务当前没有在运行。"
  sleep 2
  exit 0
fi

echo "正在停止服务（进程 $PID）…"
kill "$PID"
for i in 1 2 3 4 5; do
  sleep 1
  kill -0 "$PID" 2>/dev/null || break
done
if kill -0 "$PID" 2>/dev/null; then
  echo "未能正常退出，强制结束。"
  kill -9 "$PID"
fi
echo "✅ 服务已关闭，浏览器里的两个标签页可以手动关掉了。"
sleep 2
