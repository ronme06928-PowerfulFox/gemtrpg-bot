# 10. Action Inhibition / Skill Access Plan

**最終更新日**: 2026-04-19  
**対象バージョン**: Current  
**対象機能**: 行動阻害系スキル（封印・追加コスト）

---

## 1. 目的
- 行動阻害系の仕様を「個別ギミック」ではなく共通のスキル可否判定基盤として実装する。
- UI 判定だけでなく、`battle_intent_commit` 時点でサーバー強制する。

対象要件:
- FP消費の技を使えなくする
- 要求FP+1
- コスト参照の封印
- カテゴリ参照の封印
- 距離参照の封印
- 属性参照の封印

---

## 2. 現状
### 2.1 実装済み
- 汎用コスト検証関数: `manager/battle/runtime_actions.py::verify_skill_cost`
- UI 側コスト表示/不足警告: `static/js/battle/components/DeclarePanel.js::_evaluateCost`

### 2.2 未実装
- `battle_intent_commit` での「スキル可否」サーバー判定
- スキル制約ルール (`skill_constraints`) の評価レイヤ
- 実効コスト（要求FP+1等）を UI / commit / 実消費で一貫適用する仕組み

---

## 3. 実装方針
### 3.1 新規モジュール
- `manager/battle/skill_access.py` を追加し、以下を集約する。
  - `build_skill_reference(skill_id, skill_data)`
  - `collect_skill_constraints(actor)`
  - `evaluate_skill_access(actor, skill_id, room_state=None, battle_state=None, slot_id=None)`
  - `get_effective_skill_cost(actor, skill_id, skill_data, ...)`
  - `get_usable_skill_ids(actor, ..., allow_fallback=True)`

### 3.2 ルール定義
制約データ例:

```json
[
  { "mode": "block", "match": { "cost_types": ["FP"] }, "reason": "FP消費技封印" },
  { "mode": "add_cost", "match": { "cost_types": ["FP"] }, "add_cost": [{ "type": "FP", "value": 1 }], "reason": "要求FP+1" }
]
```

`match` キー（初期対応）:
- `cost_types`
- `cost_min` / `cost_max`
- `category`
- `distance`
- `attribute`
- `skill_id`
- `tags`

### 3.3 反映ポイント
- `events/battle/common_routes.py::on_battle_intent_change_skill`
- `events/battle/common_routes.py::on_battle_intent_commit`
- `manager/battle/resolve_effect_runtime.py::_apply_cost`（実効コストの実消費）
- 必要なら state payload に `slot_skill_access` を追加

---

## 4. 実装タスク
1. `skill_access.py` 追加
2. `on_battle_intent_commit` に可否判定組み込み
3. `on_battle_intent_change_skill` にプレビュー可否反映
4. `_apply_cost` を実効コスト対応
5. テスト追加

---

## 5. テスト観点
- 封印対象スキルが commit できない
- 要求FP+1が UI 表示 / commit判定 / 実消費で一致
- mass スキル・再使用系（`USE_SKILL_AGAIN`）でも判定が破綻しない

