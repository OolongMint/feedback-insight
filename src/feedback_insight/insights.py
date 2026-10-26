"""Grounded summaries and quotes selected from sanitized records only."""
from collections import Counter

from .classify import ModelError
from .models import TOPICS

OPPORTUNITIES = {
    'investigate':'优先回访受影响用户，复现并核查问题；当前证据不足以判断根因。',
    'validate':'进一步访谈并验证需求频率与价值，再决定是否排期。',
    'observe':'继续收集反馈，观察该主题是否持续出现。',
}


def _diverse_rows(rows, limit):
    ordered=sorted(rows,key=lambda r:(-r.severity,r.source_row))
    picked,users,texts=[],set(),set()
    for allow_repeated_text in (False,True):
        for row in ordered:
            if row.user_id=='unknown' or row.user_id in users: continue
            if not allow_repeated_text and row.text in texts: continue
            users.add(row.user_id)
            texts.add(row.text)
            picked.append(row)
            if len(picked)>=limit: return picked
    return picked


def aggregate(rows):
    topics=[]
    for topic in TOPICS:
        members=[r for r in rows if r.topic==topic and not r.quarantined]
        if not members: continue
        sentiments=dict(Counter(r.sentiment for r in members))
        picked=_diverse_rows(members,5)
        sufficient=len(picked)>=2
        quotes=[{'source_row':r.source_row,'text':r.text,'user_id':r.user_id} for r in picked] if sufficient else []
        summary=f'本主题包含 {len(members)} 条反馈，其中负向 {sentiments.get("负向",0)} 条；最高严重度 S{max(r.severity for r in members)}。'
        if not sufficient: summary+=' 数据不足：少于 2 位可识别的不同用户，不生成代表性引文。'
        topics.append({'topic':topic,'count':len(members),'score':sum(r.severity for r in members),'max_severity':max(r.severity for r in members),'sentiments':sentiments,'summary':summary,'quotes':quotes,'sufficient':sufficient,'opportunity':OPPORTUNITIES['investigate' if sentiments.get('负向',0) else 'validate'] if sufficient else OPPORTUNITIES['observe']})
    return sorted(topics,key=lambda t:(-t['score'],-t['count'],t['topic']))


def summarize_live(topics, rows, client):
    if not topics: return topics
    candidates={}
    for topic in topics:
        eligible=[{'source_row':row.source_row,'text':row.text,'user_id':row.user_id} for row in _diverse_rows([r for r in rows if r.topic==topic['topic'] and not r.quarantined],10)]
        candidates[topic['topic']]=eligible
    response=client.complete({'topics':[{'topic':t,'feedback':items} for t,items in candidates.items()]},'summarize')
    if set(response)!={'topics'} or not isinstance(response['topics'],list) or len(response['topics'])!=len(topics): raise ModelError('模型证据选择结构无效')
    selection={}
    for item in response['topics']:
        if not isinstance(item,dict) or set(item)!={'topic','source_rows','opportunity'}: raise ModelError('模型证据选择字段无效')
        name=item['topic']
        if not isinstance(name,str) or name not in candidates or name in selection or not isinstance(item['opportunity'],str) or item['opportunity'] not in OPPORTUNITIES: raise ModelError('模型返回未知主题或机会类型')
        source_ids=item['source_rows']
        allowed={r['source_row']:r for r in candidates[name]}
        if not isinstance(source_ids,list) or any(type(k) is not int or k not in allowed for k in source_ids) or len(source_ids)!=len(set(source_ids)): raise ModelError('模型选择了无效引用行号')
        if len(allowed)>=2 and not 2<=len(source_ids)<=5: raise ModelError('模型引用数量应为2至5条')
        if len(allowed)<2 and source_ids: raise ModelError('证据不足时不得生成引用')
        selection[name]=(source_ids,item['opportunity'])
    for topic in topics:
        ids,opportunity=selection[topic['topic']]
        allowed={r['source_row']:r for r in candidates[topic['topic']]}
        topic['quotes']=[allowed[k] for k in ids]
        topic['opportunity']=OPPORTUNITIES[opportunity] if topic['sufficient'] else OPPORTUNITIES['observe']
    return topics


def verify_citations(topics, rows, labels=None):
    source={r.source_row:r for r in rows}
    label_map={r.source_row:r for r in labels} if labels is not None else None
    total,verified=0,0
    for topic in topics:
        for quote in topic.get('quotes',[]):
            total+=1
            row=source.get(quote.get('source_row'))
            belongs=label_map is None or (quote.get('source_row') in label_map and label_map[quote['source_row']].topic==topic.get('topic') and not label_map[quote['source_row']].quarantined)
            if row and quote.get('text')==row.text and quote.get('user_id')==row.user_id and not row.quarantined and belongs:
                verified+=1
    return {'total':total,'verified':verified,'rate':verified/total if total else None,'passed':verified==total}
