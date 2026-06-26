#import "lib/theme.typ": *

#show: doc-conf.with(
  title: "アカウント・ルーム権限システム",
  subtitle: "デプロイ／移行 運用手順書",
  meta: (
    ("版", "2026-06-26"),
    ("対象", "Render 本番デプロイ担当"),
    ("関連計画", "manuals/planned/26_Render_Local_Account_Management_Plan.md"),
    ("MD正本", "manuals/operations/account_system_deploy_runbook.md"),
  ),
)

マニュアル26（Phase 0〜7）で実装したアカウント認証・ルーム権限・公開ロビーを、本番（Render）へ投入するための手順書。

#def-box(title: "方針（2026-06-26 決定）")[
  本番運用はまだ行っておらず既存ユーザーは全員テスト用。よって*移行はせず、本番・ローカルの
  アカウントとルームを一度まっさらに初期化し、新規登録から始める*。移行期間・後方互換・backfill が
  不要になり、最短で新システムへ切り替えられる。
]

= 大原則（クリーンスタート方式）

#warn-box(title: "最重要")[
  - *アカウント・ルームを全消去してから開始*。消去対象は users / rooms / room_members / trusted_device_tokens / one_time_login_codes。*画像・マスターデータ・用語辞典は保持*。
  - 移行が無いため*名前だけログイン（#kbd("/api/entry")）は最初から無効化*してよい（#kbd("ACCOUNT_DISABLE_NAME_ONLY_LOGIN=1")）。
  - *#kbd("main") への push = Render 自動デプロイ = 本番反映*。
  - migration は起動時に自動・冪等。空DBから始めるため *backfill は不要*。
  - 全消去後は*サーバーを再起動*して #kbd("active_room_states") も初期化する。
]

= 前提・構成

- フロントとAPI/Socketは *同一オリジン*（Flask+WhiteNoiseが単一Web Serviceで配信）。Cookieは #kbd("SameSite=Lax") + #kbd("Secure")（本番）。
- Render は *Node を持たない*。フロントは #kbd("npm run build") 済みの #kbd("static/dist/*") をコミットして配信する。
- 本番DBは *PostgreSQL*（#kbd("DATABASE_URL")）。未設定/非PostgreSQLなら*起動失敗（fail-closed）*。
- #kbd("worker=1")（eventlet）。レート制限はインメモリ（再起動でリセット）。

= 必須・任意の環境変数（Render）

#table(
  columns: (auto, auto, 1fr),
  inset: (x: 6pt, y: 4pt),
  stroke: 0.5pt + luma(75%),
  table.header([*変数*], [*要否*], [*説明*]),
  [`SECRET_KEY`], [必須], [未設定だと本番起動失敗],
  [`DATABASE_URL`], [必須], [PostgreSQL。未設定/非PGは起動失敗],
  [`CORS_ORIGINS`], [必須], [公開ドメイン（例: `https://example.onrender.com`）],
  [`CLOUDINARY_*`], [必須], [画像（CLOUD_NAME / API_KEY / API_SECRET）],
  [`GM_MASTER_KEY`], [任意], [緊急管理用8桁。最初の app admin 付与にも使う],
  [`ACCOUNT_DISABLE_NAME_ONLY_LOGIN`], [推奨], [`1` で名前だけログイン無効化。クリーンスタートでは最初から `1`],
)

= デプロイ手順（クリーンスタート）

#warn-box(title: "本番の全消去は Neon で直接")[
  Render の Shell は有料プランのみ。本番DBの全消去は *Neon の SQL Editor* で直接行う。
  ローカル(SQLite)の全消去は #kbd("scripts/reset_accounts_rooms.py --yes")。
]

#steps[
  + *バックアップ（保険）*: Neon でブランチ/バックアップ（テストデータだが念のため）。
  + *ビルド確認*: フロント変更を含む場合 #kbd("npm run build") 済みで #kbd("static/dist/*") がコミット済み。
  + *環境変数*: #kbd("ACCOUNT_DISABLE_NAME_ONLY_LOGIN=1") を設定。
  + *push（デプロイ）*: #kbd("main") へ push → Render 自動デプロイ。起動時に `run_auto_migration` が冪等追加。*新テーブルはこの初回起動で作成*されるので全消去はデプロイ後。
  + 誰も接続していないことを確認。
  + *本番DBを全消去*: Neon SQL Editor で TRUNCATE（下記）。
  + *Render を Manual Restart*: #kbd("active_room_states") を空DBから読み直す（TRUNCATE後に必ず再起動。無料で可）。
  + *起動確認*: #kbd("/healthz") 200、migration致命エラー無し（失敗時 fail-fast）。
  + *動作確認*: 下記チェックリスト。
]

#ex-box(title: "本番(Neon) 全消去 SQL")[
  ```sql
  TRUNCATE TABLE
    room_members, trusted_device_tokens, one_time_login_codes, rooms, users
  RESTART IDENTITY CASCADE;
  ```
  `image_registry`（画像メタ）は対象外＝保持。
]

#warn-box[
  手順「全消去」と「再起動」の間に誰かが操作すると、デバウンス保存でルームが復活し得る。
  誰も触っていない状態で連続して行う。ローカルは #kbd("python scripts/reset_accounts_rooms.py --yes")
  （非Render環境ではローカルSQLiteのみ消去し、本番Neonには影響しない）。backfill はクリーンスタートでは不要。
]

= まっさら初期化と最初の管理者

全消去後、UIのトップは *ログイン（ID＋パスワード）*。全員が新規登録から始める。

#steps(title: "初期セットアップ")[
  + *新規登録*: 「新規登録」タブでログインID・表示名・パスワードを作成 → ログイン状態に。
  + *最初の app admin*: 管理者にしたいユーザーで登録後、#kbd("GM_MASTER_KEY") を使って
    `/api/admin/set_user_management_admin`（`{user_id, enabled:true, master_key}`）で自分に管理権限を付与。
  + *ルーム作成*: ロビーから新規作成（作成者が owner）。参加コードを設定して共有 → 参加者はコード入力で参加。
]

#note[
  移行経路（端末トークン自動復帰・復旧コード・管理者ワンタイムコード）は実装済みだが、クリーンスタートでは使わない。将来「既存データを引き継ぐ」運用へ変える場合の手段として残置。
]

= 公開前／デプロイ後チェックリスト

- #kbd("/healthz") 200、起動ログに致命的エラー無し。
- 新規登録 → ログイン → ログアウト → 再ログインが通る。
- 誤ったパスワードでログインできない（汎用エラー）。
- ルーム作成 → owner membership が作られる。
- 非参加者が #kbd("/load_room") を叩けない（403）。ロビーに owner_id 等が出ない。
- 参加コードで参加 → 入室。owner はコード設定/再発行/失効ができる。
- GM操作は GM/owner のみ、player不可。Socketは認証なし接続を拒否。
- backfill dry-run の集計が想定どおり（owner不在ルームは fail-closed で hidden）。
- `pytest -q` / 文字コード / 文字化け / `npm run build` が緑。

= ロールバック

- 不具合時は*直前のデプロイへ戻す*。Phase 1 スキーマは expand（追加のみ）で旧コードは未知の列・テーブルを無視でき整合する。
- *新規テーブル・列を即削除しない*。
- contract migration 後のロールバックは原則不可。実施直前に再バックアップ。

= Phase 8 contract（クリーンスタートでは大半が不要）

クリーンスタートでは移行経路を使わないため、Phase 8 の大半は初回投入時点で実質達成済み。

- *済*: 名前だけログインは最初から無効、旧データは全消去済み。
- *任意*: 移行用の `/api/entry`・復旧/ワンタイム経路を将来使わないと確定したらコード・列を削除（別デプロイ・直前バックアップ）。当面は残置でも無害（UI導線なし・フラグ無効）。
- *継続確認*: `session['attribute']` を権限の正本に使わない（正本は membership）。`/save_room` 等の扱い。
- 本番投入時に公開前チェックリストを実施。

#note[GM PIN はクリーンスタート後も「ルーム作成時のGM認証」「co-GMへのGM付与手段」として継続利用する（移行専用ではない）。]

= 運用コマンド早見表

#table(
  columns: (auto, 1fr),
  inset: (x: 6pt, y: 4pt),
  stroke: 0.5pt + luma(75%),
  table.header([*目的*], [*コマンド*]),
  [ローカル開発起動], [`python app.py`],
  [マスターデータ更新], [`python app.py --update`],
  [ローカル全消去(dry-run/実行)], [`python scripts/reset_accounts_rooms.py [--yes]`],
  [本番(Neon)全消去], [Neon SQL Editor で `TRUNCATE ... RESTART IDENTITY CASCADE;` → Render再起動],
  [membership backfill(通常不要)], [`python scripts/backfill_memberships.py [--apply]`],
  [フロントビルド], [`npm run build`],
  [テスト], [`pytest -q`],
  [文字コード/化け確認], [`python scripts/check_text_encoding.py` / `check_mojibake_markers.py`],
)
