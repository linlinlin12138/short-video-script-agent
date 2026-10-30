import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.cli import load_env, main


class CLITests(unittest.TestCase):
    def test_env_is_data_and_process_values_take_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('# test\nexport OPENAI_API_KEY="test-only"\nOPENAI_MODEL=from-file\nUNRELATED=ignore\nOPENAI_BASE_URL=https://example.test/v1\n')
            with patch.dict(os.environ, {'OPENAI_MODEL': 'from-process'}, clear=True):
                load_env(path)
                self.assertEqual(os.environ['OPENAI_API_KEY'], 'test-only')
                self.assertEqual(os.environ['OPENAI_MODEL'], 'from-process')
                self.assertNotIn('UNRELATED', os.environ)

    def test_cli_persists_incomplete_task_and_returns_one(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'input.json').write_text('{}')
            with patch('builtins.print'):
                code = main(['--input', str(path / 'input.json'), '--model', 'mock', '--output-dir', str(path / 'out')])
            self.assertEqual(code, 1)
            self.assertTrue((path / 'out/trace.jsonl').exists())


if __name__ == '__main__':
    unittest.main()
