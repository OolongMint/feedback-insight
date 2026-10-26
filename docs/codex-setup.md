# Codex 开发与 GPT 调用配置

## 两种用途
Codex用于规划、实现和独立评估项目；Python命令用于分析反馈并生成报告。前者使用当前Codex账户，后者调用OpenAI API时需要单独配置 `OPENAI_API_KEY`。ChatGPT或Codex登录不自动给Python程序提供API凭证或免费额度。

## 检查和启动 Codex
在项目目录运行：

```powershell
codex --version
codex login status
```

需要登录时运行 `codex login` 并完成交互登录。然后在Codex桌面应用中打开项目目录，或在该目录运行 `codex`。不需要安装其他编码客户端；只运行本地规则演示时甚至不需要Codex。

Codex会发现根目录 `AGENTS.md`；本项目用 `.codex/agents/*.toml` 定义Planner、Generator、Evaluator。每个角色包含 `name`、`description`、`developer_instructions`。`.codex/config.toml` 开启子Agent，最多同时3个子Agent，主会话不计入该上限。不指定模型，继承父会话当前可用的模型与推理设置。

当前Codex版本会继承父会话的权限、provider、MCP服务器和skills。角色文件不能通过 `sandbox_mode` 或工具名称列表创建独立权限边界。Generator禁读黄金集、Evaluator不改源码的要求是协作约束；需要强隔离时应由环境提供相应权限控制。

项目skills如有需要使用 `.agents/skills/<name>/SKILL.md`。目前没有新增skill依赖，不要求安装额外工作流或浏览器插件；浏览器辅助验证使用现有的 `scripts/check_browser.mjs`。

## 启动提示词

```text
读取 AGENTS.md、harness/progress.md 和 harness/feature_list.json。
按项目的 Planner、Generator、Evaluator 三Agent职责继续工作。
六项工程功能已经通过时，不重复构建；先核对最新状态及待验收事项。
新增功能先由Planner拆分范围；Generator先写失败测试；Evaluator独立运行验收。
子Agent不得创建子Agent，Generator不得读取人工黄金标签。
不得把规则演示或本地HTTP模拟当作真实GPT模型质量验收。
每个功能最多3轮返工；主会话记录证据并负责最终状态。
```

如果刚新增角色文件，重启Codex会话后再使用角色。若当前客户端尚未提供自定义角色，可以由主会话调用内置角色并显式传入同样职责，保留各自独立的输出和验收证据；不能把一段自评当作独立Evaluator。

## 恢复工作
从项目目录运行 `codex resume` 选择已有会话，或在桌面应用中重新打开本项目的聊天。新会话先读取 `AGENTS.md` 和 `harness/progress.md`。状态文件是恢复依据；是否真的关闭并重开会话验证过，需要另行记录，不能从文件存在推断。

## 配置 OpenAI API

```powershell
$env:OPENAI_API_KEY = '在当前会话设置你的API Key'
python -m src.feedback_insight analyze --provider openai `
  --input data/private/feedback.csv --output reports/private/openai `
  --model '你的GPT模型ID' --budget 2 --input-price 1 --output-price 4
Remove-Item Env:OPENAI_API_KEY
```

`--provider openai` 使用OpenAI官方默认地址 `https://api.openai.com/v1`，仍使用Chat Completions协议。模型必须是账户有权调用、支持该协议及参数的模型。这里不指定固定版本，不会因迁移自动发起付费测试。

价格单位为人民币/百万token；示例数字仅为参数用法，不是模型报价。若服务商报价以其他货币表示，需用户先按自己确认的汇率换算为人民币，再传入输入和输出单价。预算单位同为人民币元，程序按实际usage计账，并在请求前预留费用。

兼容服务商使用 `--provider compatible`，显式配置服务商地址，继续使用 `FEEDBACK_API_KEY`、`FEEDBACK_BASE_URL`、`FEEDBACK_MODEL`。两种provider的凭证互不自动借用。

## 参考
- [Codex 项目规则 AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Codex 子Agent与TOML角色](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Codex 技能发现与配置](https://learn.chatgpt.com/docs/build-skills)
- [OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
