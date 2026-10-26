"""TCPを使えない環境向け。ローカルアプリの実HTTPルートへテストclientで要求を渡す。"""

import base64
import contextlib
import io
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
# 起動時のログを検証結果や個人データとして保存しない。
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    from app import app

client = app.test_client()
for line in sys.stdin:
    request = json.loads(line)
    route = request['path']
    method = request.get('method', 'GET')
    # テスト登録以外の書き込み、ルーム・ログ・管理APIを扱わない。
    allowed = route == '/api/register' if method == 'POST' else (
        route == '/' or route.startswith('/api/get_session_user') or
        Path(route.split('?')[0]).suffix.lower() in {'.js', '.css', '.html', '.svg', '.png', '.ico', '.woff2'}
    )
    if not allowed or 'socket.io' in route:
        result = {'status': 403, 'body': '', 'mime': 'text/plain'}
    else:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            response = client.open(route, method=method, data=request.get('body'), content_type=request.get('mime'))
        result = {
            'status': response.status_code,
            'body': base64.b64encode(response.get_data()).decode('ascii'),
            'mime': response.content_type,
        }
    print(json.dumps(result), flush=True)
