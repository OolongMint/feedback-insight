"""Independent structural probes for offline reporting, without golden labels."""
import copy
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.feedback_insight.insights import aggregate
from src.feedback_insight.models import Feedback
from src.feedback_insight.report import render_report


class Node:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children, self.parts = [], []

    @property
    def text(self):
        return ''.join(self.parts) + ''.join(child.text for child in self.children)

    def find(self, tag=None, **attrs):
        found = []
        for child in self.children:
            if (tag is None or child.tag == tag) and all(child.attrs.get(k) == v for k, v in attrs.items()):
                found.append(child)
            found.extend(child.find(tag, **attrs))
        return found

    def has_ancestor(self, tag):
        current = self.parent
        while current:
            if current.tag == tag:
                return True
            current = current.parent
        return False


class Tree(HTMLParser):
    VOID = {'meta', 'link', 'input', 'img', 'hr', 'br', 'area', 'base', 'embed', 'source', 'wbr', 'param', 'col'}

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node('root')
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        child = Node(tag, attrs, self.current)
        self.current.children.append(child)
        if tag not in self.VOID:
            self.current = child

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, text):
        self.current.parts.append(text)


def fixture():
    rows = [Feedback(index + 2, f'第{index + 1}种表达的页面卡顿反馈', f'2026-10-{index + 1:02d}', '客服', f'user-{index}',
                     topic='性能与稳定性', sentiment='负向', severity=3) for index in range(6)]
    rows.extend([Feedback(index + 20, f'第{index}种登录错误', '2026-10-15', '应用内', f'login-{index}',
                          topic='账号与登录', sentiment='负向', severity=2) for index in range(2)])
    return {'rows': [row.to_dict() for row in rows], 'topics': aggregate(rows),
            'metadata': {'mode': 'demo', 'provider': 'local', 'model': 'local-rules', 'synthetic': True,
                         'elapsed_seconds': .1, 'cost_cny': 0, 'rejected_rows': 0}}


class IndependentReportTests(unittest.TestCase):
    def setUp(self):
        self.report = fixture()
        self.html = render_report(self.report)
        self.tree = Tree(self.html).root

    def test_report_title_and_provenance_are_explicit_without_marketing_layout(self):
        self.assertEqual([node.text for node in self.tree.find('h1')], ['用户反馈分析报告'])
        self.assertEqual(self.tree.find('aside'), [])
        self.assertNotIn('听见用户', self.html)
        self.assertNotIn('FROM FEEDBACK', self.html)
        self.assertIn('合成数据', self.tree.text)
        self.assertIn('规则演示', self.tree.text)
        self.assertTrue('待人工验收' in self.tree.text or '待验收' in self.tree.text)
        self.assertIn('2026-10-01', self.tree.text)
        self.assertIn('2026-10-15', self.tree.text)

    def test_only_feedback_records_own_source_ids(self):
        nodes = [n for n in self.tree.find() if n.attrs.get('id', '').startswith('source-')]
        self.assertEqual(len(nodes), len(self.report['rows']))
        self.assertEqual(len({n.attrs['id'] for n in nodes}), len(nodes))
        self.assertTrue(all(n.tag == 'tr' and n.has_ancestor('tbody') for n in nodes))
        feedback_body = self.tree.find('tbody', id='feedback-rows')
        self.assertEqual(len(feedback_body), 1)
        self.assertEqual(len(feedback_body[0].find('tr')), len(self.report['rows']))

    def test_two_evidence_quotes_remain_visible_and_remainder_is_native_closed_details(self):
        articles = self.tree.find('article')
        self.assertEqual(len(articles), 2)
        first = articles[0]
        direct_quotes = [q for q in first.find('blockquote') if not q.has_ancestor('details')]
        self.assertEqual(len(direct_quotes), 2)
        detail = first.find('details')
        self.assertEqual(len(detail), 1)
        self.assertNotIn('open', detail[0].attrs)
        self.assertEqual(len(detail[0].find('blockquote')), 3)
        self.assertIn('3', detail[0].find('summary')[0].text)

    def test_two_quote_theme_has_no_empty_expand_control(self):
        second = self.tree.find('article')[1]
        self.assertEqual(len(second.find('blockquote')), 2)
        self.assertEqual(second.find('details'), [])

    def test_topic_summary_has_five_contract_columns(self):
        headers = [[n.text.strip() for n in head.find('th')]
                   for table in self.tree.find('table') for head in table.find('thead')]
        self.assertIn(['主题', '反馈数', '负向数', '最高严重度', '优先级得分'], headers)

    def test_all_free_text_escapes_and_report_has_no_remote_asset_dependencies(self):
        altered = copy.deepcopy(self.report)
        attack = '</script><img src=x onerror=alert(1)><svg onload=alert(2)>冲突文本'
        altered['rows'][0]['text'] = attack
        altered['rows'][0]['channel'] = attack
        altered['topics'][0]['quotes'][0]['text'] = attack
        altered['topics'][0]['quotes'][0]['user_id'] = attack
        altered['topics'][0]['topic'] = attack
        altered['topics'][0]['summary'] = attack
        altered['topics'][0]['opportunity'] = attack
        altered['metadata'].update(mode='live', provider='openai', model=attack)
        html = render_report(altered)
        tree = Tree(html).root
        self.assertEqual(tree.find('img') + tree.find('svg'), [])
        self.assertNotIn(attack, html)
        self.assertIn('&lt;img', html)
        self.assertEqual(len(tree.find('script')), 1)
        for node in tree.find():
            for key in ('src', 'href'):
                self.assertFalse(node.attrs.get(key, '').startswith(('https:', 'http:', '//')))
            self.assertFalse(any(key.startswith('on') for key in node.attrs))

    def test_empty_report_does_not_fabricate_dates_quotes_or_external_content(self):
        html = render_report({'rows': [], 'topics': [], 'metadata': self.report['metadata']})
        tree = Tree(html).root
        self.assertIn('暂无', tree.text)
        self.assertNotIn('2026-', tree.text)
        self.assertEqual(tree.find('blockquote'), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
