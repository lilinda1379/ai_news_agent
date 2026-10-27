# 每日 AI 新闻助手 Agent

一个可运行的 Function Calling Agent：用户填写身份和订阅偏好后，LLM 自主决定搜索词、工具调用顺序、调用次数和停止时机，生成带真实来源链接的 AI 新闻简报，并按设定时间保存和推送到飞书。

## 核心能力

- 原生 Function Calling 循环，不是硬编码的“搜索→总结→推送”流水线。
- 题目要求的 `list_dir`、`read_file`、`search_content`、`write_file`、`bash` 五个工具全部实现。
- 额外提供 `search_news`，从 Google News RSS 获取实时新闻。
- 单页设置身份、话题、关键词、时区和每日推送时间。
- SQLite 保存设置、成功/失败简报和完整工具调用轨迹。
- APScheduler 每日触发；飞书 Webhook 负责推送。
- 路径沙箱、命令白名单、参数校验、重复调用拦截、最大 6 轮和来源链接校验。

## 5 分钟启动

环境要求：Python 3.11+，模型接口必须兼容 OpenAI Chat Completions 和 Tool Calling。

### Windows PowerShell

```powershell
git clone <your-repository-url>
cd ai-news-agent
./scripts/setup.ps1
```

打开自动生成的 `.env`，至少填写：

```env
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
OPENAI_MODEL=your-tool-calling-model
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-token
AGENT_MAX_STEPS=10
```

启动：

```powershell
./scripts/run.ps1
```

访问 <http://127.0.0.1:8000>。

### macOS / Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## 使用流程

1. 在首页填写身份、关注话题、关键词、时区和推送时间。
2. 是否启用飞书推送由页面开关决定，Webhook 只从环境变量读取。
3. 点击“生成今日简报”，页面会等待 Agent 完成。
4. 在历史记录中查看 Markdown 简报、运行状态、推送状态和工具调用轨迹。
5. 服务持续运行时，定时任务会按用户时区每日触发同一套 Agent。

### 工作区预置资料

`data/workspace/seed/` 里有四份 mock 资料，让 5 个文件类工具有真实使用场景：

- `history_2026-10-26.md`：昨天的简报，用来避免今天头条重复；
- `editorial_rules.md`：条数、来源、去重规则；
- `topics.md`：长期关注话题与屏蔽词；
- `README.md`：工作区说明。

Agent 生成前会 `list_dir` 看工作区、`read_file` 读规则和历史，生成后用 `write_file` 把简报写到 `digests/YYYY-MM-DD.md`。一次实测轨迹：

```
list_dir → bash → read_file ×5 → search_news ×3 → write_file
```

提示词只声明约束（新闻事实只能来自 `search_news`、编辑规范以 `seed/editorial_rules.md` 为准、简报要保存），不规定"先做什么再做什么"，顺序仍由模型决定。

## Agent Loop

```text
用户身份与偏好
      ↓
LLM（tools + tool_choice=auto）
      ↓
有 tool_calls？──否──→ 校验来源 → 保存简报 → 飞书推送
      │
      是
      ↓
校验参数 → 执行工具 → 结果以 role=tool 回填 → 下一轮 LLM
```

模型控制：

- 使用哪个工具；
- 每个工具调用几次；
- 搜索什么关键词；
- 何时停止并输出简报。

应用控制：

- 工具权限和参数校验；
- 最多 6 个模型轮次；
- 同工具同参数不重复执行；
- 最终 URL 必须来自 `search_news` 结果；
- 保存、调度和推送等确定性副作用。

因此 Agent 的推理/行动顺序由 LLM 决定，但系统边界仍然可审计、可测试。

## 工具列表

| 工具 | 作用 | 主要限制 |
|---|---|---|
| `list_dir(path)` | 列出工作目录 | 仅 `data/workspace` |
| `read_file(path)` | 读取 UTF-8 文件 | 限制输出长度 |
| `search_content(keyword, dir)` | 递归搜索内容 | 最多返回 100 条 |
| `write_file(path, content)` | 写入文件 | 禁止越界路径 |
| `bash(command)` | 执行安全命令 | 仅 `pwd/ls/echo/date/git status` |
| `search_news(query, limit)` | 搜索 AI 新闻 | Google News RSS，最多 20 条 |

## 数据库

SQLite 建表脚本位于 [`schema.sql`](schema.sql)：

- `settings`：单用户身份、偏好、时区和推送设置。
- `digests`：正文、触发来源、状态、推送状态、错误和 Agent 轨迹。

数据库首次启动自动初始化。默认运行文件是 `data/ai_news_agent.db`，已被 Git 忽略。

## API

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/` | Web 页面 |
| GET | `/health` | 健康检查 |
| GET/PUT | `/api/settings` | 读取或保存设置 |
| POST | `/api/digests/generate` | 立即生成一次简报 |
| GET | `/api/digests` | 历史简报 |
| GET | `/api/digests/{id}` | 简报详情和轨迹 |

## 测试

```powershell
./scripts/test.ps1
```

或直接运行：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
./.venv/Scripts/python.exe -m pytest -q
```

测试覆盖数据库生命周期、六个工具、路径和命令安全、RSS 去重、动态 Agent Loop、最大轮数、重复调用、来源真实性、页面 API、失败历史、飞书和定时任务。

## 项目结构

```text
app/
├── agent/       # Function Calling 循环、提示词、工具注册
├── tools/       # 文件、搜索、命令和新闻工具
├── services/    # 简报编排、飞书、定时任务
├── templates/   # 单页前端
├── static/      # 页面样式
├── config.py
├── database.py
└── main.py
tests/           # 自动化测试
docs/            # 架构与录屏脚本
examples/        # 示例简报与调用轨迹
schema.sql       # 建表脚本
```

## 配置与安全

- `.env`、数据库、虚拟环境和运行工作区不会进入 Git。
- API Key 与飞书 Webhook 不会写入数据库或 Agent Trace。
- `bash` 不是无限制系统 Shell，而是白名单命令执行器。
- RSS、模型或飞书失败时会保留失败记录，便于排查。
- 飞书失败不会删除已经生成的简报。

## 加固记录（相对最初可运行版本）

| 改动 | 位置 | 原因 |
|---|---|---|
| Agent 轮数可配置，默认 10 | `app/config.py`、`app/main.py` | RSS 偶发失败会让模型多搜几轮，6 轮不够 |
| SQLite WAL + busy_timeout | `app/database.py` | 调度线程与请求线程并发写，避免 database is locked |
| RSS 网络失败重试一次 | `app/tools/news.py` | 实测 SSL EOF / 握手超时，重试显著降低失败率 |
| 生成并发锁 + 409 | `app/services/digest.py`、`app/main.py` | 手动点击与定时任务可能撞车 |
| 工具描述补充触发条件 | `app/agent/tool_registry.py` | 让模型按"能力 + 时机 + 边界"判断何时调用 |

每处都有对应测试：`tests/test_config.py`、`tests/test_database.py`、`tests/test_news_tool.py`、`tests/test_digest.py`。

代码讲解与面试追问见 [`docs/walkthrough.md`](docs/walkthrough.md)。

更完整的设计说明见 [`docs/architecture.md`](docs/architecture.md)，三分钟演示顺序见 [`docs/demo-script.md`](docs/demo-script.md)。

## 已知限制

- MVP 只支持一个本地用户档案，不包含注册登录。
- 新闻正文来自 RSS 摘要，不额外抓取原网页全文。
- 定时任务随 Web 进程运行，服务关闭时不会触发。
- 当前只实现飞书推送；没有邮件、企业微信或推送重试队列。
