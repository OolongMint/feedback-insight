# 项目续航状态

更新时间：2026-10-25（Asia/Shanghai）。

## 当前目标
用户批准的深色正式报告改版已完成并独立验收：纵向阅读、紧凑统计与主题汇总、默认两条原话、打印浅色与浏览状态恢复。真实模型指标仍待人工验证。

## 已完成
- 读取原始需求，范围限定为 F01–F06。
- Planner 写完需求分析、PRD、技术设计和6项验收；独立 Evaluator 已确认标准。
- 已生成300条合成演示数据、60条未标注黄金模板（36/12/12）。
- Generator 已先运行11项失败测试后开始实现。
- 建立 `AGENTS.md`、Codex三个TOML角色定义及README。

## 最终工程验收：通过
- F01–F06 均经独立Evaluator确认工程通过，主会话已将 feature_list.json 标done；此状态不代表真实模型产品指标已通过。
- 最终自测19/19、独立探针17/17全部通过；`compileall` 和CLI帮助可用。
- 300条合成反馈完整跑通：296条参与聚合，4条隔离；6个主题、30/30引文逐字通过，规则管线约0.009秒（非真实模型性能）。
- `reports/demo/report.html`、`analysis.json`、`sanitized.csv` 已生成，明确标记规则演示和合成数据。
- 空白黄金集评测状态pending，退出码2，未误报通过；见 `reports/evaluation.json`。
- Chrome实际验证1440/768/390宽度，未见页面横向溢出、远程资源或JS错误；搜索无结果状态、主题筛选、原话跳转正常。证据 `reports/browser/checks.json` 与三张PNG；主会话已查看桌面和手机截图。
- 最终独立验收 `reports/review-final.md`，主会话复核记录 `reports/verification.json`，复盘 `reports/retrospective.md`。

## 返工轮次与独立发现
- 第1轮发现F02严重度范围和未知usage后继续调用；第2轮发现F04/F06跨主题引用误通过；第3轮最终复核通过。
- 3个问题均已复现并有回归测试，没有任何功能超过3轮。每个受影响功能1轮实现返工。
- 本地HTTP模拟验证完整live协议、外发脱敏、usage记账、预算拦截、缺usage停止及失败保留既有报告；真实外网模型调用0。

## 恢复方式
1. 读取 `AGENTS.md`、此文件、feature_list.json、docs/PRD.md；Codex已有会话可用 `codex resume`，新会话按状态恢复。
2. 查看 reports/review-*.md，优先处理独立审查的阻塞项。
3. 运行 `python -m unittest discover -s tests -v` 和 `python reports/evaluator-tests/test_independent.py`。
4. 运行 `python -m src.feedback_insight demo --input data/feedback.csv --output reports/demo`。
5. 六项工程功能已经done。下一步仅推进人工标注和真实模型验收，不重复构建产品；新增功能先与用户确定范围。

## 人工待办
- 独立填写60条黄金标签；禁止Generator读取。
- 随机抽检20条，记录Evaluator误判。
- 配置自己的模型Key、服务地址、模型ID、人民币单价和预算，再跑真实模型验收。

## 流程记录
- 人工介入：仅初始实现授权，暂无中途提问。
- 真实模型调用：0；实际模型费用：0。
- 范围决策：Python产品不依赖编码客户端或外部skill；开发使用Codex，角色配置保存在 `.codex/agents/`。

## Codex 与 GPT 迁移记录
- 根据用户后续授权，将持久规则迁移到 `AGENTS.md`，角色迁移到 `.codex/agents/planner.toml`、`generator.toml`、`evaluator.toml`，删除旧平台规则文件。
- 项目 `.codex/config.toml`仅开启子Agent及最多3个并发子Agent，不修改全局配置、登录或信任设置；角色模型与skills继承父会话。
- 新增 `docs/codex-setup.md`，明确版本/登录检查、启动提示词、会话恢复、角色行为边界。
- OpenAI产品入口为 `--provider openai`、`OPENAI_API_KEY`、官方默认地址；兼容入口继续保留 `FEEDBACK_*`。产品API与Codex登录分别配置，不共享免费额度。
- 原始Word计划由主会话原位迁移，并在 `docs/archive/原始试跑计划.docx` 保留备份；最终迁移测试和文档渲染由主会话补充证据。

## Codex GPT 迁移最终验收
- 独立复核通过：30项产品测试、17项独立探针，共47项通过；`compileall`成功。实际命令日志和结果见 `reports/codex-migration/verification.json`、`review.md`。
- 新增OpenAI入口、按provider隔离的凭证读取、服务和模型元数据；不预置GPT型号。协议验证使用本地HTTP模拟，真实付费调用0。
- Word原文件已更新并保留6张表格；阶段表改为4列避免跨页断句。用本机Word导出、Poppler渲染，9页逐页查看通过。记录 `reports/codex-migration/docx-check.json`，原稿备份不变。
- 修复Windows私有暂存文件移动后保留限制DACL的问题，真实Windows回归先红后绿。新报告继承最终目录权限，宿主可读；旧演示文件保留在 `reports/.legacy-demo-sandbox`，没有删除。
- 默认 `reports/demo` 已重新生成：300条合成反馈，296聚合+4隔离，6主题，30/30引文匹配；`provider=local`。浏览器1440/768/390及交互检查通过，HTTP预览响应200。
- 当前普通shell遇到 `helper_unknown_error: setup refresh had errors`；最终本地检查已通过获准的宿主进程执行。这是工具启动环境问题，不是产品失败。未修改全局Codex配置或账户；新角色需在新会话加载。

## 深色报告改版恢复记录 2026-10-26
- 用户已授权按确认方案实施。Planner写好17条补充标准 `harness/acceptance/F05-dark-report.md`，已由独立Evaluator确认。
- 上轮工具自动审批因账户额度耗尽未能完成，工作中断。已保存新版report.py、report.js、6项产品测试和7项独立探针；report.css尚未写入，不能将当前改版判为完成。
- 主会话恢复实跑36项产品测试：1失败、16错误，主要根因为缺少样式资源；Generator继续补齐，Evaluator独立复核。浏览器验收脚本已补折叠、键盘、筛选、来源跳转、真实打印与精确状态恢复。
- 本轮证据写入 `reports/report-redesign/`。普通shell启动刷新问题仍存在，使用获准的宿主进程执行本地检查，不读取真实凭证、不调用付费模型。

## 深色报告改版最终验收 2026-10-26
- Generator补齐缺失的report.css；主会话及独立Evaluator实跑36项产品测试、17项基础独立探针、7项报告独立探针，共60项全部通过；compileall通过。
- 主报告实际Chrome检查1440/768/390宽度，确认深色、15/26px字体、无侧栏、无页面横向溢出、两条原话和原生折叠、键盘、筛选、主题与来源跳转正常。
- 重复beforeprint、无准备afterprint、真实浏览器打印前后精确恢复均通过；打印使用白底黑字。16页PDF逐一检出300条源行和30条代表性引文；主会话查看第1、2、4、5、16页及三种屏幕截图。
- 长反馈/渠道/用户代号/模型名合成边界fixture的三种宽度与打印通过；空报告1440/390实际浏览器通过。Evaluator查看了边界截图和长内容打印代表页。
- 浏览器探针初次键盘检查失败，根因为模拟Enter缺少字符事件；修复测试驱动事件后通过，产品原生details不需变更。未修改验收标准迁就实现。
- 独立最终判定见 `reports/report-redesign/review.md`，汇总证据 `verification.json`，浏览器证据 `reports/browser/checks.json`。默认演示已重新生成，http://127.0.0.1:8765/report.html返回200且为新版。
- 本轮仅改变F05呈现，保留CLI与分析格式，未读取人工标签或调用付费模型。Word计划无需因界面改版重新生成。

## GitHub 同步 2026-10-26
- 用户明确选择在OolongMint账号下新建私有仓库 `feedback-insight`。本地Git已初始化为main，并关联 https://github.com/OolongMint/feedback-insight.git 的origin/main。
- 首次代码提交 `18ccca7` 已推送，远程默认分支main、仓库PRIVATE、非空，本地与远程SHA一致。
- 提交前实跑36项产品测试+17项基础独立探针+7项报告探针，共60项全部通过；67份提交文件约648KB，暂存内容的密钥特征检查无匹配。
- 已确认样例反馈为合成数据、golden.csv为未标注模板；排除真实数据目录、环境密钥、本地Codex认证与会话、临时PDF/截图/日志/浏览器配置和旧沙盒输出。保留源码、配置、Word计划与备份、README预览图、合成演示及独立验收证据。
- 本轮仅创建项目本地Git和用户确认的私有仓库，没有修改全局Git/Codex配置或运行真实模型；README补充克隆和后续同步命令。
