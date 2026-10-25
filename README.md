# Ecommerce Assistant · 电商助手

用一个能实际运行的商品场景图项目，学习 **多 Agent 如何分工、调用工具、移交任务，以及在失败后继续工作**。

上传一张商品图片，用对话确认场景、数量和比例，主 Agent 协调方案设计与图片生成，最终返回可下载的场景图。项目重点是让流程可读、可改、可验证，适合学习 Python、LLM 工具调用和多 Agent 编排。

**公开源码 · 非商用学习项目 · Python + Streamlit**

## 界面与运行结果

以下图片展示项目的 Agent 配置界面、商品图工作室与生成结果。

### Agent 搭建配置

在「搭建配置」页面，可以选择主 Agent 模型、挂载工具、编辑系统提示词，并管理子 Agent 与移交关系。学习时可以对照下方的流程图，观察配置如何决定各角色的职责与工具权限。

![Agent 搭建配置界面](docs/images/agent-config.png)

### 商品图工作室

![商品图工作室界面](docs/images/studio-ui.png)

### 商品场景图示例

<p align="center">
  <img src="docs/images/product-scene.png" alt="由商品参考图生成的耳机场景图" width="420">
</p>

这张示例由 Seedream 5.0 Flash 基于商品参考图生成。生成结果具有随机性，单张示例不代表所有商品的效果。

## 先理解这条多 Agent 流程

```mermaid
flowchart TD
    U[用户上传商品图片并描述需求] --> M[主 Agent：理解需求与编排]
    M --> C[caption_image：识别商品]
    C --> D{商品与需求是否明确}
    D -- 否 --> H[ask_human：提问并暂停]
    H --> A[用户补充信息]
    A --> M
    D -- 是 --> B{是否需要去除复杂背景}
    B -- 是 --> R[remove_background：Pixian 抠图]
    B -- 否 --> P[方案 Agent：设计拍摄方案]
    R --> P
    P --> G[生成 Agent：撰写提示词并执行]
    G --> I[generate_scene_image：Seedream 图生图]
    I --> O[最终场景图：预览与下载]
    I -- 部分失败 --> F[保留成功产物并记录失败任务]
    F --> T[用户选择补图：仅重试失败任务]
    T --> I
```

这里的 Agent 不是三个不同品牌的大模型，而是**配置、提示词、工具权限和上下文不同的三个角色**。当前三个角色都使用 `deepseek-flash`；真正生成图片的是独立的 Seedream 图像模型。

| 角色 | 负责什么 | 可以使用什么 |
| --- | --- | --- |
| 主 Agent `product_scene_design_agent` | 识别商品、确认需求、处理背景、协调子 Agent | 看图、抠图、提问，以及两个移交工具 |
| 方案 Agent `psd_proposal_agent` | 将商品信息与用户需求变成拍摄方案 | 纯文本生成，不挂载图片工具 |
| 生成 Agent `psd_generate_agent` | 将方案写成具体提示词，逐张生成图片 | 仅 `generate_scene_image` |

## 运行时是怎样工作的

主流程在 [engine.py](src/engine.py)，可以按下面的顺序阅读。

1. **读取角色配置。** 从 `agents/<name>.json` 加载模型、提示词、工具和下属 Agent；提示词可以独立放在 `prompts/`。
2. **组装工具说明书。** `config/tool_list.json` 告诉模型每个工具的用途、参数和必填项。挂载工具不等于已经执行工具。
3. **让模型决定下一步。** 模型可以直接回复，也可以返回一个或多个 `tool_calls`。Python 运行时验证权限、解析参数，再执行实际函数。
4. **把工具结果写回上下文。** 每个工具调用都有对应的 `tool_call_id` 和结果消息。工具失败也是结构化结果，不能丢失，否则下一轮接口可能拒绝对话记录。
5. **通过移交工具调用子 Agent。** `hierarchies` 会自动变成 `handoff_to_<name>`。子 Agent 使用自己的提示词和权限，返回回复及最终图片产物。
6. **在需要用户参与时暂停。** `ask_human` 返回问题与选项，当前回合结束；用户回答后继续主流程。
7. **按真实结果交付。** 界面只展示最终场景图，抠图保留在内部。失败图片可以单独补做，已成功的图片不会因为一次失败而丢失。

工具可以一批被模型提出，但当前执行器按顺序处理，**没有实现并行 Agent 或并行生图**。这个实现有意保持简单，方便逐步跟踪每一次调用。

## 模型与服务

| 环节 | 当前配置 | 配置位置 |
| --- | --- | --- |
| 主对话、方案设计、生图调度 | DeepSeek 官方 API，`deepseek-flash` | `agents/*.json` |
| 商品图片识别 | `deepseek-flash` 的视觉能力 | `CAPTION_MODEL` |
| 商品场景图生成 | 火山方舟，`doubao-seedream-5-0-flash-260915` | `IMAGE_MODEL` |
| 去除商品背景 | Pixian API | `PIXIAN_API_ID` / `PIXIAN_API_SECRET` |

DeepSeek 请求显式关闭思考模式，使用普通工具调用流程。生图每次请求输出一张图片，支持 `1:1`、`3:4`、`4:3`、`9:16`、`16:9`，并映射为明确的像素尺寸。服务的账号权限、额度和可用模型需要自行配置。

## 本地启动

建议使用 Python 3.11 或更新版本。下面以 macOS / Linux 为例。

```bash
git clone https://github.com/Hao2048/ecommerce-assistant.git
cd ecommerce-assistant
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements/requirements.txt
cp config/config.example.py config/config.py
```

在本地 `config/config.py` 填入自己的凭证。仓库只提供**凭证为空的配置副本** [config.example.py](config/config.example.py)，不包含真实 `config/config.py`。

| 配置项 | 用途 |
| --- | --- |
| `DEEPSEEK_API_KEY` | 对话、方案、工具调度与商品识别 |
| `ARK_API_KEY` | Seedream 图片生成 |
| `PIXIAN_API_ID` / `PIXIAN_API_SECRET` | 复杂背景商品的抠图 |

白底或透明背景图片可以跳过抠图；复杂背景流程需要 Pixian 凭证。填写后启动：

```bash
python -m streamlit run src/app.py
```

打开 `http://localhost:8501`，选择顶部的「商品图工作室」进入对话；「搭建配置」用于查看和修改 Agent 模型、提示词、工具与上下级关系。

Windows 可以使用 `py -m venv .venv`、`.venv\Scripts\Activate.ps1` 和 `Copy-Item config/config.example.py config/config.py`，其余 Python 命令相同。

### 跑一个最小例子

1. 上传一张商品主体清楚的图片。
2. 输入「拍 1 张温馨家居木桌场景图，3:4 竖版，纯商品展示」。
3. 如有缺失信息，回答 Agent 的问题。
4. 等待识别、方案设计与生图完成，下载最终图片。

建议先生成 1 张，理解完整流程后再增加数量。真实接口调用会消耗对应服务的额度。上传素材需有使用权，生成图片也应人工检查商品外观和细节。

## 从哪里开始读代码

```text
README.md                       项目说明与多 Agent 教程
LICENSE                         非商用许可证
.gitignore                      忽略凭证和运行产物
src/
  app.py                        Streamlit 入口与双页面导航
  pages_studio.py                用户对话、进度、最终图片与失败补图
  pages_build.py                 Agent 配置与提示词编辑
  engine.py                      模型调用、工具执行、上下文与 Agent 移交
  chat_support.py                上传校验、图片路径及最终产物过滤
  network.py                     代理与 HTTP 客户端
  diagnostics.py                 本地错误日志与凭证脱敏
  settings.py                    加载配置模板和本地凭证
  project_paths.py               项目资源路径
config/
  config.example.py              空凭证配置模板
  config.py                      本地凭证（自行创建，Git 忽略）
  tool_list.json                 发给模型的工具 JSON Schema
agents/                         每个角色的模型、工具和上下级配置
prompts/                        各角色的系统提示词
tools/                          识别、抠图、提问和生图工具
requirements/requirements.txt   Python 依赖
.streamlit/config.toml          Streamlit 主题配置
docs/NOTICE                     版权和授权声明
docs/images/                    README 使用的界面和结果图片
```

推荐阅读顺序：`agents/product_scene_design_agent.json` → 对应提示词 → `src/engine.py` 中的 `run_agent()` → `tools/ask_human.py` → 生图工具 → `src/pages_studio.py`。

## 三个适合练习的扩展

### 1. 新增一个工具

在 `tools/` 新建模块，提供 `run(**arguments)`，返回可 JSON 序列化的字典。成功返回 `{"ok": true, ...}`，失败返回 `{"ok": false, "error": "原因"}`。

然后在 `config/tool_list.json` 注册参数说明，并把工具名加入对应 Agent 的 `functionNames`。只写提示词里的工具名不会让工具自动可用。

### 2. 新增一个子 Agent

参考 `agents/psd_proposal_agent.json` 创建角色配置与提示词，再把新角色名加入主 Agent 的 `hierarchies`。运行时会自动生成移交工具。

给子 Agent 的 `task` 应包含它需要的全部信息，不能只写「按上面的要求执行」。尤其是 `contextOutputMode: "none"`，子 Agent 只看到最后一条任务输入，不会继承主 Agent 的完整对话。

### 3. 观察失败与恢复

用测试模拟暂时性连接中断、模型返回空图片、接口鉴权失败，观察哪些错误应该重试、哪些应该立即返回，以及已完成产物如何保留。

这个练习比一开始就增加 Agent 数量更容易帮助你理解运行时的边界。

## 配置与运行文件

根目录仅保留 README、忽略文件和许可证三个文件。源码位于 `src/`，配置位于 `config/`，依赖位于 `requirements/`，版权声明与展示图片位于 `docs/`。资源路径始终以项目目录为基准，上传和生成结果仍保存在项目目录下。

仓库仅保留运行电商助手需要的代码、Agent 配置、提示词、空配置模板，以及 README 使用的界面与结果图片。不包含测试目录、样例输入、旧需求文档、试跑脚本或桌面启动器。

`config/config.py`、`.env`、`.streamlit/secrets.toml`、`.runtime/`、用户上传及 `输出/` 不应提交。运行时会按需创建上传和输出目录，无需预先放入测试图片。

可以先做一次语法检查，再启动界面：

```bash
python -m compileall -q src tools
python -m streamlit run src/app.py
```

「商品图工作室」的地址是 `http://localhost:8501/studio`。使用自己的商品图片即可开始，最终图片会保存在本地 `输出/` 目录。

## 当前边界

这是本地教学项目，尚未提供用户登录、任务队列、会话数据库、并发隔离或生产部署方案。浏览器会话内保存对话，图片落在本地磁盘；多个子 Agent 按顺序执行。不要直接把当前 Streamlit 开发服务当作面向公众的生产服务。

## 许可证：非商用源码开放

本项目采用 [PolyForm Noncommercial License 1.0.0](LICENSE)，用于条款允许的非商用学习、研究、实验、修改和分发。商业使用需另行取得授权，完整条件以 [LICENSE](LICENSE) 和 [NOTICE](docs/NOTICE) 为准。

由于包含非商用限制，本项目属于 source-available（源码开放）项目，不属于 OSI 定义的允许商用的开源许可。第三方服务、依赖、商品品牌及素材的权利仍遵循各自条款。
