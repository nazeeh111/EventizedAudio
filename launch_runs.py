"""Process matching event recordings sequentially and report child failures."""

import argparse
import os
import shutil
import stat
import tempfile
from pathlib import Path
import re
import subprocess
import sys
import wave

from tqdm import tqdm


def complete_wav(path, rate):
    """Check the PCM format and payload, including truncated final writes."""
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return False
        with wave.open(str(path), "rb") as audio:
            if (audio.getframerate() != rate or audio.getnchannels() != 1
                    or audio.getsampwidth() != 2 or audio.getnframes() == 0):
                return False
            remaining = audio.getnframes()
            while remaining:
                frames = min(remaining, 65536)
                if len(audio.readframes(frames)) != frames * 2:
                    return False
                remaining -= frames
        return True
    except (OSError, EOFError, wave.Error):
        return False


def scored_outputs(output):
    pattern = re.compile(
        re.escape(output.stem) + r"_pesq-?\d+\.\d{2}_stoi-?\d+\.\d{2}\.wav"
    )
    return sorted(path for path in output.parent.iterdir() if pattern.fullmatch(path.name)) if output.parent.is_dir() else []


def completed_output(output):
    """Both pipeline products must be intact before a recording is skipped."""
    stem = output.stem
    if not complete_wav(output.with_name(f"{stem}_44khz.wav"), 44100):
        return False
    return any(complete_wav(path, 16000) for path in scored_outputs(output))


def same_bytes(left, right):
    with left.open("rb") as a, right.open("rb") as b:
        while True:
            chunk = a.read(65536)
            if chunk != b.read(65536):
                return False
            if not chunk:
                return True


def run_staged(recording, reference, output, script):
    """Stage all child writes; publish valid products without replacing paths."""
    published = []
    try:
        # Separate sibling directories keep each publication on its own filesystem.
        with tempfile.TemporaryDirectory(prefix=".eventized-", dir=output.parent) as out_tmp, \
                tempfile.TemporaryDirectory(prefix=".eventized-", dir=reference.parent) as gt_tmp:
            staged_output = Path(out_tmp) / output.name
            staged_reference = Path(gt_tmp) / reference.name
            shutil.copyfile(reference, staged_reference)
            result = subprocess.run([
                sys.executable, str(script),
                "--event_path", str(recording.resolve()),
                "--gt_path", str(staged_reference),
                "--out_path", str(staged_output),
            ], check=False)
            if result.returncode:
                print(f"Processing failed for {recording} (exit {result.returncode})", file=sys.stderr)
                return result.returncode if result.returncode > 0 else 1

            wav44 = staged_output.with_name(f"{output.stem}_44khz.wav")
            scores = scored_outputs(staged_output)
            reference16 = staged_reference.with_name(f"{reference.stem}_16khz.wav")
            if (not complete_wav(wav44, 44100) or len(scores) != 1
                    or not complete_wav(scores[0], 16000) or not complete_wav(reference16, 16000)):
                print(f"Processing failed for {recording}: child exited 0 without three valid WAV products", file=sys.stderr)
                return 1

            target_reference = reference.with_name(reference16.name)
            products = []
            if os.path.lexists(target_reference):
                if not complete_wav(target_reference, 16000) or not same_bytes(reference16, target_reference):
                    print(f"Existing reference cache differs or is not a regular valid WAV: {target_reference}; use a fresh ground-truth copy", file=sys.stderr)
                    return 2
            else:
                products.append((reference16, target_reference))
            products.extend((source, output.parent / source.name) for source in (wav44, scores[0]))
            for source, target in products:
                # Atomic no-replace for one pathname, not a multi-file transaction.
                os.link(source, target)
                published.append(str(target))
        return 0
    except OSError as error:
        # Never unlink prior work or roll back paths another process may have changed.
        print(f"Processing failed for {recording}: {error}; newly published paths retained: {published}", file=sys.stderr)
        return 1


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

    ground_truth = {}
    for path in sorted(gt_dir.iterdir()):
        if path.is_file() and path.name.endswith(("_gt.wav", "_gt.mp3")):
            key = path.name.split("_")[0]
            if key in ground_truth:
                parser.error(f"Ambiguous ground truth for {key}: {ground_truth[key].name} and {path.name}; keep one matching reference")
            ground_truth[key] = path
    recordings = sorted(path for path in event_dir.glob("*.npy") if path.is_file())
    if not recordings:
        parser.error(f"No .npy event recordings found in {event_dir}")
    for recording in recordings:
        key = recording.stem.split("_")[0]
        if key not in ground_truth:
            parser.error(f"No matching ground truth for {recording.name}; expected {key}_gt.wav or {key}_gt.mp3")
        output = out_dir / f"{recording.stem}_hat_{args.mode}.wav"
        if not completed_output(output):
            products = [output, output.with_name(f"{output.stem}_44khz.wav"), *scored_outputs(output)]
            occupied = [path for path in products if os.path.lexists(path)]
            if occupied:
                parser.error(f"Existing incomplete output set blocks reconstruction: {occupied}; use a new --out_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve().parent / f"run_{args.mode}.py"

    for recording in tqdm(recordings, leave=True):
        key = recording.stem.split("_")[0]
        output = out_dir / f"{recording.stem}_hat_{args.mode}.wav"
        if completed_output(output):
            print(f"File {recording.stem} already exists")
            continue
        print(f"Processing {recording}")
        status = run_staged(recording, ground_truth[key].absolute(), output.absolute(), script)
        if status:
            return status
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
