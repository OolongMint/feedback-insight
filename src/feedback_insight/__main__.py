"""Run with python -m src.feedback_insight."""
import argparse
import json
import os
import sys
from pathlib import Path

from .classify import LiveClient
from .pipeline import run
from .evaluate import evaluate, load_analysis, load_sanitized


def main(argv=None):
    parser=argparse.ArgumentParser(description='用户反馈洞察助手：本地CSV、可追溯原话、离线HTML报告')
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('demo','analyze'):
        command=commands.add_parser(name,help='零API调用规则演示' if name=='demo' else '分析反馈（默认需要模型配置）')
        command.add_argument('--input',default='data/feedback.csv')
        command.add_argument('--output',default='reports/demo' if name=='demo' else 'reports/latest')
        command.add_argument('--mode',choices=('demo','live'),default='demo' if name=='demo' else 'live')
        command.add_argument('--provider',choices=('compatible','openai'),default='compatible',help='openai 使用 OPENAI_API_KEY；compatible 使用 FEEDBACK_API_KEY')
        command.add_argument('--base-url',help='兼容服务地址；openai 默认 https://api.openai.com/v1')
        command.add_argument('--model',help='模型ID；openai 可读 OPENAI_MODEL，compatible 可读 FEEDBACK_MODEL')
        command.add_argument('--budget',type=float)
        command.add_argument('--input-price',type=float,help='每百万输入Token的人民币价格')
        command.add_argument('--output-price',type=float,help='每百万输出Token的人民币价格')
        command.add_argument('--token-parameter',choices=('max_completion_tokens','max_tokens'),default='max_completion_tokens')
        command.add_argument('--redact-name',action='append',default=[],help='调用前替换指定姓名，可重复使用')
        command.add_argument('--names-file',help='本地姓名名单，每行一项，不会发送模型')
        command.add_argument('--synthetic',action='store_true',help='在报告中明确标记本次输入为合成数据')
    command=commands.add_parser('evaluate',help='仅评估人工标注黄金集，不调用模型')
    command.add_argument('--input',required=True,help='分析输出的sanitized.csv')
    command.add_argument('--predictions',required=True,help='分析输出的analysis.json')
    command.add_argument('--golden',required=True,help='人工标注的60条黄金集')
    command.add_argument('--output',default='reports/evaluation.json')
    args=parser.parse_args(argv)
    try:
        if args.command=='evaluate':
            predictions,topics,metadata=load_analysis(args.predictions)
            source=load_sanitized(args.input)
            # Restore labels only to check each citation belongs to its topic.
            labels={r.source_row:r for r in predictions}
            for row in source:
                if row.source_row in labels:
                    row.topic=labels[row.source_row].topic
                    row.quarantined=labels[row.source_row].quarantined
            result=evaluate(predictions,topics,args.golden,source,metadata)
            path=Path(args.output)
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'status':result['status'],'passed':result['passed'],'issues':result['issues']},ensure_ascii=False))
            return 0 if result['passed'] else 2
        names=args.redact_name
        if args.names_file: names+=Path(args.names_file).read_text(encoding='utf-8-sig').splitlines()
        client=None
        if args.mode=='live':
            # Credentials never fall through to a different provider's environment.
            is_openai=args.provider=='openai'
            key_name='OPENAI_API_KEY' if is_openai else 'FEEDBACK_API_KEY'
            model_name='OPENAI_MODEL' if is_openai else 'FEEDBACK_MODEL'
            api_key=os.environ.get(key_name,'')
            base_url=args.base_url or ('https://api.openai.com/v1' if is_openai else os.environ.get('FEEDBACK_BASE_URL'))
            model=args.model or os.environ.get(model_name)
            if not api_key: raise ValueError(f'{args.provider} 模式需要环境变量 {key_name}；Codex 登录不替代产品 API Key')
            if not model: raise ValueError(f'{args.provider} 模式需要 --model 或环境变量 {model_name}')
            if not base_url: raise ValueError('compatible 模式需要 --base-url 或环境变量 FEEDBACK_BASE_URL')
            if any(value is None for value in (args.budget,args.input_price,args.output_price)): raise ValueError('live 需要 --budget、--input-price 和 --output-price（人民币计价）')
            client=LiveClient(base_url=base_url,model=model,api_key=api_key,budget=args.budget,input_price=args.input_price,output_price=args.output_price,token_parameter=args.token_parameter,provider=args.provider)
        builtin_demo=args.command=='demo' and Path(args.input).resolve()==Path(__file__).resolve().parents[2]/'data'/'feedback.csv'
        result=run(args.input,args.output,mode=args.mode,client=client,names=names,synthetic=args.synthetic or builtin_demo)
        print(json.dumps({'status':'ok','mode':args.mode,'valid_rows':result['metadata']['valid_rows'],'rejected_rows':result['metadata']['rejected_rows'],'topics':len(result['topics']),'report':str(Path(args.output)/'report.html'),'cost_cny':result['metadata']['cost_cny']},ensure_ascii=False))
        return 0
    except (ValueError,OSError,UnicodeError) as error:
        # Only our own ValueError messages are safe; OS errors can include local PII paths.
        safe=str(error) if isinstance(error,ValueError) and not isinstance(error,(UnicodeError,json.JSONDecodeError)) else '文件读写失败，请检查路径与权限'
        print('错误：'+safe,file=sys.stderr)
        return 1


if __name__=='__main__': raise SystemExit(main())
