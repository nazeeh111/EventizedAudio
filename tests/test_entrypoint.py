import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import eventized_audio


class EntrypointTests(unittest.TestCase):
    def test_modes_preserve_arguments_and_exit_status(self):
        for mode, script in eventized_audio.SCRIPTS.items():
            with self.subTest(mode=mode), patch("eventized_audio.subprocess.call", return_value=7) as call:
                arguments = ["--event_path", "folder with spaces/input.npy", "--out_path", "out.wav"]
                self.assertEqual(eventized_audio.main([mode, *arguments]), 7)
                call.assert_called_once_with([
                    sys.executable, str(Path(eventized_audio.__file__).resolve().parent / script), *arguments
                ])

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(SystemExit) as result:
            eventized_audio.main(["invalid"])
        self.assertEqual(result.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
