# 17. Unified Field Effects Plan (Aura + Battle Only Stage)
最終更新: 2026-04-20  
対象: planning

---

## 1. 目的
- フィールド効果を単一仕様に統合する。
- 対象は次の2系統を同時に扱う。
  - `ステージ由来`: 戦闘専用モードでステージごとに事前設定する場ルール
  - `ユニット由来`: 場に配置されたユニットが発生させるオーラ/領域効果
- 目標は「同じエンジンで評価し、同じログ規約で可視化する」こと。

---

## 2. 統合コンセプト
- 実行時はすべて `field_effects` に正規化して処理する。
- 由来は `source_type` で識別する。
  - `source_type = "stage_preset"`
  - `source_type = "field_unit"`
- これにより、仕様分岐を増やさずに拡張できる。

---

## 3. データモデル
## 3.1 戦闘状態 (共通)
```json
{
  "field_effects": [
    {
      "field_id": "fe_stage_001",
      "name": "暴風域",
      "source_type": "stage_preset",
      "source_id": "bos_ruins_storm",
      "scope": "ALL",
      "priority": 100,
      "duration_rounds": -1,
      "effects": [
        { "type": "SPEED_ROLL_MOD", "value": -1 }
      ]
    },
    {
      "field_id": "fe_unit_001",
      "name": "重力柱",
      "source_type": "field_unit",
      "source_id": "char_obj_123",
      "scope": "ALL",
      "priority": 120,
      "duration_rounds": 3,
      "effects": [
        { "type": "DAMAGE_DEALT_MOD", "value": 1 }
      ]
    }
  ]
}
```

## 3.2 Battle Only のステージプリセット
`stage_presets.<stage_id>` に任意で以下を持たせる。

```json
{
  "field_effect_profile": {
    "version": 1,
    "rules": [
      { "type": "SPEED_ROLL_MOD", "scope": "ALL", "value": -1, "priority": 100 },
      { "type": "DAMAGE_DEALT_MOD", "scope": "ENEMY", "value": 1, "priority": 90 }
    ]
  }
}
```

## 3.3 Battle Only のルーム状態
`room_state.battle_only` に以下を追加。
- `stage_field_effect_profile` (選択ステージ由来の定義)
- `stage_field_effect_enabled` (boolean, default: `true`)

---

## 4. 処理フロー
1. `request_bo_select_stage_preset`  
`field_effect_profile` を `battle_only.stage_field_effect_profile` へ反映
2. `request_bo_start_battle`  
`stage_field_effect_enabled == true` の場合、ステージ定義を `field_effects` に注入
3. 戦闘中  
ユニット配置/消滅に応じて `source_type = "field_unit"` の効果を追加/除去
4. 評価  
`field_context` 集約で両系統を同時評価

---

## 5. 適用順序 (固定仕様)
1. 基礎値計算
2. 通常バフ (`special_buffs`)
3. フィールド効果 (`field_effects`)
4. clamp (下限/上限)
5. ログ出力

同一タイミング優先順:
- `priority desc`
- 同順位は `source_type`, `source_id`, `field_id` で安定ソート

---

## 6. 最小対応する効果タイプ
- `SPEED_ROLL_MOD`
- `DAMAGE_DEALT_MOD`
- `APPLY_STATE_ON_CONDITION`

後続で追加する候補:
- 被ダメージ補正
- 範囲条件 (地形座標依存)
- 連鎖トリガー

---

## 7. API / イベント拡張
## 7.1 既存イベント payload 追加
- `request_bo_stage_preset_save.payload.field_effect_profile` (optional)
- `bo_stage_preset_saved.record.field_effect_profile`
- `bo_stage_preset_selected.stage_preset.field_effect_profile`
- `bo_draft_state.battle_only.stage_field_effect_profile`
- `bo_draft_state.battle_only.stage_field_effect_enabled`

## 7.2 任意の新規イベント
- `request_bo_set_stage_field_effect_enabled`
  - ステージ効果の ON/OFF
  - GM 権限限定

---

## 8. UI計画
対象:
- `static/js/modals/battle_only_stage_preset_modal.js`
- `static/js/modals/battle_only_quick_start_modal.js`

最小実装:
- ステージ編集に `field_effect_profile` JSON 入力欄
- クイックスタートに効果有効/無効トグル
- ステージ一覧で「効果あり」バッジ表示

---

## 9. 実装フェーズ
## Phase 1: 統合基盤
- `field_effects` 共通ランタイムを追加
- ステージ由来注入を `request_bo_start_battle` に実装
- ユニット由来の追加/削除 API を最小実装

## Phase 2: 評価経路接続
- 速度ロールへ `SPEED_ROLL_MOD`
- ダメージ経路へ `DAMAGE_DEALT_MOD`
- 条件付き状態異常へ `APPLY_STATE_ON_CONDITION`

## Phase 3: UI / 運用
- ステージ編集 UI 拡張
- ON/OFF 操作
- ログ表記統一

## Phase 4: 制約と安定化
- バリデータ厳格化
- 件数上限とサイズ上限
- 回帰テスト固定

---

## 10. テスト計画
## 10.1 単体
- ステージ保存: `field_effect_profile` 正常/異常
- ステージ選択: `battle_only.stage_field_effect_profile` 反映
- 戦闘開始: ON/OFF で注入有無が変わる
- 優先度順と安定ソートが維持される

## 10.2 統合
- ステージ効果 + ユニット効果が同時適用される
- 速度 -> 行動順 -> ダメージまで一貫反映
- 多重発火が抑止される

## 10.3 回帰
- 既存 Battle Only ステージ選択/開始テストが維持される
- `special_buffs` 系の既存挙動に影響しない

---

## 11. リスクと対策
- リスク: ステージJSON肥大化
  - 対策: `rules` 件数上限、ペイロードサイズ制限
- リスク: 多重適用
  - 対策: `event_id + field_id + target_id` で抑止
- リスク: 表示と実処理の乖離
  - 対策: ログに `source_type/source_id/差分` を必須出力
- リスク: 後方互換破壊
  - 対策: 新規キーは optional、未設定時は no-op

---

## 12. 受け入れ基準
1. 戦闘専用モードでステージ単位のフィールド効果を保存/読込できる。  
2. 戦闘開始時にステージ由来効果が `field_effects` へ正しく注入される。  
3. 場に配置されたユニット由来効果が同一エンジンで適用される。  
4. 両者が同時に有効でも優先度規約どおり安定動作する。  
5. 既存ステージと既存バフ挙動に回帰がない。  

