# Render環境での設定ガイド

## 問題の概要
以下のエラーが発生していました：
1. `RuntimeError: do not call blocking functions from the mainloop`
2. Worker異常終了
3. PostgreSQL SSL接続切断

## 修正内容

### 1. データベース接続プール設定の追加
`app.py`に以下の設定を追加しました：
- `pool_pre_ping`: 接続前の健全性チェック
- `pool_recycle`: 5分ごとに接続を再利用
- `pool_size`: 接続プールサイズを10に設定
- `max_overflow`: プールがフルの時の追加接続数を20に設定

### 2. Gunicorn設定ファイルの作成
`gunicorn_config.py`を作成し、以下を改善：
- Eventletワーカーとの互換性確保
- シグナル処理の最適化
- ワーカー再起動設定（メモリリーク対策）
- グレースフルシャットダウンの設定

### 3. Procfileの更新
設定ファイルを使用するように変更：
```
web: gunicorn -c gunicorn_config.py app:app
```

## デプロイ手順

### Renderダッシュボードでの設定確認
以下の環境変数が正しく設定されていることを確認してください：

#### 必須の環境変数
- `DATABASE_URL`: PostgreSQLの接続URL（自動設定される）
- `SECRET_KEY`: Flask用のシークレットキー
- `GOOGLE_CREDENTIALS_JSON`: Google Sheets APIの認証情報（JSON文字列）

#### オプションの環境変数
- `PORT`: ポート番号（デフォルト: 10000、Renderが自動設定）
- `RENDER`: Render環境であることを示すフラグ（自動設定される）

### デプロイ
1. 修正したファイルをGitにコミット：
```bash
git add app.py gunicorn_config.py Procfile manager/data_manager.py
git commit -m "Fix eventlet and PostgreSQL connection issues"
git push
```

2. Renderが自動的に再デプロイを開始します

## トラブルシューティング

### もしまだエラーが発生する場合

#### 1. ワーカー数を調整
`gunicorn_config.py`の`workers`を確認：
```python
workers = 1  # Eventletでは1が推奨
```

#### 2. タイムアウトを調整
```python
timeout = 120
graceful_timeout = 30
```

#### 3. データベース接続プールを調整
`app.py`のSQLALCHEMY_ENGINE_OPTIONSで以下を調整：
```python
'pool_recycle': 300,  # より短い間隔で接続を再利用する場合は180など
'pool_size': 10,      # 必要に応じて増減
```

#### 4. データベース接続プールを調整
`app.py`のSQLALCHEMY_ENGINE_OPTIONSで以下を調整：
```python
'pool_recycle': 300,  # より短い間隔で接続を再利用する場合は180など
'pool_size': 10,      # 必要に応じて増減
```

#### 5. 入退室ログが描画されない場合
以下の修正により改善されています：
- **クライアント側**: `logToBattleLog`関数にタイムスタンプとデバッグログを追加
- **サーバー側**: `join_room`イベントで、`state_updated`送信後に短い遅延を入れてから入室ログを送信
- ブラウザの開発者コンソールで`[LOG]`プレフィックスのログを確認し、DOM要素の存在をチェック

#### 6. Renderのログを確認
Renderダッシュボードの「Logs」タブで詳細なエラー情報を確認できます。

## 期待される結果
- Workerが正常に起動し続ける
- データベース接続エラーが発生しない
- `RuntimeError: do not call blocking functions from the mainloop`が発生しない
