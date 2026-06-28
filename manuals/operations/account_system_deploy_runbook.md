# アカウント・ルーム権限システム デプロイ／移行 運用手順書

**版**: 2026-06-26
**対象**: Render 本番デプロイ担当
**関連計画**: [`manuals/implemented/26_Render_Local_Account_Management_Plan.md`](../implemented/26_Render_Local_Account_Management_Plan.md)
**Typst版（PDF用）**: `manuals/typst/operations_runbook.typ`

マニュアル26（Phase 0〜7）で実装したアカウント認証・ルーム権限・公開ロビーを、
本番（Render）へ投入するための手順書。

> **方針（2026-06-26 決定）**: 本番運用はまだ行っておらず、既存ユーザーは全員テスト用。
> よって**移行はせず、本番・ローカルのアカウントとルームを一度まっさらに初期化し、
> 新規登録から始める**。これにより移行期間・後方互換・backfill が不要になり、最短で
> 新システムへ切り替えられる。

---

## 0. 大原則（クリーンスタート方式）

1. **アカウント・ルームを全消去してから新システムを開始する**。既存データは全てテスト用なので保持しない。
   消去対象は users / rooms / room_members / trusted_device_tokens / one_time_login_codes。
   **画像・マスターデータ・用語辞典は保持**する。
2. 移行が無いため、**名前だけログイン（`/api/entry`）は最初から無効化**してよい（`ACCOUNT_DISABLE_NAME_ONLY_LOGIN=1`）。
3. **`main` への push = Render 自動デプロイ = 本番反映**。push前にバックアップ（保険）とチェックリストを通す。
4. **migration は起動時に自動・冪等**。空DBから始めるため **backfill は不要**（実行しても0件）。
5. 全消去後は **サーバーを再起動**してメモリ上の `active_room_states` も初期化する。

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
| `GM_MASTER_KEY` | 任意 | 緊急管理用8桁。最初の app admin 付与にも使う |
| `ACCOUNT_DISABLE_NAME_ONLY_LOGIN` | 推奨 | `1` で名前だけ `/api/entry` を無効化。クリーンスタートでは**最初から `1`** |

---

## 3. デプロイ手順（クリーンスタート）

> **本番DBの全消去は Neon の SQL Editor で直接行う**（Render の Shell は有料プランのみ）。
> ローカル(SQLite)の全消去は `scripts/reset_accounts_rooms.py --yes` を使う。

1. **バックアップ（保険）**: Neon でブランチ/バックアップを取得（テストデータだが念のため）。
2. **ビルド確認**: フロント変更を含む場合、`npm run build` 済みで `static/dist/*` がコミットされていること。
3. **環境変数**: `ACCOUNT_DISABLE_NAME_ONLY_LOGIN=1` を設定（名前だけログインを最初から無効化）。
4. **push（デプロイ）**: `main` へ push → Render 自動デプロイ。起動時に `run_auto_migration` が新列・新テーブルを冪等追加する。**新テーブル（`trusted_device_tokens`/`one_time_login_codes`）はこの初回起動で作成される**ため、全消去は必ずデプロイ後に行う。
5. **誰も接続していないことを確認**（テスト中なので任意のタイミングで可）。
6. **本番DBを全消去（Neon SQL Editor）**:

   ```sql
   TRUNCATE TABLE
     room_members, trusted_device_tokens, one_time_login_codes, rooms, users
   RESTART IDENTITY CASCADE;
   ```

   `image_registry`（画像メタ）は対象外＝保持。確認は `SELECT count(*) FROM users;` など。
7. **Render を Manual Restart**: メモリ上の `active_room_states` を空のDBから読み直させる（**TRUNCATE後に必ず再起動**。再起動はダッシュボードから無料でできる）。
   - ⚠️ 手順6と7の間に誰かが操作すると、デバウンス保存でルームが復活し得る。誰も触っていない状態で6→7を続けて行う。
8. **起動確認**: `/healthz` が 200。migration の致命的エラーが無いこと（失敗時は fail-fast で起動失敗）。
9. **動作確認（本番スモーク）**: 第5章チェックリスト。

> - ローカル環境も同様にまっさらにする場合は `python scripts/reset_accounts_rooms.py --yes`（ローカルSQLiteを消去）。
> - backfill（`scripts/backfill_memberships.py`）は**クリーンスタートでは不要**（空DBで0件）。既存ルームを引き継ぐ運用に切り替えた場合のみ使う。
> - `reset_accounts_rooms.py` は**非Render環境ではローカルSQLiteしか消さない**（DATABASE_URLを無視する設計のため）。本番Neonの消去には使えないので、本番はSQLを使う。

---

## 4. まっさら初期化と最初の管理者

全消去後、UIのトップは **ログイン（ID＋パスワード）**。全員が新規登録から始める。

1. **新規登録**: 「新規登録」タブでログインID・表示名・パスワードを作成 → そのままログイン状態になる。
2. **最初の app admin を作る**: 管理者にしたいユーザーで登録後、`GM_MASTER_KEY`（8桁）を使って
   `/api/admin/set_user_management_admin`（`{user_id, enabled:true, master_key}`）で自分に管理権限を付与する。
   以後はその管理者がユーザー管理・ワンタイムコード発行を行える。
3. **ルーム作成**: ログイン後、ロビーから新規ルーム作成（作成者が owner membership を持つ）。
   参加コードを設定して他ユーザーへ共有 → 参加者は「参加」からコード入力で参加。

> 移行（端末トークン自動復帰・復旧コード・管理者ワンタイムコード）の経路は実装済みだが、
> クリーンスタートでは使わない。将来「既存データを引き継ぐ」運用に変える場合の手段として残置。

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

## 7. Phase 8 contract（クリーンスタートでは大半が不要）

クリーンスタートでは移行経路を「使わない」ため、Phase 8 の大半は初回投入時点で実質達成済み。

- **済**: 名前だけログインは最初から無効（`ACCOUNT_DISABLE_NAME_ONLY_LOGIN=1`）。旧データは全消去済み。
- **任意（コード整理）**: 名前だけ `/api/entry`・移行用の復旧/ワンタイム経路を**将来使わないと確定したら**、関連コード・列を削除してよい（別デプロイ・直前バックアップ）。当面は残置でも害は無い（UI導線なし・フラグ無効）。
- **継続確認**: `session['attribute']` を権限の正本に使っていないこと（正本は membership）。`/save_room` 等の未使用APIの扱い。
- **公開前チェックリスト**（第5章）を本番投入時に実施。

> GM PIN はクリーンスタート後も「ルーム作成時のGM認証」「co-GMへのGM付与手段」として継続利用する（移行専用ではない）。

---

## 8. 運用コマンド早見表

| 目的 | コマンド |
|---|---|
| ローカル開発起動 | `python app.py` |
| マスターデータ更新 | `python app.py --update` |
| **ローカル全消去（dry-run/実行）** | `python scripts/reset_accounts_rooms.py [--yes]` |
| **本番(Neon)全消去** | Neon SQL Editor で `TRUNCATE TABLE room_members, trusted_device_tokens, one_time_login_codes, rooms, users RESTART IDENTITY CASCADE;` → Render再起動 |
| membership backfill（通常は不要） | `python scripts/backfill_memberships.py [--apply]` |
| フロントビルド | `npm run build` |
| テスト | `pytest -q` |
| 文字コード/化け確認 | `python scripts/check_text_encoding.py` / `python scripts/check_mojibake_markers.py` |
