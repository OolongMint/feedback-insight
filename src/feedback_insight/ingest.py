"""Parse local CSV once; only sanitized records leave this module."""
import csv
import hashlib
import io
import re
from datetime import date
from pathlib import Path

from .models import Feedback

ALIASES = {
    'text': ('feedback', 'text', '反馈文本', '反馈', '内容'),
    'date': ('date', '日期'),
    'channel': ('channel', '渠道'),
    'user_id': ('user_id', '用户编号', '用户ID', '用户id'),
}
INJECTION = re.compile(r'忽略.{0,12}(?:指令|规则|提示)|(?:ignore|disregard).{0,30}(?:instruction|previous|system)|system\s*:|系统提示|输出.{0,12}PWNED|扮演.{0,8}(?:系统|管理员)', re.I)


def redact(text, names=()):
    text = str(text or '')
    for name in sorted(set(names), key=len, reverse=True):
        if name.strip(): text = text.replace(name.strip(), '[姓名]')
    text = re.sub(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', '[邮箱]', text)
    text = re.sub(r'(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}(?!\d)', '[手机]', text)
    text = re.sub(r'(?<!\d)\d{17}[0-9Xx](?!\d)', '[身份证]', text)
    text = re.sub(r'(?i)((?:订单(?:号|编号)?|order(?:\s*id)?)[：:#\s]*)([A-Za-z0-9_-]{5,})', r'\1[订单号]', text)
    text = re.sub(r'((?:姓名|联系人|收件人)[：:\s]+)[\u4e00-\u9fff·]{2,5}', r'\1[姓名]', text)
    text = re.sub(r'(?<!\d)(?:\d[ -]?){13,19}(?!\d)', '[长号码]', text)
    return text


def load_feedback(path, names=()):
    raw = Path(path).read_bytes()
    if len(raw) > 8_000_000: raise ValueError('CSV 超过 8 MB，请拆分后处理')
    try: decoded = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        try: decoded = raw.decode('gb18030')
        except UnicodeDecodeError: raise ValueError('CSV 编码必须为 UTF-8 或 GB18030') from None
    reader = csv.reader(io.StringIO(decoded, newline=''), strict=True)
    try: header = next(reader)
    except (StopIteration, csv.Error): raise ValueError('CSV 缺少有效表头') from None
    header = [value.strip() for value in header]
    if len(header) != len(set(header)): raise ValueError('CSV 存在重复列名')
    mapping = {key: next((header.index(a) for a in aliases if a in header), None) for key, aliases in ALIASES.items()}
    if any(mapping[k] is None for k in ('text','date')): raise ValueError('CSV 必须包含反馈文本、日期列')
    stats = {'valid_rows':0,'rejected_rows':0,'duplicate_rows':0,'quarantined_rows':0,'redacted_rows':0,'rejections':[]}
    def reject(source_row,reason):
        stats['rejected_rows']+=1
        stats['rejections'].append({'source_row':source_row,'reason':reason})
    result, seen = [], set()
    try:
        while True:
            physical_row = reader.line_num + 1
            try: values = next(reader)
            except StopIteration: break
            if len(result) + stats['rejected_rows'] >= 5000: raise ValueError('CSV 最多支持 5000 条，请拆分后处理')
            if len(values) != len(header):
                reject(physical_row,'列数与表头不匹配')
                continue
            fields = {key: values[idx].strip() if idx is not None else '' for key, idx in mapping.items()}
            try:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',fields['date']): raise ValueError()
                date.fromisoformat(fields['date'])
            except ValueError:
                reject(physical_row,'日期格式无效')
                continue
            if not fields['text'] or len(fields['text']) > 12000:
                reject(physical_row,'反馈为空或超过12000字符')
                continue
            cleaned = redact(fields['text'],names)
            # Missing user identity is unknown, not proof of different users.
            user_id = 'unknown' if not fields['user_id'] else 'user_' + hashlib.sha256(fields['user_id'].encode()).hexdigest()[:16]
            channel = redact(fields['channel'],names) or '未提供'
            identity = (cleaned, fields['date'], user_id)
            stats['duplicate_rows'] += identity in seen
            seen.add(identity)
            quarantined = bool(INJECTION.search(cleaned))
            stats['quarantined_rows'] += quarantined
            stats['redacted_rows'] += cleaned != fields['text'] or channel != (fields['channel'] or '未提供')
            result.append(Feedback(physical_row,cleaned,fields['date'],channel,user_id,quarantined=quarantined))
    except csv.Error: raise ValueError('CSV 格式损坏，请检查引号与分隔符') from None
    stats['valid_rows'] = len(result)
    return result, stats


def write_sanitized(path, rows):
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f, fieldnames=['source_row','text','date','channel','user_id'])
        writer.writeheader()
        for row in rows:
            writer.writerow({key:row.to_dict()[key] for key in writer.fieldnames})
