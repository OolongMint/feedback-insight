"""Evaluation is isolated from generator and never trains on golden labels."""
import csv
import json
import random
from collections import Counter
from pathlib import Path

from .models import TOPICS, SENTIMENTS, Feedback
from .insights import verify_citations


def evaluate(predictions, topics, golden_path, source_rows, metadata=None):
    metadata=metadata or {}
    result={'status':'failed','passed':False,'thresholds':{'topic_accuracy':0.8,'severity_within_one':0.7,'citation_rate':1.0},'metadata':metadata,'issues':[]}
    source={r.source_row:r for r in source_rows}
    predicted={r.source_row:r for r in predictions}
    citation=verify_citations(topics,source_rows,labels=predictions)
    result['citation_check']=citation
    if len(source)!=len(source_rows) or len(predicted)!=len(predictions) or set(source)!=set(predicted): result['issues'].append('源记录与预测行号必须完整且唯一匹配')
    if not citation['passed']: result['issues'].append('引用无法在脱敏源数据中逐字找到')
    try:
        with Path(golden_path).open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            required={'source_row','topic','sentiment','severity','group','reviewed'}
            if not required<=set(reader.fieldnames or []): raise ValueError('黄金集缺少必要字段')
            golden=list(reader)
    except (OSError,csv.Error,UnicodeError,ValueError):
        result.update(status='pending')
        result['issues'].append('无法读取完整黄金集；请先准备人工标注文件')
        return result
    pending=any(any(not (g.get(k) or '').strip() for k in ('topic','sentiment','severity')) or (g.get('reviewed') or '').strip().lower() not in ('true','1','yes') for g in golden)
    if pending:
        result.update(status='pending',golden_count=len(golden))
        result['issues'].append('黄金集尚未由人工完成标注并确认 reviewed=true，不能判定通过')
        return result
    if len(golden)!=60: result['issues'].append('黄金集必须恰好为60条')
    groups=Counter((g.get('group') or '').strip() for g in golden)
    result['groups']=dict(groups)
    if groups!={'normal':36,'boundary':12,'adversarial':12}: result['issues'].append('黄金集分组必须为normal=36、boundary=12、adversarial=12')
    gold_ids=set()
    comparisons=[]
    adversarial_failures=[]
    for g in golden:
        try:
            row_id=int(g['source_row'])
            severity=int(g['severity'])
            if row_id in gold_ids or row_id not in source or row_id not in predicted: raise ValueError()
            if g['topic'] not in TOPICS or g['sentiment'] not in SENTIMENTS or not 1<=severity<=5: raise ValueError()
            row=predicted[row_id]
            if row.topic not in TOPICS or row.sentiment not in SENTIMENTS or type(row.severity) is not int or not 1<=row.severity<=5: raise ValueError()
            gold_ids.add(row_id)
            topic_ok=row.topic==g['topic']
            severity_ok=abs(row.severity-severity)<=1
            sentiment_ok=row.sentiment==g['sentiment']
            comparisons.append({'source_row':row_id,'group':g['group'],'topic_correct':topic_ok,'severity_within_one':severity_ok,'sentiment_correct':sentiment_ok,'expected':{'topic':g['topic'],'sentiment':g['sentiment'],'severity':severity},'predicted':{'topic':row.topic,'sentiment':row.sentiment,'severity':row.severity}})
            injected=(g.get('injection_success') or '').strip().lower() in ('true','1','yes')
            if g['group']=='adversarial' and (not topic_ok or row.severity!=severity or injected): adversarial_failures.append(row_id)
        except (ValueError,TypeError,KeyError): result['issues'].append('黄金集存在无效标签、重复行号或缺失预测')
    count=len(comparisons)
    metrics={
        'topic_accuracy':sum(c['topic_correct'] for c in comparisons)/count if count else None,
        'severity_within_one':sum(c['severity_within_one'] for c in comparisons)/count if count else None,
        'sentiment_accuracy':sum(c['sentiment_correct'] for c in comparisons)/count if count else None,
    }
    if count!=60: result['issues'].append('有效评测样本不足60条')
    if metrics['topic_accuracy'] is None or metrics['topic_accuracy']<.8: result['issues'].append('主题准确率未达到80%')
    if metrics['severity_within_one'] is None or metrics['severity_within_one']<.7: result['issues'].append('严重度一致率未达到70%')
    if adversarial_failures: result['issues'].append('对抗样本失败，触发一票否决')
    if metadata.get('elapsed_seconds',0)>300: result['issues'].append('运行时间超过300秒')
    if metadata.get('mode')=='live' and (metadata.get('cost_cny') is None or metadata.get('usage_estimated')): result['issues'].append('真实费用未知，不能完成费用验收')
    if metadata.get('mode')=='live' and metadata.get('budget_cny') is not None and metadata.get('cost_cny',0)>metadata['budget_cny']: result['issues'].append('运行费用超出预算')
    result.update(metrics=metrics,golden_count=len(golden),evaluated_count=count,comparisons=comparisons,adversarial_failures=adversarial_failures,manual_spotcheck_rows=random.Random(20261025).sample(sorted(gold_ids),min(20,len(gold_ids))),injection_note='自动检测仅验证标签/结构；请人工抽检提示词注入是否改变行为，并填写 injection_success。')
    result['passed']=not result['issues']
    result['status']='passed' if result['passed'] else 'failed'
    if metadata.get('mode')=='demo': result['quality_scope']='规则基线评测；不能代表真实模型质量'
    return result


def load_sanitized(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        required={'source_row','text','date','channel','user_id'}
        if not required<=set(reader.fieldnames or []): raise ValueError('评测输入必须为程序生成的 sanitized.csv')
        rows=[]
        for item in reader:
            rows.append(Feedback(int(item['source_row']),item['text'],item['date'],item['channel'],item['user_id']))
        return rows


def load_analysis(path):
    try:
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        rows=[Feedback(**item) for item in data['rows']]
        return rows,data['topics'],data.get('metadata',{})
    except (OSError,ValueError,TypeError,KeyError): raise ValueError('预测文件结构无效') from None
