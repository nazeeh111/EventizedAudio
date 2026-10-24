"""Batch publication preservation with real bounded children and native WAV writes."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import importlib.util

import numpy as np
import soundfile as sf
from batch_fixture import ROOT, make_fixture


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='eventized preservation ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        self.gt = self.root / 'gt/sample_gt.wav'
        self.cache = self.root / 'gt/sample_gt_16khz.wav'
        self.out = self.root / 'out'
        self.wav44 = self.out / 'sample_chipbag_hat_offline_44khz.wav'
        self.score = self.out / 'sample_chipbag_hat_offline_pesq1.23_stoi0.45.wav'
        self.nominal = self.out / 'sample_chipbag_hat_offline.wav'
        self.args = ['--event_dir', str(self.root/'events'), '--gt_dir', str(self.root/'gt'), '--out_dir', str(self.out), '--mode', 'offline']
        self.before_gt = digest(self.gt)

    def run_batch(self, scenario='success', entry=False, **env):
        cmd = [sys.executable, str(self.root/'app'/('eventized_audio.py' if entry else 'launch_runs.py'))]
        if entry:
            cmd.append('batch')
        result = subprocess.run(cmd + self.args, cwd=self.root, capture_output=True, text=True, timeout=15,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', EVENTIZED_TEST_SCENARIO=scenario, **env))
        self.assertEqual(digest(self.gt), self.before_gt, 'input reference changed')
        self.assertEqual(list(self.root.rglob('.eventized-*')), [], 'owned staging directories leaked')
        return result

    def wav(self, path, rate, value=.1):
        sf.write(path, np.full(160, value), rate)
        return digest(path)

    def test_real_first_write_then_failure_preserves_existing_reference_cache(self):
        cache_hash = self.wav(self.cache, 16000)
        result = self.run_batch('fail_first')
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertIn('exit 9', result.stderr)
        self.assertEqual(digest(self.cache), cache_hash)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_failure_after_all_three_writes_publishes_nothing(self):
        result = self.run_batch('fail_last')
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertFalse(self.cache.exists())

    def test_partial_valid_wav_refused_before_child(self):
        prior = self.wav(self.wav44, 44100)
        result = self.run_batch('fail_first')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(digest(self.wav44), prior)
        self.assertFalse(self.score.exists())

    def test_stale_score_and_truncated_wav_are_not_overwritten(self):
        for path, rate in ((self.score, 16000), (self.wav44, 44100)):
            with self.subTest(path=path.name):
                self.wav(path, rate)
                path.write_bytes(path.read_bytes()[:-2])
                prior = digest(path)
                result = self.run_batch()
                self.assertEqual(result.returncode, 2)
                self.assertEqual(digest(path), prior)
                path.unlink()  # This fixture's identified disposable WAV only.

    def test_complete_pair_still_skips_without_child_execution(self):
        a = self.wav(self.wav44, 44100); b = self.wav(self.score, 16000)
        result = self.run_batch('fail_last')
        self.assertEqual(result.returncode, 0)
        self.assertIn('already exists', result.stdout)
        self.assertEqual((digest(self.wav44), digest(self.score)), (a, b))
        self.assertFalse(self.cache.exists())

    def test_success_matches_direct_native_writer_bytes_and_entrypoint(self):
        expected = self.root/'expected';expected.mkdir()
        reference = expected/'sample_gt.wav';reference.write_bytes(self.gt.read_bytes())
        nominal = expected/self.nominal.name
        subprocess.run([sys.executable, str(self.root/'app/run_offline.py'), '--event_path',str(self.root/'events/sample_chipbag.npy'),
                        '--gt_path',str(reference),'--out_path',str(nominal)],check=True,timeout=15)
        result = self.run_batch(entry=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for actual in (self.wav44, self.score, self.cache):
            self.assertEqual(actual.read_bytes(), (expected/actual.name).read_bytes())
            self.assertEqual(actual.stat().st_nlink, 1)
        self.assertFalse(self.nominal.exists())

    def test_two_recordings_reuse_identical_cache_without_replacing_inode(self):
        self.assertEqual(self.run_batch().returncode, 0)
        prior = self.cache.stat(); prior_hash = digest(self.cache)
        np.save(self.root/'events/sample_second.npy', np.load(self.root/'events/sample_chipbag.npy'))
        result = self.run_batch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.cache.stat().st_ino, prior.st_ino)
        self.assertEqual(digest(self.cache), prior_hash)
        self.assertTrue((self.out/'sample_second_hat_offline_44khz.wav').exists())

    def test_identical_hardlinked_reference_cache_is_reused_without_writing_alias(self):
        os.link(self.gt,self.cache)
        prior=self.gt.stat();original=digest(self.cache)
        result=self.run_batch()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.gt.stat().st_ino,prior.st_ino)
        self.assertEqual(self.cache.stat().st_ino,prior.st_ino)
        self.assertEqual(digest(self.cache),original)
        self.assertEqual(self.cache.stat().st_nlink,2)

    def test_different_existing_reference_cache_refuses_before_publication(self):
        prior = self.wav(self.cache, 16000)
        result = self.run_batch()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(digest(self.cache), prior)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_zero_exit_without_valid_products_is_failure(self):
        for scenario in ('no_products','corrupt'):
            with self.subTest(scenario=scenario):
                result = self.run_batch(scenario)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(list(self.out.iterdir()), [])
                self.assertFalse(self.cache.exists())

    def test_output_links_directories_and_nominal_collisions_preserved(self):
        target = self.root/'alias-target.wav';prior = self.wav(target, 44100)
        for kind in ('symlink','broken-symlink','hardlink','directory','nominal'):
            with self.subTest(kind=kind):
                path = self.nominal if kind=='nominal' else self.wav44
                if kind=='symlink':path.symlink_to(target)
                elif kind=='broken-symlink':path.symlink_to(self.root/'absent.wav')
                elif kind=='hardlink':os.link(target,path)
                elif kind=='directory':path.mkdir()
                else:path.write_bytes(b'prior nominal')
                before = path.lstat()
                result = self.run_batch()
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(path.lstat().st_ino, before.st_ino)
                self.assertEqual(digest(target), prior)
                path.rmdir() if kind=='directory' else path.unlink()

    def test_reference_cache_symlink_is_refused_and_target_preserved(self):
        target=self.root/'reference-target.wav';prior=self.wav(target,16000)
        self.cache.symlink_to(target)
        result=self.run_batch()
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertTrue(self.cache.is_symlink())
        self.assertEqual(digest(target),prior)
        self.assertEqual(list(self.out.iterdir()),[])

    def test_symlink_input_keeps_original_cache_location_and_input_bytes(self):
        target=self.root/'input-target.wav';self.gt.rename(target);self.gt.symlink_to(target)
        result=self.run_batch()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(self.gt.is_symlink())
        self.assertTrue(self.cache.exists())
        self.assertFalse((self.root/'input-target_16khz.wav').exists())

    def test_child_reference_mutation_is_confined_to_owned_copy(self):
        result=self.run_batch('mutate_reference')
        self.assertEqual(result.returncode,9,result.stderr)
        self.assertEqual(list(self.out.iterdir()),[])
        self.assertFalse(self.cache.exists())

    def test_unsupported_no_replace_publication_fails_without_fallback_writes(self):
        spec=importlib.util.spec_from_file_location('publication_probe',self.root/'app/launch_runs.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.object(module.os,'link',side_effect=OSError('controlled unsupported hard-link filesystem')):
            self.assertEqual(module.main(self.args),1)
        self.assertEqual(digest(self.gt),self.before_gt)
        self.assertFalse(self.cache.exists())
        self.assertEqual(list(self.out.iterdir()),[])
        self.assertEqual(list(self.root.rglob('.eventized-*')),[])

    def test_late_destination_collision_is_never_replaced(self):
        result=self.run_batch('late_collision',EVENTIZED_TEST_COLLISION=str(self.score))
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertEqual(self.score.read_bytes(),b'late user file')
        self.assertTrue(self.wav44.exists())
        self.assertTrue(self.cache.exists())
        self.assertIn('newly published paths retained',result.stderr)

    def test_unrelated_output_ignored_and_online_naming_preserved(self):
        note=self.out/'sample_offline_notes.txt';note.write_bytes(b'keep')
        self.args[-1]='online'
        result=self.run_batch()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue((self.out/'sample_chipbag_hat_online_44khz.wav').exists())
        self.assertEqual(note.read_bytes(),b'keep')

    def test_ambiguous_and_missing_references_refuse_before_output(self):
        duplicate=self.root/'gt/sample_gt.mp3';duplicate.write_bytes(b'fixture')
        self.assertEqual(self.run_batch().returncode,2)
        duplicate.unlink();self.gt.unlink()
        result=subprocess.run([sys.executable,str(self.root/'app/launch_runs.py'),*self.args],capture_output=True,timeout=15)
        self.assertEqual(result.returncode,2)
        self.assertEqual(list(self.out.iterdir()),[])


if __name__ == '__main__':
    unittest.main()
