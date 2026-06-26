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

マニュアル26（Phase 0〜7）で実装したアカウント認証・ルーム権限・公開ロビーを、本番（Render）へ安全に投入し、既存ユーザーを移行するための手順書。

= 大原則

#warn-box(title: "最重要")[
  - *後方互換のまま投入する*。名前だけログインのバックエンド（#kbd("/api/entry")）は当面残す（UIには出さない安全網）。旧経路の撤去（contract）は*移行が一巡した後*に別デプロイで行う。
  - *#kbd("main") への push = Render 自動デプロイ = 本番反映*。push前に必ずバックアップとチェックリストを通す。
  - migration は起動時に自動・冪等。*backfill は手動*（自動実行しない）。
  - デプロイ時に*全セッションが一度失効*する（#kbd("auth_version")）。再ログインが必要。
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
  [`GM_MASTER_KEY`], [任意], [緊急管理用8桁。日常GM認証には使わない],
  [`ACCOUNT_DISABLE_NAME_ONLY_LOGIN`], [任意], [`1` で名前だけログイン無効化。Phase 8 contract まで未設定],
)

= デプロイ手順（初回・新システム投入）

#steps[
  + *DBバックアップ*: Render PostgreSQL の手動バックアップを取得する。
  + *ビルド確認*: フロント変更を含む場合、#kbd("npm run build") 済みで #kbd("static/dist/*") がコミット済みであること。
  + *push*: #kbd("main") へ push → Render 自動デプロイ。起動時に `run_auto_migration` が新列・新テーブルを冪等追加（既存 `room_members` には `updated_at`/`revoked_at` を追加）。
  + *起動確認*: #kbd("/healthz") が 200。必須migration失敗時は起動失敗（fail-fast）。
  + *backfill（dry-run → apply）*: Render shell で実行。
  + *動作確認*: 下記チェックリスト。
]

#ex-box(title: "backfill コマンド")[
  ```bash
  python scripts/backfill_memberships.py          # dry-run（集計のみ）
  python scripts/backfill_memberships.py --apply  # 実行（冪等・再実行可）
  ```
  dry-run で owner不在ルーム・重複表示名・所有者不明キャラ・作成見込みを確認してから apply する。
]

= 既存ユーザーの移行

デプロイ直後、UIのトップは *ログイン（ID＋パスワード）* に刷新され、名前だけ入力のUIは無い。既存ユーザー（無パスワード）の移行経路は次の3つ。

#steps(title: "移行経路")[
  + *端末トークンで自動復帰*: ブラウザに保存済みトークンがあれば自動ログイン → 「⚙️ユーザー設定」でログインID・パスワード設定。
  + *復旧コード*: 「復旧」タブで名前＋復旧コード（`GEM-XXXX-XXXX`）→ ログイン → パスワード設定。
  + *管理者ワンタイムコード*: 上記不可なら app admin が発行（実値は発行時のみ表示）→「ワンタイムコードで再設定」。
]

#warn-box[
  #kbd("ACCOUNT_DISABLE_NAME_ONLY_LOGIN=1") を*移行前に設定しない*こと。名前だけログインのバックアップ経路も塞がる。
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

= Phase 8 contract（移行が一巡した後・別デプロイ）

#steps[
  + #kbd("ACCOUNT_DISABLE_NAME_ONLY_LOGIN=1") を設定（名前だけ `/api/entry` 停止）。
  + 再利用可能な復旧コード／旧トークン列・旧 GM PIN 経路を段階的に停止・削除。
  + `session['attribute']` 依存を検索し、認可用途が0件であることを確認。
  + 未使用 API（`/save_room` 等）の扱いを確定。
  + contract migration は別デプロイ・直前バックアップ必須。
  + 公開前チェックリストを再実施。
]

= 運用コマンド早見表

#table(
  columns: (auto, 1fr),
  inset: (x: 6pt, y: 4pt),
  stroke: 0.5pt + luma(75%),
  table.header([*目的*], [*コマンド*]),
  [ローカル開発起動], [`python app.py`],
  [マスターデータ更新], [`python app.py --update`],
  [membership dry-run], [`python scripts/backfill_memberships.py`],
  [membership 実行], [`python scripts/backfill_memberships.py --apply`],
  [フロントビルド], [`npm run build`],
  [テスト], [`pytest -q`],
  [文字コード/化け確認], [`python scripts/check_text_encoding.py` / `check_mojibake_markers.py`],
)
