# アカウント・ルーム権限システム デプロイ／移行 運用手順書

**版**: 2026-06-26
**対象**: Render 本番デプロイ担当
**関連計画**: [`manuals/planned/26_Render_Local_Account_Management_Plan.md`](../planned/26_Render_Local_Account_Management_Plan.md)
**Typst版（PDF用）**: `manuals/typst/operations_runbook.typ`

マニュアル26（Phase 0〜7）で実装したアカウント認証・ルーム権限・公開ロビーを、
本番（Render）へ安全に投入し、既存ユーザーを移行するための手順書。

---

## 0. 大原則

1. **後方互換のまま投入する**。名前だけログインのバックエンド（`/api/entry`）は当面残す
   （UIには出さないが、緊急の安全網）。旧経路の撤去（contract）は**移行が一巡した後**に別デプロイで行う。
2. **`main` への push = Render 自動デプロイ = 本番反映**。push前に必ずバックアップとチェックリストを通す。
3. **migration は起動時に自動・冪等**。**backfill は手動**（自動実行しない）。
4. デプロイ時に **全セッションが一度失効**する（`auth_version`）。ユーザーは再ログインが必要。

---

## 1. 前提・構成

- フロントとAPI/Socketは **同一オリジン**（Flask+WhiteNoiseが単一Web Serviceで配信）。Cookieは `SameSite=Lax`+`Secure`(本番)。
- Render は **Node を持たない**。フロントは `npm run build` 済みの `static/dist/*` を**コミットして**配信する。
- 本番DBは **PostgreSQL**（`DATABASE_URL`）。未設定/非PostgreSQLなら**起動失敗（fail-closed）**。
- `worker=1`（eventlet）。レート制限はインメモリ（再起動でリセット）。

---

## 2. 必須・任意の環境変数（Render）

| 変数 | 要否 | 説明 |
|---|---|---|
| `SECRET_KEY` | 必須 | 未設定だと本番起動失敗 |
| `DATABASE_URL` | 必須 | PostgreSQL。未設定/非PGは起動失敗 |
| `CORS_ORIGINS` | 必須 | 公開ドメイン（例: `https://example.onrender.com`） |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | 必須 | 画像 |
| `GM_MASTER_KEY` | 任意 | 緊急管理用8桁。日常GM認証には使わない |
| `ACCOUNT_DISABLE_NAME_ONLY_LOGIN` | 任意 | `1` で名前だけ `/api/entry` を無効化。**Phase 8 contract まで未設定**（=有効のまま） |

---

## 3. デプロイ手順（初回・新システム投入）

1. **DBバックアップ**: Render PostgreSQL の手動バックアップを取得する。
2. **ビルド確認**: フロント変更を含む場合、`npm run build` 済みで `static/dist/*` がコミットされていること。
3. **push**: `main` へ push → Render 自動デプロイ。起動時に `run_auto_migration` が新列・新テーブルを冪等追加する（既存 `room_members` には `updated_at`/`revoked_at` を追加）。
4. **起動確認**: `/healthz` が 200。ログに migration の致命的エラーが無いこと（必須migration失敗時は起動失敗＝fail-fast）。
5. **backfill（dry-run → apply）**: Render shell で実行。

   ```bash
   python scripts/backfill_memberships.py            # dry-run（集計のみ）
   python scripts/backfill_memberships.py --apply    # 実行
   ```

   dry-run で owner不在ルーム・重複表示名・所有者不明キャラ・作成見込みを確認してから apply する。冪等なので再実行可。
6. **動作確認（本番スモーク）**: 第5章チェックリスト。

---

## 4. 既存ユーザーの移行

デプロイ直後、UIのトップは **ログイン（ID＋パスワード）** に刷新され、**名前だけ入力のUIは無い**。既存ユーザー（無パスワード）の移行経路は次の3つ。

1. **端末トークンで自動復帰**: ブラウザに保存済みの端末トークンがある利用者は、ページを開くと自動ログインされる。その後「⚙️ユーザー設定 → パスワード変更/設定」でログインID・パスワードを設定する。
2. **復旧コード**: 自動復帰できない場合、ログイン画面の「復旧」タブで名前＋復旧コード（`GEM-XXXX-XXXX`）を入力 → ログイン → ログインID・パスワード設定を案内。
3. **管理者ワンタイムコード**: 上記どちらも不可なユーザーは、app admin が管理画面でワンタイムコードを発行（実値は発行時のみ表示）。利用者は「復旧」タブの「ワンタイムコードで再設定」から再設定する。

> **注意**: `ACCOUNT_DISABLE_NAME_ONLY_LOGIN=1` を**移行前に設定しない**こと。設定すると名前だけログインのバックアップ経路も塞がる。

---

## 5. 公開前／デプロイ後チェックリスト

- [ ] `/healthz` 200、起動ログに致命的エラー無し。
- [ ] 新規登録 → ログイン → ログアウト → 再ログインが通る。
- [ ] 誤ったパスワードでログインできない（汎用エラー）。
- [ ] ルーム作成 → owner membership が作られる（`room_members`）。
- [ ] 非参加者が `/load_room` を叩けない（403）。ロビーに owner_id 等の内部情報が出ない。
- [ ] 参加コードで参加 → 入室できる。owner はコード設定/再発行/失効ができる。
- [ ] GM操作（ラウンド開始等）が GM/owner のみ、playerは不可。
- [ ] Socket: 認証なし接続が拒否される。
- [ ] backfill dry-run の集計が想定どおり（owner不在ルームは fail-closed で hidden 扱い）。
- [ ] `pytest -q` / 文字コード / 文字化け / `npm run build` 該当チェックが緑。

---

## 6. ロールバック

- 不具合時は**直前のデプロイへ戻す**。Phase 1 のスキーマは expand（追加のみ）なので、旧コードは未知の列・テーブルを無視でき、ロールバックしても整合する。
- **新規テーブル・列を即削除しない**（旧コードが無視できる expand 設計を維持）。
- contract migration（列・経路の削除）を行った後のロールバックは原則不可。実施直前に再度バックアップを取る。

---

## 7. Phase 8 contract（移行が一巡した後・別デプロイ）

移行期間を経て既存ユーザーの大半がパスワード化したら、旧経路を閉じる。

1. `ACCOUNT_DISABLE_NAME_ONLY_LOGIN=1` を設定（名前だけ `/api/entry` を停止）。
2. 再利用可能な復旧コード／旧トークン列・旧 GM PIN 経路を段階的に停止・削除。
3. `session['attribute']` 依存を検索し、認可用途が0件であることを確認（権限の正本は membership）。
4. 未使用 API（`/save_room` 等）の扱いを確定。
5. contract migration は別デプロイ・直前バックアップ必須。
6. 公開前の認証・認可・情報漏えいチェックリストを再実施。

---

## 8. 運用コマンド早見表

| 目的 | コマンド |
|---|---|
| ローカル開発起動 | `python app.py` |
| マスターデータ更新 | `python app.py --update` |
| membership dry-run | `python scripts/backfill_memberships.py` |
| membership 実行 | `python scripts/backfill_memberships.py --apply` |
| フロントビルド | `npm run build` |
| テスト | `pytest -q` |
| 文字コード/化け確認 | `python scripts/check_text_encoding.py` / `python scripts/check_mojibake_markers.py` |
