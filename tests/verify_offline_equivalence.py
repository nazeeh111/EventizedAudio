"""Run a real synthetic offline comparison against the retained compatibility fixture.

Run from the repository root: python tests/verify_offline_equivalence.py
This is a regression check, not a scientific speech-recovery benchmark.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "30195c6155b730511dd90172bf420a21dca8ea25"
WORK = ROOT / ".verification"
WORK.mkdir(exist_ok=True)
upstream = WORK / "upstream"
upstream.mkdir(exist_ok=True)
source_hashes = {}
for name in ("utils.py", "run_offline.py", "run_online.py"):
    source = (ROOT / "tests" / "fixtures" / "baseline" / name).read_bytes()
    assert source == (ROOT / name).read_bytes(), f"Numerical source changed: {name}"
    (upstream / name).write_bytes(source)
    source_hashes[name] = hashlib.sha256(source).hexdigest()

rng = np.random.default_rng(711)
count = 250000
events = np.empty(count, dtype=[("x", "u2"), ("y", "u2"), ("p", "i2"), ("t", "i8")])
events["t"] = np.sort(rng.integers(0, 999970, count))
events["t"][0] = 0
events["t"][-1] = 999970
events["x"] = rng.integers(0, 12, count)
events["y"] = rng.integers(0, 12, count)
events["p"] = rng.integers(0, 2, count)
np.save(WORK / "events.npy", events)
sr = 16000
t = np.arange(sr, dtype=np.float64) / sr
reference = 0.3 * np.sin(2 * np.pi * (160 * t + 180 * t * t)) * (0.6 + 0.4 * np.sin(2 * np.pi * 7 * t))
env = dict(os.environ, MPLCONFIGDIR=str(WORK / "matplotlib"), NUMBA_CACHE_DIR=str(WORK / "numba"))

for label, command in (
    ("upstream", [sys.executable, str(upstream / "run_offline.py")]),
    ("branded", [sys.executable, str(ROOT / "eventized_audio.py"), "offline"]),
):
    output = WORK / label / "output"
    output.mkdir(exist_ok=True, parents=True)
    # Separate writable ground truths exercise the original side effects too.
    wavfile.write(output / "reference.wav", sr, reference.astype(np.float32))
    args = ["--event_path", str(WORK / "events.npy"), "--gt_path", str(output / "reference.wav"), "--out_path", str(output / "reconstructed.wav")]
    with (WORK / f"{label}.log").open("w") as log:
        subprocess.run(command + args, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=240)

original_files = sorted((upstream / "output").glob("*.wav"))
comparisons = []
for original in original_files:
    candidate = WORK / "branded" / "output" / original.name
    assert original.read_bytes() == candidate.read_bytes(), f"Output differs: {original.name}"
    rate, samples = wavfile.read(original)
    assert np.isfinite(samples).all()
    comparisons.append({"file": original.name, "sample_rate": rate, "samples": len(samples), "sha256": hashlib.sha256(original.read_bytes()).hexdigest()})
assert len(comparisons) == 4, comparisons
record = {"baseline": BASELINE, "source_sha256": source_hashes, "identical_wav_files": comparisons, "scope": "One seeded synthetic 1-second recording; not scientific dataset validation."}
(WORK / "results.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
