"""Process matching event recordings sequentially and report child failures."""

import argparse
from pathlib import Path
import subprocess
import sys

from tqdm import tqdm


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event_dir", default="EventRecordings", help="Directory containing <identifier>[_experiment].npy files")
    parser.add_argument("--gt_dir", default="GroundTruth", help="Directory containing <identifier>_gt.wav or .mp3 files")
    parser.add_argument("--out_dir", default="Output", help="Output directory")
    parser.add_argument("--mode", choices=("online", "offline"), default="online")
    args = parser.parse_args(argv)
    event_dir, gt_dir, out_dir = map(Path, (args.event_dir, args.gt_dir, args.out_dir))
    for label, directory in (("Event recordings", event_dir), ("Ground truth", gt_dir)):
        if not directory.is_dir():
            parser.error(f"{label} directory does not exist: {directory}")

    ground_truth = {
        path.name.split("_")[0]: path
        for path in gt_dir.iterdir()
        if path.is_file() and path.name.endswith(("_gt.wav", "_gt.mp3"))
    }
    recordings = sorted(path for path in event_dir.glob("*.npy") if path.is_file())
    if not recordings:
        parser.error(f"No .npy event recordings found in {event_dir}")
    for recording in recordings:
        key = recording.stem.split("_")[0]
        if key not in ground_truth:
            parser.error(f"No matching ground truth for {recording.name}; expected {key}_gt.wav or {key}_gt.mp3")
    out_dir.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve().parent / f"run_{args.mode}.py"

    for recording in tqdm(recordings, leave=True):
        key = recording.stem.split("_")[0]
        output = out_dir / f"{recording.stem}_hat_{args.mode}.wav"
        # Preserve the existing resume behavior and successful output names.
        previous = [path.name.split("_hat")[0] for path in out_dir.iterdir() if path.is_file() and args.mode in path.name]
        if output.name.split("_hat")[0] in previous:
            print(f"File {recording.stem} already exists")
            continue
        print(f"Processing {recording}")
        result = subprocess.run([
            sys.executable, str(script),
            "--event_path", str(recording),
            "--gt_path", str(ground_truth[key]),
            "--out_path", str(output),
        ], check=False)
        if result.returncode:
            print(f"Processing failed for {recording} (exit {result.returncode})", file=sys.stderr)
            return result.returncode if result.returncode > 0 else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
