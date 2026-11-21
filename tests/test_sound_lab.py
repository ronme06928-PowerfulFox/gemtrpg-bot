import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'scripts/sound_lab'


def test_chime_presets_have_three_value_only_variants():
    settings = json.loads((LAB / 'presets.json').read_text(encoding='utf-8'))
    assert list(settings['variants']) == ['s1', 's2', 's3']
    assert isinstance(settings['seed'], int)
    assert all(len(bar['ratios']) == len(bar['decay']) == len(bar['overtones']) for bar in settings['bars'])
    for bar in settings['bars']:
        assert bar['t'] >= 0 and bar['freq'] > 0 and bar['ratios'][0] == 1
        assert all(value > 0 for value in bar['decay'])


def test_chime_output_is_reproducible_and_small(tmp_path):
    windows_python = Path('C:/Users/yharu/anaconda3/python.exe')
    python = os.environ.get('SOUND_LAB_PYTHON', str(windows_python) if windows_python.exists() else sys.executable)
    if not shutil.which('ffmpeg') or subprocess.run([python, '-c', 'import numpy, scipy']).returncode:
        pytest.skip('NumPy, SciPy and FFmpeg are required to synthesize the gallery audio')
    outputs = [tmp_path / str(i) for i in range(2)]
    for output in outputs:
        subprocess.run([python, str(LAB / 'chime.py'), '--output-dir', str(output),
                        '--reference', str(tmp_path / 'absent.mp3')], cwd=ROOT, check=True, timeout=60)
    for asset in ('s1.ogg', 's2.ogg', 's3.ogg'):
        first, second = [(directory / asset).read_bytes() for directory in outputs]
        assert first.startswith(b'OggS') and len(first) <= 60_000
        assert first == second
