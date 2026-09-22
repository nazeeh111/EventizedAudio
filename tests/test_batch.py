from contextlib import redirect_stderr
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import launch_runs


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="eventized batch ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.events = self.root / "events"
        self.gt = self.root / "ground truth"
        self.out = self.root / "output"
        self.events.mkdir()
        self.gt.mkdir()
        self.args = ["--event_dir", str(self.events), "--gt_dir", str(self.gt), "--out_dir", str(self.out), "--mode", "offline"]

    def recording(self, name="speech_chipbag"):
        (self.events / f"{name}.npy").touch()
        (self.gt / f"{name.split('_')[0]}_gt.wav").touch()

    def test_child_failure_returns_without_polling(self):
        self.recording()
        with patch("launch_runs.subprocess.run", return_value=subprocess.CompletedProcess([], 9)) as run:
            self.assertEqual(launch_runs.main(self.args), 9)
        command = run.call_args.args[0]
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[command.index("--gt_path") + 1], str(self.gt / "speech_gt.wav"))
        self.assertEqual(command[command.index("--out_path") + 1], str(self.out / "speech_chipbag_hat_offline.wav"))
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_success_and_ignore_unrelated_files(self):
        self.recording()
        (self.events / "notes.txt").touch()
        with patch("launch_runs.subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(launch_runs.main(self.args), 0)
            self.assertEqual(run.call_count, 1)

    def test_existing_output_is_skipped(self):
        self.recording()
        self.out.mkdir()
        (self.out / "speech_chipbag_hat_offline_44khz.wav").touch()
        with patch("launch_runs.subprocess.run") as run:
            self.assertEqual(launch_runs.main(self.args), 0)
            run.assert_not_called()

    def test_missing_ground_truth_is_rejected_before_launch(self):
        (self.events / "missing.npy").touch()
        with patch("launch_runs.subprocess.run") as run, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            launch_runs.main(self.args)
        self.assertEqual(result.exception.code, 2)
        run.assert_not_called()

    def test_empty_recording_directory_is_rejected(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            launch_runs.main(self.args)
        self.assertEqual(result.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
