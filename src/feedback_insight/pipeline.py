import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from .ingest import load_feedback, write_sanitized
from .classify import classify_demo, classify_live, ModelError
from .insights import aggregate, summarize_live, verify_citations
from .report import render_report


def run(input_path, output_path, *, mode='demo', client=None, names=(), synthetic=False):
    started=time.monotonic()
    if mode not in ('demo','live'): raise ValueError('mode 必须是 demo 或 live')
    output=Path(output_path)
    if Path(input_path).resolve() in [(output/name).resolve() for name in ('analysis.json','sanitized.csv','report.html')]: raise ValueError('输出路径不能覆盖输入文件')
    rows,stats=load_feedback(input_path,names)
    if not rows: raise ValueError('CSV 没有有效反馈，请检查文本、日期和长度')
    if mode=='live' and client is None: raise ValueError('live 模式缺少模型配置')
    labeled=classify_demo(rows) if mode=='demo' else classify_live(rows,client)
    topics=aggregate(labeled)
    if mode=='live': topics=summarize_live(topics,labeled,client)
    aggregated_rows=sum(topic['count'] for topic in topics)
    if aggregated_rows+stats['quarantined_rows']!=len(rows): raise ValueError('主题计数与隔离计数不守恒')
    stats['aggregated_rows']=aggregated_rows
    check=verify_citations(topics,rows,labels=labeled)
    if not check['passed']: raise ModelError('原话引用校验失败，不发布报告')
    metadata={**stats,'mode':mode,'elapsed_seconds':time.monotonic()-started,'cost_cny':client.cost if client else 0.0,'model':client.model if client else 'local-rules','calls':client.calls if client else 0,'prompt_tokens':client.prompt_tokens if client else 0,'completion_tokens':client.completion_tokens if client else 0,'usage_estimated':client.usage_estimated if client else False,'budget_cny':client.budget if client else 0,'source_name':Path(input_path).name,'quality_status':'待人工黄金集验收'}
    # Avoid persisting user-chosen input file names that may contain PII.
    metadata.pop('source_name')
    metadata['provider']=client.provider if client else 'local'
    metadata['synthetic']=bool(synthetic)
    result={'schema_version':1,'metadata':metadata,'rows':[r.to_dict() for r in labeled],'topics':topics,'citation_check':check}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.feedback-staging-',dir=output.parent) as staging:
        stage=Path(staging)
        write_sanitized(stage/'sanitized.csv',rows)
        (stage/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        (stage/'report.html').write_text(render_report(result),encoding='utf-8')
        output.mkdir(parents=True,exist_ok=True)
        prepared=[]
        try:
            for name in ('sanitized.csv','analysis.json','report.html'):
                # TemporaryDirectory uses a private Windows ACL. Moving those
                # files retains it, preventing the desktop user's browser from
                # reading them. Ordinary sibling files inherit the output ACL.
                sibling=output/('.'+name+'.'+uuid4().hex+'.tmp')
                with sibling.open('xb') as destination:
                    prepared.append((sibling,output/name))
                    with (stage/name).open('rb') as source:
                        shutil.copyfileobj(source,destination)
            # Prepare every complete file before replacing a previous report.
            for sibling,target in prepared: os.replace(sibling,target)
        finally:
            for sibling,_ in prepared: sibling.unlink(missing_ok=True)
    return result
