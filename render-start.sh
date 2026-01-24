#!/usr/bin/env bash
# exit on error
set -o errexit

# デフォルト画像の登録・同期
# 画像はGit同梱（ローカル素材）になったので登録スクリプトは不要です
# echo "Registering default images..."
# python scripts/register_default_images.py

# アプリケーションの起動
echo "Starting Gunicorn..."
gunicorn --worker-class eventlet -w 1 app:app
