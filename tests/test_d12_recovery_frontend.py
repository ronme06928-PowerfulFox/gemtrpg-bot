from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("scenario", ["registration", "login"])
def test_auth_success_shows_issued_code_without_blocking_socket(scenario):
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync('static/js/main.js', 'utf8');
const start = source.indexOf('    function onSuccess(data) {');
const end = source.indexOf('    async function withLock(fn)', start);
assert(start >= 0 && end > start);
const calls = [];
const context = {
  applySessionUserData: () => calls.push('apply'),
  saveRecoveryTokenFromResponse: () => calls.push('save'),
  initializeSocketIO: () => calls.push('socket'),
  showRecoveryCodeOnce: code => {
    if (code) calls.push('code:' + code);
    return new Promise(() => {});
  },
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const registration = process.argv[1] === 'registration';
const data = registration ? {recovery_code: 'GEM-TEST-TEST'} : {};
context.onSuccess(data);
assert.deepStrictEqual(calls, registration
  ? ['apply', 'save', 'socket', 'code:GEM-TEST-TEST']
  : ['apply', 'save', 'socket']);
"""
    result = subprocess.run(["node", "-e", script, scenario], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
