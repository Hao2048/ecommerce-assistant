# Tool 清单

> 每个工具都用 `测试台.py` 真实跑过一次；✅ = 通过，❌ = 未通过（附原因）。
> 最近全量验证时间：2026-10-03 10:03（北京时间）

| Tool | 干什么 | 测试命令 | 状态 | 最近一次结果 |
|---|---|---|---|---|
| ask_human | 需要用户补充信息或做选择时向用户提问；不调 API，"停下等回答"由平台负责 | `.venv/bin/python 测试台.py ask_human '{"question": "要什么尺寸？", "options": ["1:1", "9:16"]}'` | ✅ | 返回 `ok:true`，原样带回问题和选项 |
| remove_background | 把商品图背景去掉，只留商品（Pixian API） | `.venv/bin/python 测试台.py remove_background '{"image_path": "样图/产品.jpg"}'` | ✅ | 生成 `输出/产品_抠图_100325004.png`，RGBA 透明通道有效 |
| caption_image | 看图识别商品：有无明确主体 + 品类/外观/颜色/材质/用途（DeepSeek 官方 deepseek-flash） | `.venv/bin/python 测试台.py caption_image '{"image_path": "样图/产品.jpg"}'` | ✅ | `has_product:true`，描述"蓝色液体容器、黑色瓶盖，疑似洗护用品瓶" |
| generate_scene_image | 把抠好的商品放进场景生成新图（火山方舟 Seedream 5.0 Flash，支持 1:1/3:4/4:3/9:16/16:9） | `.venv/bin/python 测试台.py generate_scene_image '{"image_path": "输出/产品_抠图_100325004.png", "prompt": "the product on a wooden desk by the window, soft morning light"}'` | ✅ | 生成 `输出/产品_场景_100344367.png`（1024×1024，商品外观保持不变） |

## 说明

- **约定**：每个 Tool 三件套——`tools/<名>.py`（只暴露 `run()`，永远返回 dict，绝不抛异常）+ `tool_list.json` 说明书 + 用 `测试台.py` 测过才算完成。
- **退出码**：测试台退出码 0 = `ok:true`，1 = 失败，可接 CI。
- **未覆盖的报错路径**（也都人工验过，返回中文 error）：缺参数、文件不存在、非法 aspect_ratio、凭证未配置。

## 待接入的 Tool（需求文档里有、还没做）

| Tool | 用途 | 状态 |
|---|---|---|
| handoff_to_\<下属名\>（engine 按 hierarchies 自动生成，不在 tool_list.json） | 主 Agent 移交任务给下属 Agent，返回其最终回复；参数只有 task | ✅ 已接入 |
| planning_generation / planning_status | 生成并跟踪任务规划 | ⬜ 未开始 |
| parallel_tool_invoker | 并行调用多条生图方案 | ⬜ 未开始 |
| agent_end_tool | Agent 结束信号 | ⬜ 未开始 |

## 2026-10-15 模型切换验证

- 主 Agent、方案子 Agent、生图执行子 Agent、演示 Agent 和商品识别统一使用 DeepSeek 官方 `deepseek-flash`；工具调用显式关闭思考模式。
- 生图使用火山方舟 `doubao-seedream-5-0-flash-260915`，直接传入商品参考图；不使用 Flash 不支持的组图参数。每个请求仅生成一张最终场景图。
- 白色耳机参考图的识别 → 方案设计 → 单张生图 → 移交回传已通过真实 API 验证，产物为 1536×2048（3:4）。该次完整链路约60秒，仅作为本次观测。
- 抠图仍使用 Pixian，本次模型切换未重新调用抠图接口；中间产物仅供内部参考。
- 回归命令：`.venv/bin/python -m unittest discover -s tests -v`，当前30项通过，覆盖鉴权失败不重试、503与TLS中断重连、空图片失败、最终产物过滤及失败任务补图。
- 密钥只存于被 Git 忽略的 `config.py`；可提交的模板为 `config.example.py`。
