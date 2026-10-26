# Codex GPT 迁移独立验收

日期：2026-10-25。判定：本轮配置、说明与 OpenAI provider 运行接口的工程验收通过，未发现阻塞项。未读取 `data/golden.csv`，未修改产品代码、配置或 Word 文档，未调用真实收费模型。

## 实际执行证据

- `python -m unittest discover -s tests -v`：最终 30/30 通过，其中 8 项新增测试覆盖 OpenAI provider、3 项覆盖报告发布；Windows DACL 回归在本机实际执行，未跳过。
- `python reports/evaluator-tests/test_independent.py`：17/17 通过。
- `python -m compileall -q src tests`：退出码 0。
- Python `tomllib` 校验 `.codex/config.toml` 与三份角色 TOML：通过。项目配置仅含 `agents.enabled=true`、`agents.max_concurrent_threads_per_session=3`；每份角色仅含 `name`、`description`、`developer_instructions`，名称与角色一致。
- `codex --version`：本机为 `codex-cli 0.164.0-alpha.11.1`；`codex features list` 显示 `multi_agent stable true`。未据此声称当前会话已重新加载新增自定义角色。
- `python -m src.feedback_insight analyze --help`：存在 `--provider {compatible,openai}`、token/预算/脱敏等参数，与 README 和 Word 运行示例一致。
- 原位更新的 DOCX ZIP 完整性检查通过，原始备份存在；正文不再含旧平台文件路径、客户端名及原计划所依赖的特定第三方工作流名称。

## 核对结果

| 核对项 | 结果 |
| --- | --- |
| 持久项目规则 | `AGENTS.md` 已替代旧规则文件；旧文件与三份旧 Markdown 角色文件已删除。 |
| 自定义角色 | `.codex/agents/*.toml` 使用当前 standalone 角色格式；没有固定模型或推理强度、没有无效 YAML 工具列表、没有伪造独立沙盒配置。 |
| Skill 与权限说明 | 文档一致说明继承父会话配置；禁读黄金标签与独立评审属于协作要求，不能当作操作系统 ACL。 |
| OpenAI 默认路由 | `--provider openai` 默认使用官方 API 地址，仅读取 `OPENAI_API_KEY` 与显式模型或 `OPENAI_MODEL`，忽略兼容 provider 的环境配置。 |
| 兼容 provider | 保持原有 `FEEDBACK_*` 契约，默认 provider 仍为 compatible。OpenAI 与 compatible 的 Key 均无跨 provider 自动回退。 |
| GPT 请求适配 | 默认请求不再附带 `temperature`，保留 `max_completion_tokens`、JSON 输出与本地结构校验；未对账号可用型号或所有 GPT 兼容性作无依据承诺。 |
| 本地协议完整验证 | 新增本地 HTTP 测试执行两次模型协议请求，检查授权 Key 选择、仅脱敏文本外发、usage/人民币费用、引文校验和报告中的模型名转义。 |
| 演示与真实质量区分 | demo 的 metadata 为 provider=local、model=local-rules，报告明确规则演示；没有将本地模拟或规则运行当作 GPT 效果证据。 |
| 登录与计费 | 说明明确区分 Codex 开发登录、Python 产品 API Key 和计费路径，不假称自动共享免费 API 额度。 |
| 活跃文档残留 | AGENTS、README、docs、harness 与项目 `.codex` 活跃 Markdown/TOML 无旧平台名称或旧文件路径。解释“不沿用 tools:/skills: YAML”的文字不是遗留配置。历史原始 DOCX 只在归档备份中保留。 |
| Word 文本与运行命令 | 已核对 AGENTS、TOML 角色路径、`codex --version`、`codex login status`、`OPENAI_API_KEY`、`OPENAI_MODEL` 与 `--provider openai` 示例；未参与版面渲染，视觉验收由主会话完成。 |

## 报告发布权限修复末轮复核

主会话在迁移后的默认演示重跑中发现旧文件访问权限问题，根因记录见 `publication-debug.md`。`TemporaryDirectory` 内文件直接移动到输出目录时，在 Windows 上会保留私有 DACL；这为先前的 `ERR_ACCESS_DENIED` 提供了具体文件权限原因，不能仅归因于内置浏览器限制。

独立复核确认，修复仍先在私有暂存中生成并校验完整结果，再通过目标目录中普通 `open('xb')` 创建的临时兄弟文件复制完整内容，最后做同目录替换并清理临时文件。产品代码没有调用 `icacls`、重写系统权限或放宽全局规则。实际测试验证新报告 DACL 与同目录普通文件相同、复制失败不改旧报告、首次替换失败不留临时文件。

最终独立重跑 30 项产品测试和 17 项探针，共 **47 项全部通过**，`compileall` 再次成功。另用 `Get-Acl` 与读取操作确认默认 `reports/demo/report.html` 已启用继承规则且当前宿主可读。主会话已重跑默认300条演示及三种尺寸浏览器检查；本次独立读取 `reports/browser/checks.json` 确认结果为通过、无远程资源、无JS错误，搜索空状态/筛选/来源跳转通过。

发布目前是逐文件替换，不应描述成整个三文件目录级原子事务；该限制不阻塞本轮 Windows ACL 修复与平台迁移。原来无法读取的三个合成报告由主会话保留在旧目录，未删除源数据或人工标签。

文档最终记录 `docx-check.json` 显示使用 Microsoft Word 16 COM 与 bundled Poppler 渲染9页，主会话已逐页视觉检查并标记通过；Evaluator核对了该记录，没有将自己的文本检查冒称为视觉验收。

## 保留边界

真实 GPT API 可用性、模型质量、实际费用、60 条人工标签、20 条人工抽检和全新会话恢复仍需用户配置及相应验证。本轮只证明迁移后的工程接口与离线/本地模拟验证通过。角色文件需由支持该格式的 Codex 新会话发现；本次没有为此修改用户全局配置、认证或信任状态。

普通执行工具的环境刷新故障发生在创建进程之前，未将其当成测试失败或自动审批拒绝。所有上述验收实际通过经审核的项目内只读检查或本地模拟测试执行。
