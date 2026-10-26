"""Offline baseline and strictly validated remote model interface."""
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from pathlib import Path

from .models import TOPICS, SENTIMENTS


class ModelError(ValueError): pass


def classify_demo(rows):
    rules = [('性能与稳定性', ('卡顿','闪退','崩溃','慢','加载','crash','lag','卡死','丢失')), ('账号与登录', ('登录','登陆','验证码','账号','密码','login')), ('付费与订单', ('支付','退款','扣款','订单','收费','价格','订阅')), ('功能需求', ('希望','建议','增加','支持','导出','批量','功能')), ('使用体验', ('界面','按钮','操作','找不到','导航','难用'))]
    output=[]
    for row in rows:
        if row.quarantined:
            output.append(replace(row,topic='其他',sentiment='中性',severity=1))
            continue
        text=row.text.lower()
        topic=next((topic for topic, keywords in rules if any(k in text for k in keywords)), '其他')
        negative=any(k in text for k in ('不','没','失败','卡','闪退','崩溃','慢','差','垃圾','丢失','crash','糟糕','扣款','退款','难用'))
        positive=any(k in text for k in ('喜欢','很好','好用','满意','流畅','方便','赞','不错','great'))
        sentiment='负向' if negative else '正向' if positive else '中性'
        severity=5 if any(k in text for k in ('丢失','重复扣款')) else 4 if any(k in text for k in ('无法使用','崩溃','卡死')) else 3 if any(k in text for k in ('闪退','失败','无法','不能','退款')) else 2 if negative else 1
        output.append(replace(row,topic=topic,sentiment=sentiment,severity=severity))
    return output


def validate_labels(payload, rows):
    if not isinstance(payload,list) or len(payload)!=len(rows): raise ModelError('模型分类条数不匹配')
    expected={r.source_row:r for r in rows}
    seen=set()
    result=[]
    for item in payload:
        if not isinstance(item,dict) or set(item)!={'source_row','topic','sentiment','severity'}: raise ModelError('模型分类结构无效')
        row_id=item['source_row']
        if type(row_id) is not int or row_id not in expected or row_id in seen: raise ModelError('模型返回未知或重复行号')
        if item['topic'] not in TOPICS or item['sentiment'] not in SENTIMENTS or type(item['severity']) is not int or not 1<=item['severity']<=5: raise ModelError('模型分类标签无效')
        seen.add(row_id)
        result.append(replace(expected[row_id],topic=item['topic'],sentiment=item['sentiment'],severity=item['severity']))
    return sorted(result,key=lambda r:r.source_row)


class LiveClient:
    def __init__(self, *, base_url, model, api_key, budget, input_price, output_price, timeout=40, max_calls=24, max_output_tokens=4000, token_parameter='max_completion_tokens', provider='compatible'):
        if provider not in ('compatible','openai'): raise ModelError('模型 provider 必须为 compatible 或 openai')
        parsed=urllib.parse.urlparse(base_url)
        if parsed.scheme not in ('https','http') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment: raise ModelError('模型 Base URL 无效')
        if parsed.scheme=='http' and parsed.hostname not in ('127.0.0.1','localhost','::1'): raise ModelError('远程模型必须使用 HTTPS')
        if not api_key or not model: raise ModelError('live 模式需要模型名和 '+('OPENAI_API_KEY' if provider=='openai' else 'FEEDBACK_API_KEY'))
        if any(not math.isfinite(v) or v<=0 for v in (budget,input_price,output_price)): raise ModelError('预算和每百万 Token 单价必须为正数')
        if token_parameter not in ('max_completion_tokens','max_tokens'): raise ModelError('不支持的 token 参数')
        self.url=base_url.rstrip('/')+'/chat/completions'
        self.provider=provider
        self.model,self.api_key,self.budget,self.input_price,self.output_price=model,api_key,budget,input_price,output_price
        self.timeout,self.max_calls,self.max_output_tokens,self.token_parameter=timeout,max_calls,max_output_tokens,token_parameter
        self.calls=0
        self.cost=0.0
        self.prompt_tokens=0
        self.completion_tokens=0
        self.usage_estimated=False
        self.started=time.monotonic()

    def complete(self, payload, purpose):
        if self.usage_estimated: raise ModelError('上次请求缺少可靠 usage，已停止后续付费调用')
        prompt_path=Path(__file__).resolve().parents[2]/'prompts'/f'{purpose}.txt'
        prompt=prompt_path.read_text(encoding='utf-8')
        messages=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
        # UTF-8 bytes provide a conservative input bound plus protocol overhead.
        input_bound=len(json.dumps(messages,ensure_ascii=False).encode('utf-8'))+2048
        reserve=(input_bound*self.input_price+self.max_output_tokens*self.output_price)/1_000_000
        remaining=240-(time.monotonic()-self.started)
        if self.calls>=self.max_calls or remaining<=0: raise ModelError('已达到调用次数或总运行时间上限')
        if self.cost+reserve>self.budget: raise ModelError('预计费用超过预算，未发送模型请求')
        request_body={'model':self.model,'messages':messages,self.token_parameter:self.max_output_tokens,'response_format':{'type':'json_object'}}
        request=urllib.request.Request(self.url,data=json.dumps(request_body).encode(),headers={'Authorization':'Bearer '+self.api_key,'Content-Type':'application/json'},method='POST')
        self.calls+=1
        try:
            with urllib.request.urlopen(request,timeout=min(self.timeout,remaining)) as response:
                raw=response.read(2_000_001)
                if len(raw)>2_000_000: raise ModelError('模型响应过大')
            envelope=json.loads(raw)
        except (urllib.error.URLError,TimeoutError,OSError,ValueError):
            self.cost+=reserve
            self.usage_estimated=True
            raise ModelError('模型请求失败或响应无效；已保守预留本次费用，不自动重试') from None
        usage=envelope.get('usage') if isinstance(envelope,dict) else None
        valid_usage=isinstance(usage,dict) and all(type(usage.get(k)) is int and usage[k]>=0 for k in ('prompt_tokens','completion_tokens'))
        if valid_usage:
            input_tokens,output_tokens=usage['prompt_tokens'],usage['completion_tokens']
            self.prompt_tokens+=input_tokens
            self.completion_tokens+=output_tokens
            self.cost+=(input_tokens*self.input_price+output_tokens*self.output_price)/1_000_000
        else:
            self.cost+=reserve
            self.usage_estimated=True
        if self.cost>self.budget: raise ModelError('服务返回费用超出预算，已停止后续调用')
        try:
            content=envelope['choices'][0]['message']['content']
            parsed=json.loads(content)
            if not isinstance(parsed,dict): raise ValueError()
            return parsed
        except (KeyError,IndexError,TypeError,ValueError): raise ModelError('模型必须返回有效 JSON 对象') from None


def classify_live(rows, client):
    result=[replace(r,topic='其他',sentiment='中性',severity=1) for r in rows if r.quarantined]
    safe=[r for r in rows if not r.quarantined]
    for offset in range(0,len(safe),25):
        batch=safe[offset:offset+25]
        payload={'feedback':[{'source_row':r.source_row,'text':r.text} for r in batch]}
        response=client.complete(payload,'classify')
        if set(response)!={'labels'}: raise ModelError('模型分类响应字段无效')
        result.extend(validate_labels(response['labels'],batch))
    return sorted(result,key=lambda r:r.source_row)
