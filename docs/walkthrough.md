# 代码讲解提纲（面试/复盘用）

> 目标：看完这份文档，你能按"一次请求"的顺序把整个仓库讲下来，并接住追问。

---

## 一、一张图看懂

```
浏览器 templates/index.html
   │  fetch('/api/settings', '/api/digests/generate')
   ▼
FastAPI  app/main.py（路由 + 启动时建表/起调度）
   │
   ├──► DigestService  app/services/digest.py（编排，带并发锁）
   │        │
   │        ├──► AgentRunner  app/agent/loop.py（唯一的循环）
   │        │        │  调模型（OpenAI SDK，tool_choice=auto）
   │        │        └──► ToolRegistry  app/agent/tool_registry.py
   │        │                 ├── filesystem.py：list_dir / read_file / search_content / write_file / bash
   │        │                 └── news.py：search_news（Google News RSS）
   │        │
   │        ├──► Database  app/database.py + schema.sql（SQLite）
   │        └──► FeishuPush  app/services/feishu.py（webhook）
   │
   └──► APScheduler  app/services/scheduler.py（按用户时区每日触发同一个 DigestService）
```

**一句话**：页面触发 → 服务编排 → 循环驱动模型 → 工具干活 → 轨迹和正文落库 → 可选推送。

---

## 二、一次「生成简报」的 10 步

1. 点按钮 → `POST /api/digests/generate`（`main.py`）
2. `DigestService.generate("manual")`：先拿锁，拿不到就抛 `already running`，接口返回 409
3. 读 `settings`（身份、话题、关键词、时区、推送开关）
4. `build_digest_task()` 把设置和当天日期拼成一段任务文字
5. `Database.create_digest()` 先插一条 `status=running` 的记录
6. `AgentRunner.run(SYSTEM_PROMPT, task)`：
   - `messages = [system, user]`
   - 循环最多 `AGENT_MAX_STEPS`（默认 10）轮：
     a. 调模型，带上 6 个工具的 schema，`tool_choice="auto"`
     b. 记一条 `model` 轨迹
     c. 没有 `tool_calls` → 校验 → 返回最终 Markdown
     d. 有 `tool_calls` → 先把 `assistant(tool_calls)` 追加进 messages
     e. 逐个执行：去重检查 → `ToolRegistry.execute`（pydantic 校验 → 调函数）→ 记 `tool` 轨迹 → 以 `role=tool` + `tool_call_id` 回填
   - 轮数用完 → 抛 `AgentLoopError("maximum agent steps exceeded")`
7. 校验通过 → `complete_digest()` 写入正文、轨迹、`push_status`
8. 推送开关打开且配了 webhook → 飞书推送
9. 返回简报 JSON → 前端 `location.reload()`
10. 页面展示历史、正文、可折叠的轨迹

失败路径同样走到底：`fail_digest()` 保存错误信息和已有轨迹，所以历史里能看到"为什么失败"。

**文件工具怎么被用起来**：`data/workspace/seed/` 预置了昨天的简报、编辑规则和关注话题。系统提示让模型"先看工作区、读需要的文件、写完后保存"，所以一次真实轨迹是：

```
list_dir → bash → read_file ×5 → search_news ×3 → write_file
```

这 5 个指定工具不是摆设：模型自己决定先读规则和历史、避免头条重复，最后把结果写回 `digests/YYYY-MM-DD.md`。

---

## 三、每个文件干什么

| 文件 | 职责 | 面试一句话 |
|---|---|---|
| `app/main.py` | 装配应用、6 个路由、lifespan | "入口只做装配，业务都在 service 里" |
| `app/config.py` | 环境变量 → `AppConfig` | "密钥和模型名都走环境变量" |
| `app/database.py` | SQLite 读写 + WAL | "settings 单行、digests 一行一次运行" |
| `schema.sql` | 建表 + 默认设置 | "幂等，启动时自动执行" |
| `app/agent/loop.py` | Function Calling 循环 | **核心**，见下一节 |
| `app/agent/prompts.py` | 系统提示词 + 任务拼装 | "规则和用户偏好分开" |
| `app/agent/tool_registry.py` | 工具表、schema、参数校验 | "名字→(pydantic 模型, 函数)" |
| `app/tools/filesystem.py` | 5 个本地工具 + 沙箱 + 白名单 | "路径必须落在 workspace 内" |
| `app/tools/news.py` | RSS 搜索 + URL 去重 | "失败返回结构化 error，让模型换词" |
| `app/services/digest.py` | 编排 + 并发锁 + 失败落库 | "成功失败都留痕" |
| `app/services/scheduler.py` | cron 触发 | "保存设置即重排任务" |
| `app/services/feishu.py` | webhook 推送 | "推送失败不影响简报完成" |
| `templates/index.html` | 表单 + 生成 + 历史 + 轨迹 | "纯 fetch，没有前端框架" |

---

## 四、核心：loop.py 讲什么

**三条不变量**（背下来）：

1. **每轮都传同一组工具 schema，`tool_choice="auto"`** —— 调不调、调哪个、调几次，全是模型决定，代码里没有任何"先搜索再总结"的顺序。
2. **模型说调工具，应用只做三件事**：校验参数、执行、把结果用 `tool_call_id` 回填，然后再问模型。
3. **模型不再要工具就是出口** —— 出口前做 grounding 校验，防止编造。

**结构**：

```
AgentRunner.run
├─ 初始化 messages / trace / seen / grounded
├─ for step in 1..max_steps
│   ├─ gateway.complete(messages, schemas)   → content / tool_calls
│   ├─ if 没有 tool_calls: 校验 → return
│   ├─ messages.append(assistant with tool_calls)
│   └─ for call in tool_calls:
│        ├─ 去重（name + 规范化参数）
│        ├─ registry.execute → {ok, data, error}
│        ├─ 记 trace / 更新 grounded_urls / searched_news
│        └─ messages.append({"role":"tool","tool_call_id":...})
└─ 超轮数 → AgentLoopError
```

**出口校验三连**（防幻觉）：

- 调过 `search_news` 且成功？没有 → `search_news was not called`
- 正文里有链接吗？没有 → `digest has no source link`
- 链接都来自搜索结果吗？不是 → `digest contains ungrounded source link`

---

## 五、五个必答设计点

### 1. 为什么手写循环，不用 LangChain / LangGraph
题目核心是"顺序由 LLM 决定"，手写 120 行把循环摊开，评审一眼能确认没有写死流程；框架会省掉这 120 行，但工具、校验、轨迹、调度一样要自己写，还多一层版本风险。需要多 Agent、断点续跑、人工审批时再换 LangGraph，替换点就是 `AgentRunner.run` 一个函数。

### 2. 怎么证明顺序真的是模型决定的
看 trace：每条 `model` 事件记录模型当轮要调什么，`tool` 事件记录实际执行结果；同一道题跑两次，搜索词和顺序可能不同。代码里搜不到任何固定的工具调用序列。

### 3. 死循环怎么防
两层：轮数上限（`AGENT_MAX_STEPS`，默认 10）+ 同工具同参数去重（返回 `duplicate tool call` 而不是重复执行）。

### 4. 工具失败为什么不抛异常
工具统一返回 `{ok, data, error}`。失败也作为 `role=tool` 的内容回填，模型能读到 `error` 自己换关键词重试——抛异常会直接打断循环，模型就没机会自愈。

### 5. 参数契约怎么保证一致
`tool_registry.py` 用 pydantic 模型定义参数，`model_json_schema()` 直接生成给模型的 schema，执行前 `model_validate`。schema 和实现同源，不会出现"模型传 query、函数收 keyword"那种错。

### 6. 工具描述按"能力 + 时机 + 边界"写
六条 description 都是三段式：能做什么、什么时候该用、什么时候别用或有什么限制。模型只读这段文字决定调不调，所以把"问今日新闻必须先调 `search_news`"直接写进描述，而不是只靠系统提示词。

### 7. 提示词只写约束，不写步骤
系统提示里没有"先 `list_dir` 再 `read_file`"这种顺序指令，只声明三条约束：新闻事实只能来自 `search_news`、编辑规范以 `seed/editorial_rules.md` 为准、简报保存到 `digests/`。模型为了满足约束，自己去决定先看目录还是先读文件。实测轨迹是：

```
list_dir → bash → read_file ×5 → search_news ×3 → write_file
```

顺序由模型决定，约束由提示词给——这两件事可以同时成立。

---

## 六、高频追问与答案

**Q：为什么用 SQLite？**
单用户本地应用，零运维；`settings` 一行、`digests` 一行一次运行，足够。换 Postgres 只需要换 `database.py`。

**Q：定时任务和手动点击撞车怎么办？**
`DigestService` 里有 `threading.Lock`，第二个请求直接 409；调度器本身也设了 `max_instances=1`。数据库开了 WAL + busy_timeout，避免并发写锁。

**Q：RSS 挂了怎么办？**
网络类异常重试一次；仍失败就返回结构化 error，模型可以换关键词或停止。整次失败也会落库，历史里能看到原因。

**Q：模型编造新闻链接怎么办？**
出口校验：链接必须 ⊆ 本次搜索结果里出现过的 URL，否则整次判失败。

**Q：为什么 6 轮改成 10 轮？**
实际联调里 RSS 会 SSL 失败，模型会重试搜索，6 轮不够用；改成环境变量可配，默认 10。

**Q：怎么加一个新工具？**
三步：在 `filesystem.py`/`news.py` 写函数 → 在 `tool_registry.py` 加 pydantic 参数模型和一行注册 → 加测试。循环和前端都不用动。

**Q：安全边界在哪？**
路径解析后必须位于 `data/workspace`；`bash` 只允许 `pwd/ls/echo/date/git status` 且 `shell=False`；读文件有 20k 截断、搜索最多 100 条。

**Q：失败了能看到什么？**
`digests` 里 `status=failed` + `error_message` + 已产生的 `trace_json`，页面上直接展示。

**Q：为什么把轨迹存 JSON 而不是拆表？**
轨迹是"一次运行的整体证据"，读取时整体回放；拆表反而复杂。查询需求只有"按简报看"，JSON 足够。

**Q：没有做的是什么？**
多用户/登录、正文抓取、邮件/企微、分布式调度、失败重试队列。这些是明确的非目标。

---

## 七、我改过的 4 处（讲这段最加分）

| 改动 | 文件 | 为什么 |
|---|---|---|
| 轮数可配置（默认 10） | `config.py`、`main.py` | RSS 不稳导致 6 轮不够，写死会频繁失败 |
| SQLite WAL + busy_timeout | `database.py` | 调度线程和请求线程并发写，避免 database is locked |
| RSS 失败重试一次 | `news.py` | 实测 SSL EOF/握手超时，重试一次明显降低失败率 |
| 生成并发锁 + 409 | `digest.py`、`main.py` | 手动点击和定时任务可能撞车，保证同一时刻只跑一个 Agent |

每个改动都有对应测试：`test_config.py`、`test_database.py`、`test_news_tool.py`、`test_digest.py`。

**讲法**："这个项目我先跑通，再针对实际踩到的三个问题做了加固——网络抖动、并发写库、并发触发；每处都补了测试。"

---

## 八、30 秒版本（背这个）

> "这是一个 Function Calling 的新闻 Agent。页面填偏好，服务把身份和话题拼成任务，AgentRunner 带着 6 个工具调模型，模型自己决定搜什么、搜几次、什么时候停。工具结果按 tool_call_id 回填，循环结束前校验正文里的链接必须来自搜索结果。成功后正文和完整轨迹存 SQLite，页面能看到每次运行调了哪些工具；失败也落库。调度器按用户时区每天触发同一套逻辑，飞书推送是可选的。"
