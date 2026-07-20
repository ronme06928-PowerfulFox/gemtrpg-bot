# AGENTS.md

このリポジトリを編集する AI エージェント（Codex / Claude Code など）および開発者向けの共通ルール。
**作業前に必ず一読し、コミット前に該当チェックを通すこと。**

## プロジェクト概要

- ジェムリアTRPG用ダイスボット。**Flask + Flask-SocketIO**（リアルタイム）。
- 永続化は **PostgreSQL**（本番 Render）/ ローカルは SQLite。画像は **Cloudinary**、スキル等マスターデータは **Google Sheets** から取り込み JSON キャッシュ化。
- デプロイ: **main へ push すると Render が自動デプロイ**（Render は Python 環境で **Node を持たない**）。
- バックエンド主要: `app.py`（ルート/起動）, `manager/`（ロジック層）, `events/`（Socket ハンドラ）, `models.py`。

## フロントエンド JS は必ずビルドする（最重要）

`static/index.html` は個別の JS/CSS ではなく **バンドル成果物**のみを読み込む:
`static/dist/app.bundle.js`（クラシックスクリプト連結）, `static/dist/battle.bundle.js`（`battle/index.js` の ES モジュールツリー）, `static/dist/app.bundle.css`（`styles.css` の `@import` を全インライン化）。

**ルール:**
1. JS/CSS の編集対象は **必ず `static/js/` と `static/css/`（および `static/styles.css`）のソース**。`static/dist/` の成果物は直接編集しない（ビルドで上書きされる）。
2. `static/js/*` や `static/css/*`・`styles.css` を編集したら **`npm run build` を実行**してから起動・確認・コミットする。実行しないとブラウザに反映されず、リポジトリ上でソースと成果物が不整合になる。
3. ビルド成果物 `static/dist/*`（`.map` 含む）は **リポジトリにコミットする**（Render に Node が無いため）。`node_modules/` は `.gitignore` 済み。
4. `index.html` に **新しいクラシック JS を追加**する場合は、`scripts/build_frontend.mjs` の `CLASSIC_SCRIPTS` 配列にも **同じ順序**で追加する（ここがバンドル順の単一の正）。CSS の新モジュールは従来どおり `static/styles.css` に `@import` を追加すればよい（ビルドが自動でインライン化する）。
5. 連結バンドルはグローバルスコープ共有方式を保つため **識別子の mangling は無効**（空白/構文圧縮のみ）。グローバル名（`window.X` や トップレベル関数）に依存するコードは安全。
6. `static/mobile/` は別エントリで現状バンドル対象外。

```bash
# JS 編集後
npm install   # 初回のみ（esbuild 取得）
npm run build
```

## 文字コード / 文字化け対策（CONTRIBUTING.md と同一）

- 全テキストファイルは **UTF-8（BOM なし）**。既知の文字化けマーカー文字を含めない。
- Python でファイル書き込み時は `encoding="utf-8"`、PowerShell では `-Encoding utf8`。
- 外部コマンド出力をエンコーディング未確認のままソースへ保存しない。
- コミット前チェック:

```bash
python scripts/check_text_encoding.py
python scripts/check_mojibake_markers.py
```

CI と pre-commit（`.pre-commit-config.yaml`）でも自動実行され、違反は fail する。

## 行末・インデント（`.gitattributes` / `.editorconfig`）

- コード（`.py .js .html .css .json .md .yml .yaml`）は **LF**。`.bat .cmd .ps1` は **CRLF**。
- インデント: Python = スペース4 / JS・HTML・CSS・JSON 等 = スペース2。
- 最終改行を入れる、行末空白を除去する。

## Python モジュール行数制限

- 1 ファイル **1500 行以内**（`tests/test_python_module_size_guard.py` が強制）。
- 超過時は分割する。やむを得ず一時的に許容する場合のみ同テストの `LEGACY_FILE_CEILINGS` に登録。
  （※ `manager/game_logic.py` は既存超過。分割は別タスク扱い。）

## テスト

```bash
pytest -q
```

`save_specific_room_state` 等の保存系はテストでモックされる前提。ルーム/戦闘ロジックを変更したら関連テストを通すこと。

全件テストは通常2分を超える。エージェントが `pytest -q` を実行する場合は、コマンド実行のタイムアウトを **600秒以上** に指定すること。

## ローカル実行

```bash
python app.py        # 開発サーバ (127.0.0.1:5000, async_mode=threading)
python app.py --update  # スキル/アイテム等マスターデータを Google Sheets から再取得
```

本番は gunicorn + eventlet（`gunicorn_config.py`, worker=1）。`/healthz` はスピンダウン防止/死活監視用の軽量エンドポイント。

## 状態管理・永続化の注意

- ルーム状態の真実は **メモリ上の `active_room_states`**。DB はその永続化。
- `save_specific_room_state` は **デバウンス**（約2秒）して書き込みを集約する。即時の DB 反映を前提にしたコードを書かないこと（読み取りはメモリ優先なので整合する）。
- worker=1 / eventlet のため、重い同期処理はイベントループ全体をブロックする点に注意。

## ドキュメント（manuals/）

- `manuals/implemented/` の仕様書は **A〜F 系統のファイルで管理**する（詳細は `manuals/README.md`）。
- 実装済み内容を追記するときは既存の系統ファイルへ節を追加する。`implemented/` に番号付きファイルを新規作成しない。
- `manuals/planned/` は未実装の計画のみ。実装完了後は計画書を削除し内容を系統ファイルへ統合する。
