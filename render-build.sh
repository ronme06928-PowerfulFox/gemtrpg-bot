#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# Render環境でのDBセットアップ
# テーブル作成 (app.pyの起動時にも実行されるが、念のため)
# python -c "from app import app, db; app.app_context().push(); db.create_all()"

# デフォルト画像の登録・同期
# CloudinaryへのアップロードとDB登録を行う
# 既に登録済みの画像はスキップされるので、毎回実行しても安全です
python scripts/register_default_images.py
