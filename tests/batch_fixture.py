"""Owned synthetic child using the unchanged pipeline's real soundfile writes."""
from pathlib import Path
import shutil
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]


def make_fixture(root, launcher=None):
    root.mkdir(parents=True, exist_ok=True)
    for folder in ('events', 'gt', 'out', 'app'):
        (root / folder).mkdir()
    for name in ('launch_runs.py', 'eventized_audio.py'):
        shutil.copyfile(launcher if name == 'launch_runs.py' and launcher else ROOT / name, root / 'app' / name)
    events = np.array([(0, 0, 0, 0), (1, 1, 1, 10)], dtype=[('x', 'u2'), ('y', 'u2'), ('p', 'i2'), ('t', 'i8')])
    np.save(root / 'events' / 'sample_chipbag.npy', events)
    sf.write(root / 'gt' / 'sample_gt.wav', np.sin(np.arange(1600) * .1) * .2, 16000)
    source = (ROOT / 'run_offline.py').read_text()
    fragment = source[source.rindex('out_path_44khz ='):]
    first = 'sf.write(out_path_44khz, out_signal_sr, 44100)'
    assert fragment.count(first) == 1
    fragment = fragment.replace(first, first + '\nif scenario == "fail_first": raise SystemExit(9)')
    prefix = '''import argparse, os
from pathlib import Path
import numpy as np
import soundfile as sf
p=argparse.ArgumentParser()
for flag in ('event_path','gt_path','out_path'): p.add_argument('--'+flag,required=True)
a=p.parse_args();gt_path=a.gt_path;out_path=a.out_path
scenario=os.environ.get('EVENTIZED_TEST_SCENARIO','success')
np.load(a.event_path,allow_pickle=False)
gt_16khz,rate=sf.read(gt_path);assert rate==16000
out_signal_sr=np.sin(np.arange(4410)*.1)*.3
out_signal_16khz=np.sin(np.arange(1600)*.2)*.3
psq=1.23;sto=.45
if scenario=='no_products': raise SystemExit(0)
if scenario=='mutate_reference':
    Path(gt_path).write_bytes(b'controlled staged reference mutation');raise SystemExit(9)
'''
    suffix = '''
if scenario=='fail_last': raise SystemExit(9)
if scenario=='corrupt': Path(out_path).write_bytes(Path(out_path).read_bytes()[:-2])
if scenario=='late_collision': Path(os.environ['EVENTIZED_TEST_COLLISION']).write_bytes(b'late user file')
'''
    for mode in ('offline','online'):
        (root / 'app' / f'run_{mode}.py').write_text(prefix + fragment + suffix)
    return fragment
