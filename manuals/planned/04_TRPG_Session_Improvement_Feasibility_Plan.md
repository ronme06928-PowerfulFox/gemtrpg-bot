# 04 TRPGセッション改善機能（残課題のみ）

**最終更新日**: 2026-03-30  
**位置づけ**: 本計画書は「未実装タスクのみ」を保持する。

## 1. 実装済みとして移設した内容

以下は実装完了のため、本書から詳細を削除し `implemented/` へ移設済み。

- GMによるバフ/デバフ付与・解除
- GMによるアイテム付与/没収（個数増減）
- `request_state_update` / `request_use_item` の認可強化（所有者 or GM）
- クイック編集上の GM 操作UI（バフ/アイテム管理）

移設先:

- `manuals/implemented/14_GM_Buff_Item_Operations_Spec.md`
- `manuals/implemented/02_Integrated_GM_Creator_Manual.md`（運用導線）

## 2. 現時点の残課題

- 最小回帰テストの恒常化（認可NG/GM操作OK/在庫不足など）
- `debug_apply_buff` などデバッグ導線の露出管理（本番運用の安全策）
- GM操作ログの見える化改善（必要なら別計画へ分離）

## 3. 運用ルール

- 新規に実装完了した項目は、`planned/` に詳細を残さず `implemented/` 側へ移設する。
- 本書は常に「未完了のみ」を維持する。
