# 独立评估 · 问题与修复记录

日期：2026-10-25。Evaluator 未修改产品源码；仅创建并执行独立探针。

## 发现的问题与复核

| 轮次 | 问题 | 复现证据 | 修复后的检查 |
| --- | --- | --- | --- |
| 第一轮 | 分类协议拒绝严重度 5，与 F02 的 1–5 不一致 | `test_accepts_highest_documented_severity` 初次抛出 ModelError | 已通过 |
| 第一轮 | 缺少 usage 后仍发送第二次付费请求 | `test_unknown_usage_prevents_next_paid_request` 初次未抛异常，stub 接到第二次请求 | 已通过；首请求保守记账，后续请求被阻断 |
| 第二轮扩展复核 | 真实原话归入错误主题，评测仍判通过 | `test_cross_topic_evidence_is_rejected_in_evaluation` 初次取得 passed=true | 已通过；在源文本验真之外，使用预测分类检查主题归属 |

这些问题均在 Generator 初版自测之外由独立 Evaluator 发现，满足“至少发现一处自评遗漏”的流程目标。没有通过人为造错来凑该指标。

## 第三轮最终复核前的扩展验证

`python reports/evaluator-tests/test_independent.py` 已运行 17 项，全部通过。包含真实本地 HTTP 协议的完整流水线测试，不涉及外网模型或付费调用。验证了脱敏后才发送请求、classification/summary 两阶段响应、usage 计账与可追溯输出。

独立运行 300 条合成反馈：有效 300，隔离 4，参与主题聚合 296，二者守恒；引用 30/30 精确匹配；规则步骤耗时约 0.011 秒、调用 0 次、费用 0。该时间不是远程模型性能指标。

对未标注的 `data/golden.csv` 执行 CLI 评测返回 `status=pending`、`passed=false`，并以非零退出，不将未标注模板判为通过。

## 当前验收口径

隔离反馈在总量和明细中保留，单列隔离数量，不参与主题与情绪聚合。守恒式为：有效反馈 = 参与主题聚合反馈 + 隔离反馈。

真实模型准确率、真实模型耗时与费用、人工抽检 20 条及全新会话恢复仍需后续用户数据和人工证据。自动脱敏无法证明所有自由文本姓名均被识别，应先本地审核并提供姓名名单。

浏览器验证由主会话执行，证据位于 `reports/browser/checks.json`：1440/768/390 视口、无外部资源、无 JavaScript 错误，搜索空状态、主题筛选及来源跳转通过。Evaluator 已读取该 JSON；截图视觉检查由主会话承担。
