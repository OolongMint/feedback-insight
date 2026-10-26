"""Provider routing is explicit; all API traffic here stays on loopback."""
import csv
import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from src.feedback_insight.__main__ import main
from src.feedback_insight.classify import LiveClient, ModelError
from src.feedback_insight.pipeline import run
from src.feedback_insight.report import render_report


@contextmanager
def local_provider():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append({'path': self.path, 'authorization': self.headers.get('Authorization'), 'body': body})
            payload = json.loads(body['messages'][1]['content'])
            if 'feedback' in payload:
                content = {'labels': [dict(source_row=row['source_row'], topic='性能与稳定性', sentiment='负向', severity=3) for row in payload['feedback']]}
            else:
                content = {'topics': [dict(topic=topic['topic'], source_rows=[row['source_row'] for row in topic['feedback'][:5]], opportunity='investigate') for topic in payload['topics']]}
            envelope = {'choices': [{'message': {'content': json.dumps(content, ensure_ascii=False)}}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 50}}
            encoded = json.dumps(envelope, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', received
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class OpenAIProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'input.csv'
        with self.source.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['反馈文本', '日期', '渠道', '用户编号'])
            writer.writerows([
                ['姓名：张三 手机13800138000 闪退', '2026-10-20', '客服', 'u1'],
                ['页面卡顿', '2026-10-21', '客服', 'u2'],
            ])

    def command(self, *extra):
        return ['analyze', '--input', str(self.source), '--output', str(self.root / 'out'),
                '--budget', '1', '--input-price', '1', '--output-price', '2', *extra]

    def invoke(self, arguments, environment):
        output, errors = io.StringIO(), io.StringIO()
        # Windows socket/SSL initialization needs these OS paths even for HTTP.
        # Preserve no API key, provider, or proxy variable from the real shell.
        isolated={key:value for key,value in os.environ.items() if key.upper() in ('SYSTEMROOT','WINDIR','TEMP','TMP')}
        isolated.update(environment)
        with patch.dict(os.environ, isolated, clear=True), redirect_stdout(output), redirect_stderr(errors):
            code = main(arguments)
        return code, output.getvalue(), errors.getvalue()

    def test_openai_defaults_ignore_compatible_environment(self):
        environment = {'OPENAI_API_KEY': 'openai-test-key', 'OPENAI_MODEL': 'gpt-test',
                       'FEEDBACK_API_KEY': 'compatible-test-key', 'FEEDBACK_BASE_URL': 'https://elsewhere.invalid/v1', 'FEEDBACK_MODEL': 'other-model'}
        fake_result = {'metadata': {'valid_rows': 2, 'rejected_rows': 0, 'cost_cny': 0}, 'topics': []}
        with patch('src.feedback_insight.__main__.LiveClient') as client, patch('src.feedback_insight.__main__.run', return_value=fake_result):
            code, _, _ = self.invoke(self.command('--provider', 'openai'), environment)
        self.assertEqual(code, 0)
        self.assertEqual(client.call_args.kwargs['base_url'], 'https://api.openai.com/v1')
        self.assertEqual(client.call_args.kwargs['model'], 'gpt-test')
        self.assertEqual(client.call_args.kwargs['api_key'], 'openai-test-key')
        self.assertEqual(client.call_args.kwargs['provider'], 'openai')

    def test_compatible_cannot_reuse_openai_credentials(self):
        with patch('src.feedback_insight.__main__.LiveClient') as client:
            code, _, error = self.invoke(self.command('--base-url', 'https://elsewhere.invalid/v1', '--model', 'test'), {'OPENAI_API_KEY': 'do-not-forward'})
        self.assertEqual(code, 1)
        self.assertIn('FEEDBACK_API_KEY', error)
        self.assertNotIn('do-not-forward', error)
        client.assert_not_called()

    def test_openai_cannot_reuse_compatible_credentials(self):
        with patch('src.feedback_insight.__main__.LiveClient') as client:
            code, _, error = self.invoke(self.command('--provider', 'openai', '--model', 'gpt-test'), {'FEEDBACK_API_KEY': 'do-not-forward'})
        self.assertEqual(code, 1)
        self.assertIn('OPENAI_API_KEY', error)
        self.assertNotIn('do-not-forward', error)
        client.assert_not_called()

    def test_compatible_retains_existing_environment_contract(self):
        fake_result = {'metadata': {'valid_rows': 2, 'rejected_rows': 0, 'cost_cny': 0}, 'topics': []}
        environment = {'FEEDBACK_API_KEY': 'legacy-key', 'FEEDBACK_BASE_URL': 'https://legacy.invalid/v1', 'FEEDBACK_MODEL': 'legacy-model', 'OPENAI_API_KEY': 'unrelated-key'}
        with patch('src.feedback_insight.__main__.LiveClient') as client, patch('src.feedback_insight.__main__.run', return_value=fake_result):
            code, _, _ = self.invoke(self.command(), environment)
        self.assertEqual(code, 0)
        self.assertEqual(client.call_args.kwargs['api_key'], 'legacy-key')
        self.assertEqual(client.call_args.kwargs['base_url'], 'https://legacy.invalid/v1')
        self.assertEqual(client.call_args.kwargs['model'], 'legacy-model')
        self.assertEqual(client.call_args.kwargs['provider'], 'compatible')

    def test_openai_requires_explicit_or_openai_model(self):
        with patch('src.feedback_insight.__main__.LiveClient') as client:
            code, _, error = self.invoke(self.command('--provider', 'openai'), {'OPENAI_API_KEY': 'key', 'FEEDBACK_MODEL': 'wrong-provider-model'})
        self.assertEqual(code, 1)
        self.assertIn('OPENAI_MODEL', error)
        client.assert_not_called()

    def test_openai_cli_real_transport_and_escaped_model_identity(self):
        model = 'gpt-test-<img src=x onerror=alert(1)>'
        with local_provider() as (url, requests):
            code, _, errors = self.invoke(self.command('--provider', 'openai', '--base-url', url, '--model', model),
                                          {'OPENAI_API_KEY': 'openai-local-secret', 'FEEDBACK_API_KEY': 'wrong-secret'})
        self.assertEqual((code, errors), (0, ''))
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(r['authorization'] == 'Bearer openai-local-secret' for r in requests))
        self.assertTrue(all(r['path'] == '/v1/chat/completions' for r in requests))
        self.assertTrue(all('temperature' not in r['body'] for r in requests))
        self.assertTrue(all(r['body']['max_completion_tokens'] == 4000 for r in requests))
        serialized = json.dumps([r['body'] for r in requests], ensure_ascii=False)
        for value in ('张三', '13800138000', 'openai-local-secret', 'wrong-secret'):
            self.assertNotIn(value, serialized)
        report = json.loads((self.root / 'out/analysis.json').read_text(encoding='utf-8'))
        self.assertEqual(report['metadata']['provider'], 'openai')
        self.assertEqual(report['metadata']['model'], model)
        self.assertEqual(report['metadata']['prompt_tokens'], 200)
        self.assertEqual(report['metadata']['completion_tokens'], 100)
        self.assertAlmostEqual(report['metadata']['cost_cny'], .0004)
        self.assertTrue(report['citation_check']['passed'])
        html = (self.root / 'out/report.html').read_text(encoding='utf-8')
        self.assertIn('OpenAI', html)
        self.assertIn('&lt;img', html)
        self.assertNotIn('<img src=x onerror=alert(1)>', html)

    def test_demo_metadata_never_claims_openai_model(self):
        report = run(self.source, self.root / 'demo', mode='demo')
        self.assertEqual(report['metadata']['provider'], 'local')
        self.assertEqual(report['metadata']['model'], 'local-rules')
        self.assertIn('规则演示', render_report(report))

    def test_client_validates_provider_without_changing_legacy_construction(self):
        settings = dict(base_url='https://api.openai.com/v1', model='gpt-test', api_key='key', budget=1, input_price=1, output_price=2)
        self.assertEqual(LiveClient(**settings).provider, 'compatible')
        with self.assertRaises(ModelError):
            LiveClient(**settings, provider='unregistered')


if __name__ == '__main__':
    unittest.main()
