"""Report structure and real embedded JavaScript behavior, without model calls."""
import json
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser

from src.feedback_insight.report import render_report


def fixture(count=5):
    rows = [dict(source_row=i + 2, text=f'反馈证据{i + 1}', date=f'2026-10-{20 + i:02d}',
                 channel='客服', user_id=f'user_{i}', topic='性能与稳定性', sentiment='负向',
                 severity=3, quarantined=False) for i in range(count)]
    topic = dict(topic='性能与稳定性', count=count, sentiments={'负向': count}, score=count * 3,
                 max_severity=3, summary=f'本主题包含 {count} 条反馈。', opportunity='继续复现核查。',
                 quotes=[dict(source_row=r['source_row'], text=r['text'], user_id=r['user_id']) for r in rows], sufficient=True)
    return {'rows': rows, 'topics': [topic] if count else [],
            'metadata': {'mode': 'demo', 'synthetic': True, 'elapsed_seconds': .1,
                         'cost_cny': 0, 'rejected_rows': 0, 'quality_status': '待人工黄金集验收'}}


class Structure(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.stack = []
        self.quotes = []
        self.details = []
        self.ids = []
        self.tables = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag in ('meta', 'input', 'link', 'br', 'hr', 'img'):
            if data.get('id'): self.ids.append(data['id'])
            return
        self.stack.append((tag, data))
        if data.get('id'): self.ids.append(data['id'])
        if tag == 'details': self.details.append(data)
        if tag == 'blockquote': self.quotes.append(any(t == 'details' for t, _ in self.stack))
        if tag == 'table': self.tables.append(data)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


class ReportRedesignTests(unittest.TestCase):
    def test_formal_report_contains_compact_overview_and_actual_date_range(self):
        html = render_report(fixture())
        parsed = Structure(html)
        self.assertIn('<h1>用户反馈分析报告</h1>', html)
        self.assertIn('2026-10-20', html)
        self.assertIn('2026-10-24', html)
        self.assertIn('topic-overview', [table.get('id') for table in parsed.tables])
        for heading in ('主题', '反馈数', '负向数', '最高严重度', '优先级得分'):
            self.assertIn(heading, html)
        self.assertNotIn('<aside', html)
        self.assertNotIn('听见用户', html)
        self.assertNotIn('FROM FEEDBACK', html)
        self.assertIn('规则演示', html)
        self.assertIn('合成数据', html)
        self.assertIn('待人工验收', html)

    def test_two_quotes_visible_and_remaining_evidence_in_closed_native_details(self):
        html = render_report(fixture())
        parsed = Structure(html)
        self.assertEqual(parsed.quotes, [False, False, True, True, True])
        self.assertEqual(len(parsed.details), 1)
        self.assertNotIn('open', parsed.details[0])
        self.assertIn('查看其余 3 条原话', html)
        self.assertEqual(len(parsed.ids), len(set(parsed.ids)))
        self.assertIn('feedback-rows', parsed.ids)
        for i in range(2, 7): self.assertIn(f'source-{i}', parsed.ids)

    def test_exactly_two_quotes_needs_no_empty_disclosure(self):
        parsed = Structure(render_report(fixture(2)))
        self.assertEqual(parsed.quotes, [False, False])
        self.assertEqual(parsed.details, [])

    def test_empty_and_insufficient_evidence_are_explicit(self):
        html = render_report(fixture(0))
        self.assertIn('暂无有效反馈', html)
        self.assertIn('暂无日期', html)
        report = fixture(1)
        report['topics'][0]['quotes'] = []
        report['topics'][0]['sufficient'] = False
        self.assertIn('数据不足', render_report(report))

    def test_user_content_stays_outside_executable_script(self):
        report = fixture()
        attack = '</script><img src=x onerror=alert(1)>'
        report['rows'][0]['text'] = attack
        report['topics'][0]['quotes'][0]['text'] = attack
        html = render_report(report)
        self.assertNotIn(attack, html)
        self.assertIn('&lt;/script&gt;', html)
        self.assertNotIn(attack, re.search(r'<script>(.*?)</script>', html, re.S)[1])
        self.assertNotRegex(html, r'<(?:script|link)[^>]+(?:src|href)=')

    @unittest.skipUnless(shutil.which('node'), 'Node is required for embedded script behavior checks')
    def test_print_cycle_and_source_link_restore_real_embedded_script_state(self):
        script = re.search(r'<script>(.*?)</script>', render_report(fixture()), re.S)[1]
        harness = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
class Element {
  constructor(id='', text='') { this.id=id; this.textContent=text; this.value=''; this.hidden=false; this.open=false; this.listeners={}; this.dataset={}; }
  addEventListener(type, fn) { (this.listeners[type]??=[]).push(fn); }
  dispatch(type) { for(const fn of this.listeners[type]??[]) fn({target:this,preventDefault(){}}); }
  getAttribute(key) { return this[key]??null; }
  scrollIntoView() {}
}
const ids={};
for(const id of ['search','topic-filter','sentiment-filter','result-count','no-results','print-report']) ids[id]=new Element(id);
const rows=[new Element('source-2','闪退'),new Element('source-3','登录失败')];
rows[0].dataset={topic:'性能与稳定性',sentiment:'负向'};
rows[1].dataset={topic:'账号与登录',sentiment:'负向'};
for(const row of rows) ids[row.id]=row;
const details=[new Element(),new Element()]; details[1].open=true;
const citation=new Element(); citation.href='#source-3';
const windowEvents={};
const document={
 getElementById:id=>ids[id],
 querySelector:selector=>selector.startsWith('#')?ids[selector.slice(1)]:null,
 querySelectorAll:selector=>selector.includes('tbody')||selector.includes('feedback-rows')?rows:selector.includes('details')?details:selector.includes('href')?[citation]:[],
};
const window={addEventListener:(type,fn)=>(windowEvents[type]??=[]).push(fn),print(){},location:{hash:''}};
const context={document,window,location:window.location,console,requestAnimationFrame:fn=>fn()};
vm.runInNewContext(SCRIPT,context);
const fire=type=>{for(const fn of windowEvents[type]??[])fn();};
ids.search.value='闪退'; ids.search.dispatch('input');
assert.equal(rows[1].hidden,true,'search hides nonmatching source');
const priorCount=ids['result-count'].textContent;
fire('beforeprint'); fire('beforeprint');
assert.deepEqual(details.map(d=>d.open),[true,true],'printing expands evidence');
assert.deepEqual(rows.map(r=>r.hidden),[false,false],'printing includes all feedback');
fire('afterprint');
assert.deepEqual(details.map(d=>d.open),[false,true],'printing restores disclosure choices');
assert.deepEqual(rows.map(r=>r.hidden),[false,true],'printing restores filtered source rows');
assert.equal(ids['result-count'].textContent,priorCount,'printing restores result count');
citation.dispatch('click');
assert.equal(ids.search.value,'','source link clears search');
assert.deepEqual(rows.map(r=>r.hidden),[false,false],'source link reveals original feedback');
'''.replace('SCRIPT', json.dumps(script, ensure_ascii=False))
        result = subprocess.run(['node', '-e', harness], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
