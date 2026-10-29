"""Offline event indexing and immutable comparison-fixture contracts."""
import ast
import hashlib
import math
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


class EventBinTests(unittest.TestCase):
    def test_last_rounded_event_has_a_valid_time_bin(self):
        source = ROOT / 'run_offline.py'
        tree = ast.parse(source.read_text())
        assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name)
                               and target.id in {'relative_t', 'coord_t', 'nbins'}
                               for target in node.targets)]
        self.assertEqual(len(assignments), 3)
        for last_us, expected in ((0, 1), (40, 2), (999970, 25000),
                                  (999990, 25001), (1000000, 25001)):
            with self.subTest(last_us=last_us):
                events = np.zeros(2, dtype=[('t', 'i8')])
                events['t'] = [0, last_us]
                namespace = dict(events=events, f=25000, np=np, math=math)
                # Execute the production indexing assignments without loading
                # audio/SDK dependencies or starting the reconstruction script.
                exec(compile(ast.Module(body=assignments, type_ignores=[]),
                             str(source), 'exec'), namespace)
                self.assertEqual(namespace['nbins'], expected)
                self.assertLess(int(namespace['coord_t'].max()), namespace['nbins'])

    def test_equivalence_guard_pins_baseline_but_allows_candidate_changes(self):
        source = ROOT / 'tests/verify_offline_equivalence.py'
        tree = ast.parse(source.read_text())
        hashes = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'BASELINE_SHA256'
                              for t in node.targets))
        loop = next(node for node in tree.body if isinstance(node, ast.For))
        code = compile(ast.Module(body=[hashes, loop], type_ignores=[]), str(source), 'exec')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            baseline = root / 'tests/fixtures/baseline'
            baseline.mkdir(parents=True)
            upstream = root / 'upstream'
            upstream.mkdir()
            for name in ('utils.py', 'run_offline.py', 'run_online.py'):
                shutil.copyfile(ROOT / 'tests/fixtures/baseline' / name, baseline / name)
                (root / name).write_text('# controlled candidate source differs\n')
            namespace = dict(ROOT=root, upstream=upstream, hashlib=hashlib, source_hashes={})
            exec(code, namespace)
            for item in namespace['source_hashes'].values():
                self.assertNotEqual(item['baseline'], item['current'])
            (baseline / 'utils.py').write_text('# corrupted reference\n')
            with self.assertRaisesRegex(AssertionError, 'Baseline fixture changed: utils.py'):
                exec(code, namespace)


if __name__ == '__main__':
    unittest.main()
