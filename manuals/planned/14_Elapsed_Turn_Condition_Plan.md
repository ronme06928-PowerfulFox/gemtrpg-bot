# 14. Elapsed Turn Condition Plan

**最終更新日**: 2026-04-19  
**対象バージョン**: Current  
**対象機能**: 経過ターン（ラウンド）を発動条件にしたスキル

---

## 1. 目的
- 「3ラウンド目以降で有効」などのターン経過条件を条件式に統合する。

---

## 2. 現状
### 2.1 実装済み
- `check_condition` の汎用評価基盤
- `self/target/target_skill/actor_skill/relation` の条件ソース

### 2.2 未実装
- 条件ソースとして `round` / `turn_elapsed` を直接参照する標準仕様
- スキルデータでの明示的な経過ターン条件運用

---

## 3. 実装方針
### 3.1 条件ソース追加
- `source: "battle"` を追加し、
  - `param: "round"`（現在ラウンド）
  - 必要なら `param: "elapsed_rounds"` を参照可能にする。

### 3.2 互換性
- 既存 condition への影響を出さない（追加のみ）
- `context` から `battle_state.round` -> `room_state.round` の順で解決

---

## 4. 実装タスク
1. `check_condition` / `_get_value_for_condition` を拡張
2. サンプルスキル定義を追加
3. 説明文とログの整備

---

## 5. テスト観点
- `round >= N` で正しく発動
- ラウンド未到達時は不発
- round情報未取得時の安全動作（False）

