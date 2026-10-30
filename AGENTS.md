# AGENTS.md

このリポジトリを編集する AI エージェント（Codex / Claude Code など）および開発者向けの共通ルール。
**作業前に必ず一読し、コミット前に該当チェックを通すこと。**


これは個人用アプリであり、開発中のPJのため後方互換やデータ移行は行わず、常に理想的かつKISSなコードに書き換えて下さい。開発は以下のサイクルで行って下さい

1. 資料を更新する。常に開発は資料ファーストで先に資料を更新して矛盾や古い情報が無いことを確認して下さい

2. テストを書く。TDDで進めてください。

3. 最小実装する。

4. 不要コード、資料矛盾がないか最終確認する。


## プロジェクト概要

- ジェムリアTRPG用ダイスボット。**Flask + Flask-SocketIO**（リアルタイム）。
- 永続化は **PostgreSQL**（本番 Render）/ ローカルは SQLite。画像は **Cloudinary**、スキル等マスターデータは **Google Sheets** から取り込み JSON キャッシュ化。
- デプロイ: **main へ push すると Render が自動デプロイ**（Render は Python 環境で **Node を持たない**）。main への push は本番反映と同じなので、エージェントは commit / push をユーザーの指示があるときだけ行う。
- バックエンド主要: `app.py`（ルート/起動）, `manager/`（ロジック層）, `events/`（Socket ハンドラ）, `models.py`。

## フロントエンド JS は必ずビルドする（最重要）

`static/index.html` は個別の JS/CSS ではなく **バンドル成果物**のみを読み込む:
`static/dist/app.bundle.js`（クラシックスクリプト連結）, `static/dist/battle.bundle.js`（`battle/index.js` の ES モジュールツリー）, `static/dist/app.bundle.css`（`styles.css` の `@import` を全インライン化）。

**ルール:**
1. JS/CSS の編集対象は **必ず `static/js/` と `static/css/`（および `static/styles.css`）のソース**。`static/dist/` の成果物は直接編集しない（ビルドで上書きされる）。
2. `static/js/*` や `static/css/*`・`styles.css` を編集したら **`npm run build` を実行**してから起動・確認・コミットする。実行しないとブラウザに反映されず、リポジトリ上でソースと成果物が不整合になる。ビルドは `index.html` の `?v=` も成果物のハッシュで書き換える。
3. ビルド成果物 `static/dist/*`（`.map` 含む）は **リポジトリにコミットする**（Render に Node が無いため）。`node_modules/` は `.gitignore` 済み。
4. **新しいクラシック JS** は `scripts/build_frontend.mjs` の `CLASSIC_SCRIPTS` 配列に依存順で追加する（ここがバンドル順の単一の正）。`index.html` に個別の `<script>` タグを書かない（バンドルと二重読み込みになり、トップレベル宣言が衝突する）。CSS の新モジュールは従来どおり `static/styles.css` に `@import` を追加すればよい（ビルドが自動でインライン化する）。
5. 連結バンドルはグローバルスコープ共有方式を保つため **識別子の mangling は無効**（空白/構文圧縮のみ）。グローバル名（`window.X` や トップレベル関数）に依存するコードは安全。
6. `static/mobile/` はバンドル対象外。モバイル版は開発停止中で `/mobile` とそのアセット配信も止めているため、編集依頼が来たら着手前にユーザーへ確認する。
7. 演出の一覧は `npm run gallery` で `/_local/fx_gallery/fx_gallery.html` を作る。本番のバンドルには入らない。
8. 解決パネルの見比べ用HTMLは `npm run resolve-preview` で作る。本番のバンドルには入らない。

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
- 超過時は分割する。やむを得ず一時的に許容する場合のみ同テストの `LEGACY_FILE_CEILINGS` に登録（現在は空）。

## テスト

```bash
pytest -q
```

`save_specific_room_state` 等の保存系はテストでモックされる前提。ルーム/戦闘ロジックを変更したら関連テストを通すこと。

全件テストは通常2分を超える。エージェントが `pytest -q` を実行する場合は、コマンド実行のタイムアウトを **300秒以上** に指定すること。

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

## 確認用の出力の片付け

マニュアル・動画・アプリのアニメーションなどの確認で作る画像・PDF・MP4の部品・ソースの写しは、ストレージを大きく使う。作ること自体はかまわないが、作業の区切り（コミット・push、段階の完了、確認の完了）ごとに整理する。

- 使い捨ての出力は、Git管理外の決まった置き場（本は `typst_manual/_local/`、動画は `typst_manual/動画/out/` と `typst_manual/動画/_local/`、演出の一覧は `/_local/fx_gallery/`、解決パネルの見本は `/_local/resolve_preview/`）か、エージェント自身の一時フォルダに出す。
- 残すのは、組み直し・作り直しに必要なもの（`typst_manual/_local/fonts/`、動画の声キャッシュなど）と、再開の目印になる最新の1点だけ。確認が済んだ画像や古い段階の写しは消す。
- 消す前に中身を確かめる。Gitにない唯一の成果物はリポジトリへ移してから消し、何を消して何を残したかを報告する。
- 別の作業者（セッション）が使っている出力は、その作業者が片付ける。
- 繰り返し使う検査は使い捨てにせず `scripts/` に置く（例：`scripts/check_ruby_clearance.py`）。

## ドキュメント（manuals/）

- `manuals/implemented/` の仕様書は **A〜F 系統のファイルで管理**する（詳細は `manuals/README.md`）。
- 実装済み内容を追記するときは既存の系統ファイルへ節を追加する。`implemented/` に番号付きファイルを新規作成しない。
- `manuals/planned/` は未実装の計画のみ。実装完了後は計画書を削除し内容を系統ファイルへ統合する。
