# Verification record

Verified on 2026-09-22 with Python 3.12.13 on Apple Silicon macOS, CPU execution. Exact installed package versions are in `requirements.txt`.

## Passed

- All seven unit tests passed, covering command dispatch, batch failure propagation, missing inputs, resume behavior, and ignoring unrelated files.
- All Python source compiled successfully.
- `uv pip check` confirmed all 50 installed packages are compatible.
- Main help and offline help completed successfully with installed dependencies.
- All three numerical reconstruction files match baseline source snapshot `30195c6155b730511dd90172bf420a21dca8ea25` byte for byte.
- A seeded one-second synthetic recording containing 250,000 events completed the real offline reconstruction twice: once through the baseline script, once through the EventizedAudio entry point. No mocks were used for optical flow, filtering, denoising, resampling, evaluation, or WAV writing.
- The two reconstructed WAVs (44.1 kHz and 16 kHz) and the generated 16 kHz reference WAV were byte-identical. The input reference was also checked. Exact hashes and sample counts are in [offline-equivalence.json](offline-equivalence.json).

- A real batch reconstruction succeeded from another working directory with spaces in all input/output paths. All three generated WAVs matched the baseline, and a second batch invocation skipped the completed recording.
- A disposable failing child reproduced the prior launcher’s endless polling: it timed out after three seconds. The updated launcher returned the child’s exit code 9 within the same deadline. [Batch evidence](batch-verification.json).

## Dependency compatibility

Unrestricted latest packages failed inside the unchanged high-pass filter because NumPy 2.5 rejects conversion of its one-item cutoff array to a scalar. The verified environment pins NumPy 1.26.4, SciPy 1.13.1, OpenCV 4.10.0.84, librosa 0.11.0, and compatible dependencies. Install the supplied requirements rather than upgrading numerical packages without retesting.

## Limits

- The synthetic fixture proves parity for that input and environment; it is not a speech-recovery quality benchmark or a universal equivalence proof.
- The original research dataset and event-camera hardware were not used. Research results have not been independently reproduced.
- Online reconstruction was not executed because `metavision_sdk_cv` is unavailable in the local environment. Its source remains unchanged and its command dispatch is covered.
- Batch processing retains the existing naming convention and resume heuristic. It now runs each child directly without a shell and reports child failures immediately; successful numerical processing and output filenames are preserved. Online batch reconstruction still requires the unverified SDK.
- Malformed/empty events and zero-motion cases retain the existing numerical limitations. Destination folders must exist, and the pipeline writes a converted ground-truth file beside the input.
- The full pinned environment was tested on macOS ARM64 only. Other operating systems, Python versions, and numerical environments are unverified.

## Reproduce

```bash
python -m unittest discover -s tests -v
python -m compileall -q eventized_audio.py run_offline.py run_online.py launch_runs.py utils.py tests
python tests/verify_offline_equivalence.py
python tests/verify_batch_behavior.py
```

The regression script uses the retained source snapshot under `tests/fixtures/baseline`, generates its own data under ignored `.verification/`, and compares WAV bytes. It works from a fresh clone or source archive without inherited Git history.
