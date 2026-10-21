"""The common code is task-neutral: no fixed test input (a particular app idea) and no fixed data provider is named in it."""
import re
import unittest
from pathlib import Path

from backend.contracts import ROOT

FORBIDDEN = re.compile(r'cafemap|kakao|geoapify|map_access|validate_cafemap|카공', re.I)
SCANNED = ('runner', 'backend', 'infra', 'templates')
SUFFIXES = {'.py', '.json', '.sh', '.js', '.html', '.css'}
SKIPPED_PARTS = {'.venv', '__pycache__', 'node_modules'}


def scanned_files():
    for top in SCANNED:
        for path in sorted((ROOT / top).rglob('*')):
            if path.is_file() and path.suffix in SUFFIXES and not SKIPPED_PARTS & set(path.parts) and path != Path(__file__).resolve():
                yield path


class TaskNeutrality(unittest.TestCase):
    def test_the_pattern_catches_the_names_it_is_meant_to_forbid(self):
        for name in ('cafemap-v1', 'backend/kakao.py', 'Geoapify', 'map_access', '카공지도'):
            self.assertTrue(FORBIDDEN.search(name), name)

    def test_common_code_names_no_template_or_provider(self):
        files = list(scanned_files())
        self.assertGreater(len(files), 50)
        hits = [f'{p.relative_to(ROOT)}:{n}' for p in files for n, line in enumerate(p.read_text(errors='replace').splitlines(), 1) if FORBIDDEN.search(line)]
        self.assertEqual(hits, [])


if __name__ == '__main__':
    unittest.main()
