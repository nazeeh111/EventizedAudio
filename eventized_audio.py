"""EventizedAudio: reconstruct audio from event-camera vibrations."""

import argparse
from pathlib import Path
import subprocess
import sys

SCRIPTS = {
    "offline": "run_offline.py",
    "online": "run_online.py",
    "batch": "launch_runs.py",
}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="EventizedAudio",
        description="Reconstruct audio from event-camera vibrations.",
        epilog="Arguments after the mode are passed unchanged to the original script.",
    )
    parser.add_argument("mode", choices=SCRIPTS, help="reconstruction method or folder batch")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    script = Path(__file__).resolve().parent / SCRIPTS[args.mode]
    return subprocess.call([sys.executable, str(script), *args.arguments])


if __name__ == "__main__":
    raise SystemExit(main())
