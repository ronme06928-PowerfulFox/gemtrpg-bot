#!/usr/bin/env bash
# exit on error
set -o errexit

# 念のため依存関係を再確認・インストール
pip install -r requirements.txt

# デフォルト画像の登録・同期
# 起動時（Start Command）なら環境変数が確実に読み込まれています
echo "Registering default images..."
python scripts/register_default_images.py

# アプリケーションの起動
echo "Starting Gunicorn..."
gunicorn --worker-class eventlet -w 1 app:app
