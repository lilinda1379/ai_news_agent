# 工作区说明

这个目录是 Agent 的文件工作区，模型可以通过 `list_dir` / `read_file` / `search_content` / `write_file` / `bash` 访问。

- `seed/`：预置资料，模拟"长期积累的知识库"。
  - `history_2026-10-26.md`：昨天的简报，用来避免今天重复。
  - `editorial_rules.md`：编辑规则（来源、条数、去重）。
  - `topics.md`：长期关注话题与屏蔽词。
- `digests/`：Agent 每天生成的简报会写到这里。

约定：所有路径都是相对本目录的，不要使用绝对路径。
