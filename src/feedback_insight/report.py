"""Render a self-contained report; source data never enters executable code."""
from html import escape
from pathlib import Path


def _text(value):
    return escape(str(value), quote=True)


def _severity(value):
    return f'<span class="severity s{_text(value)}">S{_text(value)}</span>'


def _quote(quote):
    return (
        '<blockquote><p>' + _text(quote['text']) + '</p><footer class="quote-source">'
        f'<a href="#source-{_text(quote["source_row"])}">源文件第 {_text(quote["source_row"])} 行</a>'
        f'<span>用户 {_text(quote["user_id"])}</span></footer></blockquote>'
    )


def _topic_section(index, topic):
    quotes = topic.get('quotes', [])
    evidence = ''.join(_quote(quote) for quote in quotes[:2])
    if len(quotes) > 2:
        evidence += (
            '<details class="quote-overflow">'
            f'<summary>查看其余 {len(quotes) - 2} 条原话</summary>'
            '<div class="remaining-quotes">' + ''.join(_quote(quote) for quote in quotes[2:]) + '</div></details>'
        )
    if not quotes:
        evidence = '<p class="insufficient">数据不足：缺少来自至少两位已知用户的独立证据。</p>'
    return f'''<article class="topic-analysis" id="topic-{index}">
  <header class="topic-heading"><h3><span class="section-number">{index + 1:02d}</span>{_text(topic['topic'])}</h3><span class="severity-label">最高严重度 {_severity(topic['max_severity'])}</span></header>
  <p class="topic-summary">{_text(topic['summary'])}</p>
  <div class="evidence"><h4>代表性原话</h4>{evidence}</div>
  <div class="opportunity"><h4>待验证方向</h4><p>{_text(topic['opportunity'])}</p></div>
</article>'''


def _feedback_row(row):
    quarantine = '<span class="quarantine">疑似指令，已隔离</span>' if row.get('quarantined') else ''
    return f'''<tr id="source-{_text(row['source_row'])}" data-topic="{_text(row['topic'])}" data-sentiment="{_text(row['sentiment'])}">
  <td class="numeric source-number"><a href="#source-{_text(row['source_row'])}">{_text(row['source_row'])}</a></td>
  <td class="feedback-text">{_text(row['text'])}</td>
  <td class="feedback-topic">{_text(row['topic'])}{quarantine}</td>
  <td>{_text(row['sentiment'])}</td><td>{_severity(row['severity'])}</td>
  <td class="date-cell">{_text(row['date'])}</td><td class="channel-cell">{_text(row['channel'])}</td>
</tr>'''


def render_report(report):
    """Keep the original input/output contract and inline local CSS/JS assets."""
    rows, topics, metadata = report['rows'], report['topics'], report['metadata']
    is_demo = metadata.get('mode') == 'demo'
    mode = '规则演示 · 非模型效果' if is_demo else '模型分析'
    provenance = '合成数据' if metadata.get('synthetic') else '用户提供数据'
    dates = sorted(str(row['date']) for row in rows if row.get('date'))
    date_range = f'{dates[0]} 至 {dates[-1]}' if dates else '暂无日期'
    negative = sum(row['sentiment'] == '负向' and not row.get('quarantined') for row in rows)
    critical = sum(row['severity'] >= 3 and not row.get('quarantined') for row in rows)
    quarantine = sum(bool(row.get('quarantined')) for row in rows)
    topic_rows = ''.join(
        f'<tr><th scope="row"><a href="#topic-{index}">{_text(topic["topic"])}</a></th>'
        f'<td class="numeric">{topic["count"]}</td><td class="numeric">{topic["sentiments"].get("负向", 0)}</td>'
        f'<td>{_severity(topic["max_severity"])}</td><td class="numeric">{topic["score"]}</td></tr>'
        for index, topic in enumerate(topics)
    )
    if not topic_rows:
        topic_rows = '<tr><td colspan="5" class="empty-state">暂无可分析主题。</td></tr>'
    analyses = ''.join(_topic_section(index, topic) for index, topic in enumerate(topics))
    if not analyses:
        analyses = '<p class="empty-state">暂无有效反馈可供主题分析；请检查输入数据或隔离记录。</p>'
    feedback_rows = ''.join(_feedback_row(row) for row in rows)
    options = ''.join(f'<option>{_text(topic)}</option>' for topic in sorted({row['topic'] for row in rows}))
    cost = metadata.get('cost_cny')
    cost_text = '未知' if cost is None else f'¥{cost:.4f}'
    if metadata.get('usage_estimated'):
        cost_text += '（保守估算）'
    provider = {'openai': 'OpenAI', 'compatible': '兼容 API', 'local': '本地规则'}.get(metadata.get('provider'), '未记录')
    model_information = '本地规则，零模型调用' if is_demo else f'{provider} · {metadata.get("model", "未记录")}'
    citation_status = '已通过逐字与主题归属校验' if report.get('citation_check', {}).get('passed') else '按脱敏明细源行号展示'
    assets = Path(__file__).resolve().parent
    stylesheet = (assets / 'report.css').read_text(encoding='utf-8')
    script = (assets / 'report.js').read_text(encoding='utf-8')
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>用户反馈分析报告</title><style>{stylesheet}</style></head>
<body><main class="report">
<header class="report-header">
  <div class="report-title"><h1>用户反馈分析报告</h1><p class="date-range">反馈日期：{_text(date_range)}</p></div>
  <button type="button" class="print-button" id="print-report">打印 / 另存为 PDF</button>
  <div class="report-status" aria-label="报告来源和分析状态"><span>{_text(provenance)}</span><span>{_text(mode)}</span><span>质量待人工验收</span></div>
</header>
<section class="overview" aria-label="反馈概览"><dl class="metrics">
  <div class="metric"><dt>有效反馈</dt><dd>{len(rows)}<small>条</small></dd></div>
  <div class="metric"><dt>关注主题</dt><dd>{len(topics)}<small>个</small></dd></div>
  <div class="metric"><dt>负向反馈</dt><dd>{negative}<small>条</small></dd></div>
  <div class="metric"><dt>高优先级反馈</dt><dd>{critical}<small>条 · S3–S5</small></dd></div>
</dl><p class="overview-note">无效记录 {metadata.get('rejected_rows', 0)} 条；疑似指令隔离 {quarantine} 条，不参与主题与情绪统计。</p></section>
<section class="report-section" aria-labelledby="topics-heading"><div class="section-heading"><h2 id="topics-heading">主题汇总</h2><p>按严重度总分排序</p></div>
<div class="table-wrap" tabindex="0" role="region" aria-label="主题汇总表"><table id="topic-overview"><thead><tr><th scope="col">主题</th><th scope="col" class="numeric">反馈数</th><th scope="col" class="numeric">负向数</th><th scope="col">最高严重度</th><th scope="col" class="numeric">优先级得分</th></tr></thead><tbody>{topic_rows}</tbody></table></div>
<p class="section-note">优先级得分为主题内严重度之和；点击主题查看分析。S1 一般 · S2 困扰 · S3 受阻 · S4 阻塞 · S5 损失。</p></section>
<section class="report-section" aria-labelledby="analysis-heading"><div class="section-heading"><h2 id="analysis-heading">主题分析</h2><p>摘要、证据与后续核查方向</p></div>{analyses}</section>
<section class="report-section" aria-labelledby="feedback-heading"><div class="section-heading feedback-heading"><div><h2 id="feedback-heading">反馈明细</h2><p id="result-count">显示 {len(rows)} / {len(rows)} 条 · 已脱敏</p></div>
<div class="filters"><label>搜索反馈<input id="search" type="search" placeholder="输入反馈关键词"></label><label>主题<select id="topic-filter"><option value="">全部主题</option>{options}</select></label><label>情绪<select id="sentiment-filter"><option value="">全部情绪</option><option>负向</option><option>中性</option><option>正向</option></select></label></div></div>
<div class="table-wrap feedback-table-wrap" tabindex="0" role="region" aria-label="脱敏反馈明细表"><table class="feedback-table"><thead><tr><th scope="col" class="numeric">源行号</th><th scope="col">反馈原话（脱敏）</th><th scope="col">主题</th><th scope="col">情绪</th><th scope="col">严重度</th><th scope="col">日期</th><th scope="col">渠道</th></tr></thead><tbody id="feedback-rows">{feedback_rows}</tbody></table></div>
<p class="empty-state" id="no-results"{' hidden' if rows else ''}>没有匹配的反馈，请调整筛选条件。</p></section>
<section class="report-section methodology" aria-labelledby="method-heading"><div class="section-heading"><h2 id="method-heading">分析方法与运行信息</h2></div>
<dl class="run-information"><div><dt>分析方式</dt><dd>{_text(model_information)}</dd></div><div><dt>运行耗时</dt><dd>{metadata.get('elapsed_seconds', 0):.2f} 秒</dd></div><div><dt>调用费用</dt><dd>{_text(cost_text)}</dd></div><div><dt>引文核查</dt><dd>{_text(citation_status)}</dd></div></dl>
<p>统计数字由程序计算；原话来自脱敏明细，行号对应原 CSV 记录的物理起始行。用户代号为不可逆摘要，缺失身份不假定为不同用户。待验证方向不表示已证实的原因或解决方案。</p>
<p>{'合成数据不代表真实用户反馈，规则演示不代表模型准确率。' if metadata.get('synthetic') else '数据由用户提供，未声明为合成数据。'} {'真实模型准确率尚需人工黄金集与抽检确认。' if not is_demo else '真实模型质量需另行使用人工黄金集评测。'}自动脱敏不能识别全部自由文本隐私，真实调用前需本地复核。</p>
</section><footer class="report-footer">本地分析报告 · 全部内容可离线阅读</footer>
</main><script>{script}</script></body></html>'''
