**最終更新日**: 2026-02-25
**対象**: GM限定・敵行動チャート自動化（ループ/条件分岐）＋プリセットJSON搬出入

---

## 1. 結論サマリ

1. 要望は**実現可能**。
2. 既存のSelect/Resolve基盤（`battle_state.intents`）とPvE自動宣言基盤（`_apply_pve_auto_enemy_intents`）があるため、敵の行動チャート実行は既存導線に乗せられる。
3. 未実装なのは主に以下。
- 敵ごとの「ラウンド別スキルチャート」定義
- チャートのループ/条件分岐エンジン
- プリセットのJSONエクスポート/インポート
- プリセット系SocketのGMサーバー権限チェック

---

## 2. 現状調査（根拠）

### 2.1 PvE自動宣言の基盤は実装済み

- `manager/battle/common_manager.py`
  - `process_round_start`
  - `process_select_resolve_round_start`
  - 上記2箇所で `_apply_pve_auto_enemy_intents` を呼び、ラウンド開始直後に敵intentを投入している。
- `_apply_pve_auto_enemy_intents` は現在、
  - 対象: 味方スロットから自動選択
  - スキル: `flags.auto_skill_select` または `flags.show_planned_skill` がONなら `ai_suggest_skill` で提案
  - `battle_state.intents` へ投入（条件により `committed=true`）

### 2.2 Selectフェーズ中のPvE敵intent補正も実装済み

- `events/battle/common_routes.py`
  - `_apply_pve_enemy_intent_defaults` により、PvE敵スロットの target/skill 補正が行われる。
  - これにより「敵ターゲットが none になっても補完する」挙動を持つ。

### 2.3 プリセット保存/読込は実装済み（機能は最小）

- `events/socket_char.py`
  - `request_save_preset`, `request_load_preset`, `request_delete_preset`, `request_get_presets`
- `static/js/modals.js`
  - `openPresetManagerModal()` で保存済みプリセットの保存/読込/削除UIあり。

### 2.4 ただしプリセット周りの不足点

- 行動チャート専用データ構造が無い（敵キャラ辞書の生保存のみ）。
- JSONエクスポート/インポート機能は未実装。
- `request_save_preset` で `state['presets'][name] = current_enemies` としており、保存時にディープコピーしていない。
- プリセット系Socketに明示的なGMサーバー権限チェックが無い（UI表示はGM制御だが、Socket直叩きの防御が不十分）。

### 2.5 既存テスト基盤

- PvE自動intent: `tests/test_pve_auto_intents.py`
- PvE敵target補正: `tests/test_pve_enemy_target_fallback_routes.py`
- AIスキル選択: `tests/test_battle_ai_skill_selection.py`

---

## 3. 要件別の実現可能性

| 要件 | 現状 | ギャップ | 実現性 |
|---|---|---|---|
| 敵ごとに1R/2R/...の使用スキルを指定 | PvE自動intentあり | ラウンドチャート定義が無い | 高 |
| 一定ラウンドパターンのループ | 同上 | ループ状態管理が無い | 高 |
| 条件でループ切替 | 条件判定ロジックは別用途で存在（`check_condition`） | 行動AI向けの遷移評価が無い | 中 |
| プリセット保存時に行動パターン同梱 | プリセット保存あり | 行動パターン専用スキーマ未定義 | 高 |
| プリセットJSON出力/他ルーム取込 | 未実装 | API/Socket/UI/検証が必要 | 中〜高 |

---

## 4. 提案データ設計

### 4.1 敵キャラに行動チャート定義を保持

`character.flags` 直下に `behavior_profile` を保持（保存/プリセット/出力に同梱しやすい）。

```json
{
  "flags": {
    "auto_target_select": true,
    "behavior_profile": {
      "enabled": true,
      "version": 1,
      "initial_loop_id": "phase_1",
      "loops": {
        "phase_1": {
          "repeat": true,
          "steps": [
            { "actions": ["SKILL_A"] },
            { "actions": ["SKILL_B"] }
          ],
          "transitions": [
            {
              "priority": 10,
              "when_all": [
                { "source": "self", "param": "HP", "operator": "LTE", "value": 50 }
              ],
              "to_loop_id": "phase_2",
              "reset_step_index": true
            }
          ]
        },
        "phase_2": {
          "repeat": true,
          "steps": [
            { "actions": ["SKILL_C"] }
          ],
          "transitions": []
        }
      }
    }
  }
}
```

補足:
- `actions` は行動回数スロット順に対応（`index_in_actor`）。
- 要素不足時は最後の値を再利用、または `null` で「未コミット」扱い。

### 4.2 実行時状態は `battle_state` に分離

ランタイムポインタはプリセット定義と分離し、`battle_state` に置く。

```json
{
  "battle_state": {
    "behavior_runtime": {
      "<actor_id>": {
        "active_loop_id": "phase_1",
        "step_index": 0,
        "last_round": 3,
        "last_skill_ids": ["SKILL_A"]
      }
    }
  }
}
```

理由:
- プリセット保存時に「定義」と「実行中カーソル」を混同しないため。
- 読込時にID再発行されても、runtimeを安全に初期化できる。

### 4.3 プリセット保存構造をv2化（後方互換あり）

現行は `state['presets'][name] = [enemy, ...]`（配列）。
新規は以下を推奨:

```json
{
  "version": 2,
  "created_at": 1760000000000,
  "enemies": [ ... ]
}
```

互換方針:
- 読込時に `list` なら legacy とみなし `enemies` に正規化。

### 4.4 エクスポートJSON形式

```json
{
  "schema": "gem_dicebot_enemy_preset.v1",
  "exported_at": "2026-02-25T00:00:00Z",
  "preset_name": "BossPhase",
  "payload": {
    "version": 2,
    "enemies": [ ... ]
  }
}
```

---

## 5. 実装計画（段階）

### Phase 0: 安全性/互換の土台

1. プリセットSocketへGM権限チェック追加（`events/socket_char.py`）。
2. プリセット正規化ヘルパー追加。
- `list` / `dict(version=2)` の両対応。
3. `request_save_preset` をディープコピー保存へ変更。

### Phase 1: 行動チャートエンジン（サーバー）

1. `manager/battle/enemy_behavior.py`（新規）
- `normalize_behavior_profile()`
- `evaluate_transitions()`
- `pick_step_actions()`
- `advance_step_pointer()`
2. 条件評価は初期版で `when_all`（AND）を実装。
- `source=self`（HP/MP/FP/状態値）
- `source=battle`（round等）

### Phase 2: ラウンド開始フロー統合

1. `manager/battle/common_manager.py`
- `_apply_pve_auto_enemy_intents` を拡張し、
  - `behavior_profile.enabled` がある敵はチャート優先
  - 未設定敵は既存ロジック（ランダム+AI提案）継続
2. 既存の呼び出し箇所（`process_round_start` / `process_select_resolve_round_start`）はそのまま利用。

### Phase 3: ループ切替/フォールバック仕様

1. 優先順位:
- 条件遷移判定 -> step選択 -> skill検証
2. スキル検証:
- 所持/コスト不可なら `fallback`（任意）
- fallback不可なら「targetのみ保持、未コミット」
3. 複数行動対応:
- `actions[index_in_actor]` を採用

### Phase 4: GM設定UI（最小実装）

1. `static/js/modals.js` のキャラ設定に「行動チャート編集」導線追加。
2. 初期版はJSONエディタ方式（構造化フォームは次段階）。
3. 保存時は `request_state_update` で `flags.behavior_profile` を更新。

### Phase 5: プリセット保存/読込への同梱

1. `request_save_preset` は敵データ丸ごと保存（`behavior_profile` 含む）。
2. `request_load_preset` はID再発行時に `behavior_runtime` を初期化。
3. プリセット読込時に `behavior_profile` のスキーマ正規化実行。

### Phase 6: JSON出力/取込

1. `events/socket_char.py` に新規イベント:
- `request_export_preset_json`
- `request_import_preset_json`
2. `static/js/modals.js` にUI追加:
- 「JSON出力」: ダウンロード
- 「JSON取込」: 貼り付けまたはファイル
3. バリデーション:
- `schema` / `version` / `payload.enemies` 必須
- 不正スキルIDは警告付きで許容（読込は可能）

### Phase 7: テストとドキュメント反映

1. 新規テスト:
- `tests/test_enemy_behavior_profile.py`
- `tests/test_preset_json_transfer.py`
- `tests/test_preset_permissions.py`
2. 既存更新:
- `tests/test_pve_auto_intents.py`（チャート優先分岐）
- `tests/test_pve_enemy_target_fallback_routes.py`（互換確認）
3. ドキュメント更新:
- `manuals/03_Integrated_Data_Definitions.md`
- `manuals/05_PvE_Mode_Spec.md`

---

## 6. 受け入れ条件（Done定義）

1. GMが敵ごとにラウンド別スキルチャートを設定できる。
2. PvEラウンド開始時、設定どおりに敵intentが投入される。
3. ループ設定が有効に循環し、条件一致時に別ループへ切替わる。
4. プリセット保存/読込で行動チャートが欠落しない。
5. プリセットをJSON出力し、別ルームで取込後に同じチャートが再現される。
6. すべてのプリセット関連操作はサーバー側でGM権限チェックされる。

---

## 7. リスクと対策

1. 既存プリセット互換性崩壊
- 対策: `list` legacyを正規化して読み込み続行。

2. 行動不能/コスト不足でintent破綻
- 対策: fallbackポリシーを実装し、最終的に未コミットへ安全退避。

3. ランタイム状態の持ち越しバグ
- 対策: `behavior_runtime` を `battle_state` 管理に限定し、プリセット定義と分離。

4. GM限定要件の抜け漏れ
- 対策: UI制御に加えてSocketハンドラで属性検証を必須化。

---

## 8. 実装優先度（推奨）

1. Phase 0（権限/互換の安全化）
2. Phase 1-3（チャート実行エンジン）
3. Phase 5（プリセット同梱の堅牢化）
4. Phase 6（JSON搬出入）
5. Phase 4（設定UIの改善を段階導入）

---

この計画は「既存PvE auto-intent基盤を壊さずに拡張する」ことを前提にしており、段階導入が可能。
