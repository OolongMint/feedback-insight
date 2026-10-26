# 用户反馈洞察助手协作规则

## 1. 启动与范围
先读 `harness/progress.md`、`harness/feature_list.json`、`docs/PRD.md`、`docs/technical-design.md`。只实现 F01–F06。不增加登录、数据库、多用户、实时接入、模型微调、自动发送报告或后端服务。迁移与开发入口见 `docs/codex-setup.md`。

## 2. 数据边界
Generator 不得读取 `data/golden.csv`、人工标签或评测答案，也不得用黄金集调优提示词。合成演示不证明 GPT 或其他模型的准确率。人工黄金集必须由用户独立填写，36 normal、12 boundary、12 adversarial，并抽检20条。

原始反馈只在本地导入时短暂处理，先脱敏再调用外部模型。报告引用脱敏规范数据，保留原始CSV物理起始行号；不能以“逐字引用”为理由输出PII。姓名、地址等非结构化隐私需用户本地复核，不能声称正则能全部识别。Key只从环境读取，禁止提交、记录或在报错中打印。

这些读取边界和 Evaluator 不修改产品代码的要求属于协作规则，不是操作系统级文件权限隔离。需要强隔离时，主会话应在独立环境中只提供所需材料；不得声称TOML角色定义自动创建了专属只读沙盒。

## 3. 验收
先写有意义的失败测试，再实现。缺少测试证据不能声称通过。无API Key、人工标签、有效价格或真实usage时，相关指标标记待验收，禁止伪造。对抗样本任一失败即不通过。HTML必须离线打开、转义用户输入，不能依赖CDN。引文必须同时验证文字、源行号、用户身份和主题归属。

## 4. Codex 三 Agent 工作流
本项目的三Agent试跑已获用户授权。主会话按 Planner → Generator → Evaluator 编排；子Agent不得再创建子Agent。角色定义在 `.codex/agents/planner.toml`、`generator.toml`、`evaluator.toml`，使用继承的父会话模型，不硬编码模型版本或推理强度。

Planner只规划六个功能并写验收；Generator实现，不修改验收或读取黄金标签；Evaluator独立审阅并运行命令，不修改产品代码。Evaluator确认通过前，主会话不得把功能标为done。每个功能最多3轮返工，超限则向用户报告分歧。当前会话若未加载自定义角色，主会话可用可用的内置角色显式传入同样职责；不能把角色文件存在等同于实际运行过三个Agent。

自定义Agent继承父会话的权限、provider、MCP服务器及skills。角色文件内的行为约束不能替换父会话沙盒；不使用其他客户端的 `tools:` 或 `skills:` YAML配置。后续确需项目技能时，放在 `.agents/skills/<name>/SKILL.md`，本项目当前不要求新增技能。

用户已授权按试跑计划实施。一般可逆实现和本地测试继续推进，无须逐步重复请求批准；真实模型费用和人工标注仍需用户配置/完成，不能代替用户造数据。不得通过迁移修改用户全局配置、账户或信任状态。

## 5. Codex 开发与产品模型调用
Codex登录用于开发协作；Python产品的OpenAI调用使用用户单独配置的 `OPENAI_API_KEY` 和 `--provider openai`。Codex或ChatGPT登录不向产品自动提供API凭证或免费API额度。兼容服务商路径保留 `--provider compatible` 和 `FEEDBACK_*` 环境变量；不要跨provider自动借用另一方凭证。

## 6. 续航与复盘
每轮更新 `harness/progress.md`，记录命令、实际结果、失败原因、返工轮次、人工介入和待办。`done`表示工程验收通过，不表示真实模型的产品指标已通过。复盘见 `reports/retrospective.md`。
