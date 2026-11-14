"""Shared preset construction must work without HTTP/Socket entry modules."""

import os
from pathlib import Path
import subprocess
import sys


def test_simulator_builds_preset_without_importing_socket_routes():
    code = r'''
import builtins

real_import = builtins.__import__

def import_without_entrypoints(name, globals=None, locals=None, fromlist=(), level=0):
    if level == 0 and (name == 'events' or name.startswith('events.') or name == 'app'):
        raise AssertionError(f'Preset construction imported an entrypoint: {name}')
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = import_without_entrypoints
from manager.sim.preset_loader import _build_character_from_preset

store = {'character_presets': {'enemy': {
    'name': 'Enemy',
    'allow_enemy': True,
    'hp': 10,
}}}
character = _build_character_from_preset(store, 'enemy', 'enemy', 1, masters={})
assert character['type'] == 'enemy'
assert character['hp'] == 10
assert character['name'] == 'Enemy'
assert character['id'].startswith('char_unit_')
assert 'id' not in store['character_presets']['enemy']
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
