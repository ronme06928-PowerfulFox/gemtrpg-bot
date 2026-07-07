# 04 TRPGセッション改善機能（残課題のみ）

**最終更新日**: 2026-07-07
**位置づけ**: 本計画書は「未実装タスクのみ」を保持する。

## 1. 実装済みとして移設・解消した内容

以下は実装完了のため、本書から詳細を削除し `implemented/` へ移設済み。

- GMによるバフ/デバフ付与・解除
- GMによるアイテム付与/没収（個数増減）
- `request_state_update` / `request_use_item` の認可強化（所有者 or GM）
- クイック編集上の GM 操作UI（バフ/アイテム管理）

移設先:

- `manuals/implemented/F01_Operations_Manual.md`（Part1: GMバフ・アイテム操作）
- `manuals/implemented/A02_GM_Creator_Manual.md`（運用導線）

2026-07-07 棚卸しで解消を確認した残課題:

- **認可系の回帰テスト**: `tests/test_intent_authorization_routes.py` が認可NG/GM操作OK/不正スロット拒否をカバー済み。
- **`debug_apply_buff` の露出管理**: サーバー側で在室チェック＋GM属性チェック実装済み（`events/battle/common_routes.py` の `on_debug_apply_buff`）。ソケット直叩きでも非GMは実行不可。

## 2. 現時点の残課題

- アイテム在庫不足（個数0で使用/没収）まわりの回帰テスト追加（認可系テストは上記のとおり実装済み）
- GM操作ログの見える化改善
  - `planned/28_TRPG_Play_Experience_Improvement_Plan.md` P1-3（限定undo・操作履歴）と実装が重なるため、着手時に28へ吸収するか判断する（28 §7 参照）

## 3. 運用ルール

- 新規に実装完了した項目は、`planned/` に詳細を残さず `implemented/` 側へ移設する。
- 本書は常に「未完了のみ」を維持する。
