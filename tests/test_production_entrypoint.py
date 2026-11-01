"""Keep production launch declarations aligned and verify their app export."""

import os
from pathlib import Path
import shlex
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _script_gunicorn_args():
    lines = (ROOT / "render-start.sh").read_text(encoding="utf-8").splitlines()
    commands = [shlex.split(line) for line in lines if line.startswith("gunicorn ")]
    assert len(commands) == 1
    return commands[0]


def test_procfile_matches_confirmed_render_start_command():
    process, command = (ROOT / "Procfile").read_text(encoding="utf-8").strip().split(":", 1)
    assert process == "web"
    assert shlex.split(command) == _script_gunicorn_args()


def test_production_target_exports_http_app_and_socket_handlers(tmp_path):
    target = _script_gunicorn_args()[-1]
    module, attribute = target.split(":", 1)
    env = os.environ.copy()
    for name in ("RENDER", "FLASK_ENV", "APP_ENV", "GEMTRPG_DISABLE_DEFAULT_APP"):
        env.pop(name, None)
    env["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib, sys\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            f"module = importlib.import_module({module!r})\n"
            f"app = getattr(module, {attribute!r})\n"
            "from flask import Flask\n"
            "from extensions import socketio\n"
            "assert isinstance(app, Flask)\n"
            "response = app.test_client().get('/healthz')\n"
            "assert response.status_code == 200\n"
            "assert module._SOCKET_HANDLERS_REGISTERED\n"
            "assert socketio.server.handlers.get('/')\n",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert list(tmp_path.iterdir()) == []
