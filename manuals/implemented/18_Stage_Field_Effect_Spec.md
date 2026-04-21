# 18. ステージ効果 実装済み仕様
最終更新: 2026-04-22  
対象: 戦闘専用モードのステージプリセット効果

---

## 1. 方針
ステージ効果は、戦闘専用モードのステージプリセットに紐づく場ルールです。

- 効果の発生源はステージのみです。
- ユニット由来の効果発生は扱いません。
- ステージアバターは表示専用です。
- 戦闘ロジックは `stage_field_effect_profile.rules` のみを評価します。

---

## 2. データ構造
ステージプリセットは次の追加キーを持てます。

```json
{
  "field_effect_profile": {
    "version": 1,
    "rules": []
  },
  "stage_avatar": {
    "enabled": true,
    "name": "ステージ名",
    "description": "表示説明",
    "icon": "STAGE"
  }
}
```

戦闘専用ルームでは、選択中ステージの情報が `battle_only` と戦闘状態へ反映されます。

- `battle_only.stage_field_effect_profile`
- `battle_only.stage_field_effect_enabled`
- `battle_only.stage_avatar_enabled`
- `battle_only.stage_avatar_profile`
- `state.stage_field_effect_profile`
- `state.stage_avatar_profile`
- `state.field_effects`

---

## 3. 効果ルール
`field_effect_profile.rules[]` に設定できる主なキーは次の通りです。

- `type`: 必須。効果種別。
- `scope`: 任意。`ALL` / `ALLY` / `ENEMY`。省略時は `ALL`。
- `priority`: 任意。整数。高い順で評価順を安定化します。
- `value`: 任意。効果量。実処理では整数として扱います。
- `rule_id`: 任意。ログや識別用。
- `state_name`: 状態異常付与時の状態名。
- `condition`: 条件付き効果の条件。

対応済みの `type` は次の3種類です。

- `SPEED_ROLL_MOD`: 速度ロール補正。
- `DAMAGE_DEALT_MOD`: 与ダメージ補正。
- `APPLY_STATE_ON_CONDITION`: 条件成立時に状態を付与。

`condition` は次の形です。

```json
{
  "param": "HP",
  "operator": "LTE",
  "value": 50
}
```

`operator` は `GT` / `GTE` / `LT` / `LTE` / `EQ` / `NE` を使えます。

---

## 4. ステージアバター
`stage_avatar` は実処理には影響しません。  
戦闘中にステージ効果を見つけやすくするための表示情報です。

- `enabled`: 表示有効フラグ。
- `name`: 表示名。
- `description`: 説明文。
- `icon`: 短いアイコン文字列。

---

## 5. UI
ステージプリセット管理画面では、JSONを直接書かなくてもステージ効果を編集できます。

- 効果ルールは「効果ルールを追加」で追加します。
- 初期状態では効果ルールは0件です。
- 効果ルールごとに折りたたみできます。
- 種類、対象、値、優先度、条件をフォームで設定できます。
- 上級者向けJSON編集欄はフォーム内容と同期します。

戦闘中のVisual画面では、ステージ効果カードから詳細を確認できます。

---

## 6. サンプル
```json
{
  "field_effect_profile": {
    "version": 1,
    "rules": [
      {
        "rule_id": "spd_down_1",
        "type": "SPEED_ROLL_MOD",
        "scope": "ALL",
        "priority": 100,
        "value": -1
      },
      {
        "rule_id": "dmg_up_enemy",
        "type": "DAMAGE_DEALT_MOD",
        "scope": "ENEMY",
        "priority": 50,
        "value": 2
      },
      {
        "rule_id": "bleed_low_hp",
        "type": "APPLY_STATE_ON_CONDITION",
        "scope": "ENEMY",
        "priority": 10,
        "state_name": "出血",
        "value": 1,
        "condition": {
          "param": "HP",
          "operator": "LTE",
          "value": 50
        }
      }
    ]
  },
  "stage_avatar": {
    "enabled": true,
    "name": "血霧闘技場",
    "description": "傷が開きやすい不吉な空間",
    "icon": "BLOOD"
  }
}
```

---

## 7. 実装対象
主な実装ファイルは次の通りです。

- `events/socket_battle_only.py`
- `manager/field_effects.py`
- `manager/battle/common_manager.py`
- `manager/game_logic.py`
- `static/js/modals/battle_only_stage_preset_modal.js`
- `static/js/modals/battle_only_quick_start_modal.js`
- `static/js/visual/visual_ui.js`

主なテストは次の通りです。

- `tests/test_battle_only_catalog.py`
- `tests/test_stage_field_effects_runtime.py`

