import os

os.environ["GEMTRPG_DISABLE_DEFAULT_APP"] = "1"

from app import create_app


def _should_run_startup():
    return os.environ.get("GEMTRPG_SKIP_WSGI_STARTUP") != "1"


app = create_app(run_startup=_should_run_startup(), register_sockets=True)
