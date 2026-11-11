"""PR60-21 の試作のサーバー：見本のページを配り、/power_preview で本物の計算を返す（本番には入らない）。

python scripts/catalog_preview/pr21/serve.py  →  http://127.0.0.1:8766/
"""
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault("GEMTRPG_DISABLE_DEFAULT_APP", "1")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from power import preview  # noqa: E402

PAGES = ROOT / "_local" / "catalog_preview" / "pr21"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PAGES), **kwargs)

    def do_POST(self):
        if self.path != "/power_preview":
            self.send_error(404)
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            status, result = 200, preview(body["payload"], body.get("entry_id"), body.get("params") or {})
        except Exception as exc:  # 試作なので理由をそのまま返す
            status, result = 400, {"error": str(exc)}
        data = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8766), Handler).serve_forever()
