"""Shared preset construction must work without HTTP/Socket entry modules."""

import os
from pathlib import Path
import subprocess
import sys


def test_simulator_builds_preset_without_importing_socket_routes():
    code = r'''
import builtins

real_import = builtins.__import__

def import_without_entrypoints(name, *args, **kwargs):
    if name == 'events' or name.startswith('events.') or name == 'app':
        raise AssertionError(f'Preset construction imported an entrypoint: {name}')
    return real_import(name, *args, **kwargs)

builtins.__import__ = import_without_entrypoints
from manager.sim.preset_loader import _build_character_from_preset

store = {'character_presets': {'enemy': {
    'name': 'Enemy',
    'allow_enemy': True,
    'character_json': {'name': 'Enemy', 'hp': 10, 'maxHp': 10},
}}}
character = _build_character_from_preset(store, 'enemy', 'enemy', 1)
assert character['type'] == 'enemy'
assert character['hp'] == 10
assert character['name'] == 'Enemy'
assert character['id'].startswith('char_bo_')
assert 'id' not in store['character_presets']['enemy']['character_json']
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
