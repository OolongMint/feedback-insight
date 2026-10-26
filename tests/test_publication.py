"""Generated reports must inherit the destination directory's Windows ACL."""
import csv
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from src.feedback_insight.pipeline import run


class PublicationTests(unittest.TestCase):
    def setUp(self):
        # Deliberately avoid TemporaryDirectory: its private ACL would hide the
        # original issue by making the destination private as well.
        parent = Path(__file__).resolve().parents[1] / 'reports' / 'codex-migration'
        parent.mkdir(parents=True, exist_ok=True)
        self.root = parent / ('.test-publication-' + uuid4().hex)
        self.root.mkdir()
        self.addCleanup(self.cleanup_workspace)
        self.source = self.root / 'input.csv'
        with self.source.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['反馈文本', '日期', '渠道', '用户编号'])
            writer.writerows([['闪退', '2026-10-20', '客服', 'u1'], ['卡顿', '2026-10-21', '客服', 'u2']])
        self.output = self.root / 'published'
        self.output.mkdir()

    def cleanup_workspace(self):
        expected_parent = Path(__file__).resolve().parents[1] / 'reports' / 'codex-migration'
        if self.root.resolve().parent != expected_parent.resolve() or not self.root.name.startswith('.test-publication-'):
            raise AssertionError('Unexpected publication test cleanup path')
        shutil.rmtree(self.root)

    def windows_dacl(self, path):
        # Do not pass PowerShell 7 module paths into Windows PowerShell 5.
        env = {key:value for key,value in os.environ.items() if key.upper() != 'PSMODULEPATH'}
        env['FEEDBACK_TEST_ACL_PATH'] = str(path.resolve())
        command = "(Get-Acl -LiteralPath $env:FEEDBACK_TEST_ACL_PATH).GetSecurityDescriptorSddlForm([System.Security.AccessControl.AccessControlSections]::Access)"
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                                env=env, capture_output=True, text=True)
        if result.returncode:
            self.fail('Windows ACL probe failed: ' + result.stderr.strip())
        return result.stdout.strip()

    @unittest.skipUnless(sys.platform == 'win32', 'Windows DACL regression')
    def test_reports_inherit_destination_acl_like_an_ordinary_file(self):
        probe = self.output / 'ordinary-file.txt'
        probe.write_text('ACL reference', encoding='utf-8')
        expected_acl = self.windows_dacl(probe)
        self.assertTrue(expected_acl)
        run(self.source, self.output, mode='demo')
        for name in ('sanitized.csv', 'analysis.json', 'report.html'):
            with self.subTest(name=name):
                self.assertEqual(self.windows_dacl(self.output / name), expected_acl,
                                 'Published file retained a private staging ACL instead of inheriting its output directory ACL')

    def test_failed_publication_preserves_previous_files_and_cleans_siblings(self):
        run(self.source, self.output, mode='demo')
        previous = {path.name: path.read_bytes() for path in self.output.iterdir()}
        with patch('src.feedback_insight.pipeline.os.replace', side_effect=PermissionError('simulated publication denial')):
            with self.assertRaises(PermissionError):
                run(self.source, self.output, mode='demo')
        self.assertEqual({path.name: path.read_bytes() for path in self.output.iterdir()}, previous)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ['input.csv', 'published'])

    def test_copy_failure_prepares_nothing_partial_and_keeps_previous_report(self):
        run(self.source, self.output, mode='demo')
        previous = {path.name: path.read_bytes() for path in self.output.iterdir()}
        copy = shutil.copyfileobj
        attempts = 0

        def fail_second_copy(source, destination):
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                raise OSError('simulated disk write failure')
            return copy(source, destination)

        with patch('src.feedback_insight.pipeline.shutil.copyfileobj', side_effect=fail_second_copy):
            with self.assertRaises(OSError):
                run(self.source, self.output, mode='demo')
        self.assertEqual({path.name: path.read_bytes() for path in self.output.iterdir()}, previous)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ['input.csv', 'published'])


if __name__ == '__main__':
    unittest.main()
