# GemDiceBot / Gem_DiceBotTool

ジェムリアTRPGのセッション進行を支援するダイスボットです。Flask・Flask-SocketIOで画面と状態を同期し、ローカルはSQLite、本番RenderはPostgreSQLを使用します。画像はCloudinary、スキル等のマスターはGoogle SheetsとJSONキャッシュで管理します。

遊び方は[読者別マニュアル](manuals/START_HERE.md)、開発前の規約は[AGENTS.md](AGENTS.md)、継続的な改善は[アプリ基盤・安定運用プロジェクト](manuals/projects/app_foundation/README.md)を参照してください。

## ローカルで起動する

リポジトリ直下で実行します。Pythonは3.11系（`runtime.txt`は3.11.5）です。Windows PowerShellで環境を新しく用意する場合の例:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python app.py
```

ブラウザで `http://127.0.0.1:5000` を開きます。既存の開発環境を使う場合は、その環境を有効にして起動してください。ローカルDBは `instance/gemtrpg.db`、通常の起動ではマスターJSONを読み込みます。キャッシュ欠落時にGoogle Sheetsから取得する場合も認証設定が必要です。ローカルではRender環境を示す `RENDER` を設定しません。

画像アップロードにはCloudinary、マスターの再取得にはGoogle Sheetsの認証設定が必要です。設定項目は[F01のRender環境変数と運用手順](manuals/implemented/F01_Operations_Manual.md)を参照し、`.env`や認証JSONはGitに追加しないでください。

マスターをGoogle Sheetsから再取得する場合だけ、次を実行します。

```powershell
python app.py --update
```

## フロントエンドを変更する

JS/CSSの編集元は `static/js/`、`static/css/`、`static/styles.css` です。Node.js環境で初回に依存を導入し、変更後にビルドします。

```powershell
npm install
npm run build
```

`static/index.html`は `static/dist/` のバンドルを読みます。成果物・source map・参照ハッシュはビルドで更新し、成果物もGit管理します。既存の成果物でローカル起動するだけならNode.jsは不要です。バンドル順やモバイル版の扱いは[AGENTS.md](AGENTS.md)を確認してください。

演出一覧は `npm run gallery`、解決パネルの比較は `npm run resolve-preview` で生成します。出力先は `_local/` です。

## 変更を確認する

変更に関連するテストを先に確認し、広いロジック変更では全件を実行します。全件テストは通常2分以上かかります。

```powershell
python -m pytest -q
python scripts/check_text_encoding.py
python scripts/check_mojibake_markers.py
```

文字・行末の規約は[CONTRIBUTING.md](CONTRIBUTING.md)、テストの選び方は[テスト案内](manuals/test_manuals/README.md)を参照してください。

## 主なフォルダと資料

| 場所 | 役割 |
|---|---|
| `app.py`・`extensions.py`・`models.py` | 起動とHTTP登録、共有状態・拡張、DBモデル |
| `routes/`・`events/` | HTTPとSocketイベントの入口 |
| `manager/`・`plugins/` | 処理・状態・保存・外部データと効果プラグイン |
| `static/`・`CharaCreator/` | PC画面と素材・バンドル、キャラ作成等の独立HTML |
| `data/` | 起動に使うマスターJSONと検証データ。`archive/` は旧資料の保管先 |
| `scripts/`・`tests/` | ビルド・検査・運用ツール、自動テスト |
| [manuals/](manuals/README.md) | 実装仕様、運用手順、機能計画、常設プロジェクト |
| [typst_manual/](typst_manual/README.md) | ルール本・操作ガイド・動画の制作元と保持方針 |
| `_local/`等 | 確認用出力。保持と片付けはAGENTS.mdに従う。`_local/legacy_data/` と `_local/backups/` は原本保管先で、出力の片付けでは削除しない |

詳しい所在・依存関係と整理候補は[初回棚卸し](manuals/projects/app_foundation/repository_inventory.md)、現在の改善事項は[基盤プロジェクトの課題一覧](manuals/projects/app_foundation/backlog.md)へ進んでください。

## 本番を運用する

`main`へのpushでRenderが自動デプロイします。実施前後の確認と障害調査は[F01 Part 3](manuals/implemented/F01_Operations_Manual.md#part-3-renderデプロイ運用手順)、認証の導入確認は[運用手順書](manuals/operations/account_system_deploy_runbook.md)を参照してください。エージェントによるcommit / pushは、ユーザーの指示があるときだけ行います。

本番RenderのStart Commandは `chmod +x render-start.sh; ./render-start.sh`（2026-10-31に設定画面で確認）。`render-start.sh` と `Procfile` はともに `gunicorn -c gunicorn_config.py app:app` を指定します。実際のBuild Commandは未確認です。詳細は[F01の起動と接続設定](manuals/implemented/F01_Operations_Manual.md#8-起動と接続設定)を参照してください。

DBのPC保管は[PostgreSQL手元バックアップ](manuals/operations/postgres_backup_runbook.md)を参照してください。手動実行は `scripts/backup_postgres.cmd` です。
