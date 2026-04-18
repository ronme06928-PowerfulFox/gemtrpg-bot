# 11. Fallback Struggle Plan

**最終更新日**: 2026-04-19  
**対象バージョン**: Current  
**対象機能**: 何も使えない状態専用の特殊スキル（わるあがき）

---

## 1. 目的
- 全スキル封印やコスト不足時に行動不能で進行停止しないよう、フォールバック技を保証する。

---

## 2. 現状
### 2.1 実装済み
- スキル候補抽出は `commands` / 付与スキルを起点に動作している。

### 2.2 未実装
- `SYS-STRUGGLE` のシステムスキル定義
- 「通常候補ゼロ時だけ出す」フォールバックロジック
- フォールバックを封印対象外にするルール

---

## 3. 実装方針
- システムスキルID: `SYS-STRUGGLE`
- 性質:
  - 無コスト
  - 単体固定ダメージ（最小限）
  - `system_fallback` タグを付与
  - 通常の封印ルールから除外

ロジック:
- `get_usable_skill_ids(..., allow_fallback=True)` で通常候補が空なら `SYS-STRUGGLE` を返す
- `allow_fallback=False` の呼び出しでは返さない

---

## 4. 実装タスク
1. `SYS-STRUGGLE` データを追加（ロード対象に含める）
2. `skill_access.py` 側に fallback 返却条件を実装
3. Declare UI で fallback 表示確認
4. commit/resolve で通常スキル同様に処理できることを確認

---

## 5. テスト観点
- 全封印時に `SYS-STRUGGLE` のみ選択可能
- `resolve_ready` が詰まらない
- 通常スキルが1つでもある場合は fallback が出ない

