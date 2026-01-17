import os
import multiprocessing

# Gunicorn設定ファイル
# Eventletワーカーとの互換性を確保

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 1  # Eventletでは通常1ワーカーで十分
worker_class = 'eventlet'
timeout = 120
graceful_timeout = 30
keepalive = 5

# Eventletとの競合を避けるため、シグナル処理を調整
worker_tmp_dir = '/dev/shm'  # Renderの推奨設定

# ロギング設定
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# プロセス名
proc_name = 'gemtrpg-dicebot'

# ワーカー再起動の設定（メモリリーク対策）
max_requests = 1000
max_requests_jitter = 50
