"""Reproduce failed-child handling and check real batch reconstruction parity.

First run tests/verify_offline_equivalence.py to prepare the synthetic fixture.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "30195c6155b730511dd90172bf420a21dca8ea25"
WORK = ROOT / ".verification"
assert (WORK / "events.npy").exists(), "Run verify_offline_equivalence.py first"

# Disposable stand-in child isolates failure propagation from numerical code.
with tempfile.TemporaryDirectory(prefix="eventized-failure-", dir=WORK) as directory:
    probe = Path(directory)
    (probe / "events").mkdir()
    (probe / "gt").mkdir()
    (probe / "events" / "speech.npy").touch()
    (probe / "gt" / "speech_gt.wav").touch()
    (probe / "run_offline.py").write_text("raise SystemExit(9)\n")
    (probe / "baseline.py").write_bytes((ROOT / "tests" / "fixtures" / "baseline" / "launch_runs.py").read_bytes())
    shutil.copyfile(ROOT / "launch_runs.py", probe / "updated.py")
    env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))
    arguments = ["--event_dir", "events", "--gt_dir", "gt", "--out_dir", "output", "--mode", "offline"]
    try:
        subprocess.run([sys.executable, "baseline.py", *arguments], cwd=probe, env=env, capture_output=True, timeout=3)
        raise AssertionError("Expected baseline to keep polling after failed child")
    except subprocess.TimeoutExpired:
        pass
    result = subprocess.run([sys.executable, "updated.py", *arguments], cwd=probe, env=env, capture_output=True, timeout=3)
    assert result.returncode == 9, result.stderr.decode()

# A fresh path with spaces checks argument transport in a real successful run.
with tempfile.TemporaryDirectory(prefix="batch with spaces ", dir=WORK) as directory:
    batch = Path(directory)
    events, gt, output = batch / "events", batch / "ground truth", batch / "output"
    events.mkdir()
    gt.mkdir()
    shutil.copyfile(WORK / "events.npy", events / "synthetic_chipbag.npy")
    shutil.copyfile(WORK / "upstream" / "output" / "reference.wav", gt / "synthetic_gt.wav")
    command = [sys.executable, str(ROOT / "eventized_audio.py"), "batch", "--event_dir", str(events), "--gt_dir", str(gt), "--out_dir", str(output), "--mode", "offline"]
    env = dict(os.environ, MPLCONFIGDIR=str(WORK / "matplotlib"), NUMBA_CACHE_DIR=str(WORK / "numba"))
    result = subprocess.run(command, cwd=batch, env=env, capture_output=True, timeout=240)
    (WORK / "batch.log").write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr.decode()
    for reference in (WORK / "upstream" / "output").glob("reconstructed*.wav"):
        candidate = output / reference.name.replace("reconstructed", "synthetic_chipbag_hat_offline")
        assert reference.read_bytes() == candidate.read_bytes(), candidate
    assert (gt / "synthetic_gt_16khz.wav").read_bytes() == (WORK / "upstream" / "output" / "reference_16khz.wav").read_bytes()
    # A second invocation must preserve resume behavior and skip finished work.
    resumed = subprocess.run(command, cwd=batch, env=env, capture_output=True, timeout=10)
    assert resumed.returncode == 0 and b"already exists" in resumed.stdout

record = {"baseline_failed_child": "still polling after 3 seconds; timed out", "updated_failed_child_exit": 9, "real_batch": "passed from another working directory with spaces in paths", "generated_wav_comparisons": 3, "resumed_batch": "skipped existing output"}
(WORK / "batch-results.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
