# Batch preservation and recovery

This policy applies only to `python eventized_audio.py batch`. Direct `offline` and `online` commands retain their inherited write/overwrite behavior. Use working copies of inputs and fresh output destinations.

## Before running

- Provide exactly one `<identifier>_gt.wav` or `<identifier>_gt.mp3` for each recording identifier, the portion before its first underscore. Ambiguous references refuse with exit 2.
- Both the output directory and reference directory must be writable. Batch creates private temporary sibling directories, copies reference bytes, and runs the child against that copy. The original event recording is read at its resolved path; numerical scripts do not write it.
- Final publication requires filesystem hard-link support at each destination. Sibling staging avoids an ordinary cross-filesystem link, but filesystems without hard links are unsupported. There is no overwrite/copy fallback.

## Skip and refusal rules

Batch preflights all recordings before starting children. An intact pair consists of a nonempty regular mono PCM16 `_44khz.wav` at 44,100 Hz and at least one intact score-named reconstruction WAV at 16,000 Hz. Such a pair skips. This does **not** compare input identity, timestamps or settings; changed inputs can still match an old completed pair. Use a fresh destination when intentionally reconstructing changed inputs.

If a pair is incomplete and any nominal, 44.1 kHz or matching scored destination is occupied, batch refuses with exit 2. It preserves files, links and directories in those paths. A valid single product, truncated WAV or output symlink does not establish completion. Use a new `--out_dir`; do not delete prior work merely to make a retry run. One incomplete set can block the whole batch's preflight.

After child success, the existing derived reference cache must be a valid regular 16 kHz WAV and byte-identical to the newly generated cache. An identical hardlinked cache is reused without changing its inode or aliases. A differing, invalid or symlinked cache refuses with exit 2 before reconstruction outputs are published. Use a fresh writable copy of the reference directory without that conflicting derived cache, and keep the prior directory intact. Changing only `--out_dir` does not resolve a cache conflict.

## Child and publication outcomes

- A nonzero child exit reports/returns that positive code; a negative child status maps to exit 1. Its staged products are discarded, leaving prior final paths unchanged. Earlier recordings already completed in this batch remain.
- Child exit 0 is accepted only after checking all three expected nonempty mono PCM16 WAV products: one 44.1 kHz reconstruction, exactly one 16 kHz score-named reconstruction, and one 16 kHz reference conversion. Missing, extra score-named or invalid products return exit 1 without final publication.
- Valid new products are created with atomic no-replace hard links, reference cache first when needed, then the 44.1 kHz and scored reconstructions. Existing destinations are never intentionally replaced or unlinked, even if they appear after preflight.
- Publication is **per pathname, not a three-file transaction**. A collision, unsupported hard link, other I/O error or interruption can leave new partial products. Publication I/O failure returns exit 1 and lists paths already created. No rollback deletes those paths, because another process may have changed them. Preserve them for inspection; use fresh output/reference working destinations as needed. No crash durability/fsync or hostile concurrent-directory guarantee is provided.

The filenames and retained numerical algorithms are unchanged. Synthetic native-writer checks cover failure and preservation behavior; one generated offline reconstruction matched direct output bytes. This is not a speech-quality guarantee or validation of the separate online SDK.
