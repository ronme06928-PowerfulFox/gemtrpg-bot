# PvE Enemy Auto-Declare Implementation Plan

## 1. Scope
- 目的: PvEモードで「自動的に攻撃対象を選ぶエネミー」を、**スロット単位**で味方側スロットへ矢印表示し、必要に応じて**ラウンド開始時点で対象+スキルが宣言済み**になる状態を実現する。
- 対象: Select/Resolveフロー（`battle_state.slots`, `battle_state.intents`）を中心に実装する。
- 非対象: 旧デュエル/広域モーダル主体フローの大規模改修。

## 2. Current-State Investigation

### 2.1 PvEモード切替は存在するが、戦闘ロジック連動は薄い
- `request_switch_battle_mode` は実装済み。
  - `events/battle/common_routes.py`
  - `manager/battle/common_manager.py` (`process_switch_battle_mode`)
- ただし `battle_mode` はほぼUI表示用で、ラウンド開始時の宣言生成には未接続。

### 2.2 AIターゲット選定コードは「キャラID矢印」ベースで、現行矢印描画と系統が異なる
- `manager/battle/battle_ai.py` の `ai_select_targets` は `state['ai_target_arrows']` (`from_id`,`to_id`) を更新。
- しかし現行の矢印描画 (`static/js/visual/visual_arrows.js`) は `battle_state.intents` の **slot->slot** を描画しており、`ai_target_arrows` を参照していない。
- 結果: 既存 `ai_target_arrows` は現行UIの主要経路でほぼ未使用。

### 2.3 ラウンド開始時に敵宣言を自動確定する処理は未実装
- `process_round_start` と `process_select_resolve_round_start` はラウンド生成後、`intents` を空で開始する。
  - `manager/battle/common_manager.py`
- 旧コメントとしてPvEターゲット抽選呼び出しは残るが無効化済み。

### 2.4 AIスキル提案のSocketハンドラに欠落
- `on_request_ai_suggest_skill` は定義されているが、`@socketio.on('request_ai_suggest_skill')` デコレータがない。
  - `events/battle/common_routes.py`
- クライアントは `request_ai_suggest_skill` を送っているため、現状は受信されない可能性が高い。
  - `static/js/visual/visual_panel.js`

### 2.5 既存Select/Resolve基盤は今回要件に適合しやすい
- `intents` を `committed=True` で埋めれば、スロットバッジ・矢印・Resolve進行が既存機能で成立。
  - 矢印: `static/js/visual/visual_arrows.js`
  - 宣言UI/差分: `static/js/visual/visual_map.js`, `static/js/battle/components/DeclarePanel.js`
  - Resolve readiness: `events/battle/common_routes.py` (`_required_slots`, `_refresh_resolve_ready`)

## 3. Gap vs Requested Behavior
- 要望1: 「自動対象選択エネミーはスロットごとに味方スロットへ矢印」
  - 現状: slot矢印は実装済みだが、敵スロットのintent自動投入がない。
- 要望2: 「自動決定機能があるならラウンド開始時に対象+スキル宣言済み」
  - 現状: ラウンド開始で宣言は空。
  - 追加で、どの敵が auto-skill 対象かの判定仕様が必要。

## 4. Implementation Policy
- 方針A: **`ai_target_arrows` 依存を増やさず、`intents` に統一**する。
- 方針B: PvE時のみ、敵スロットに対してサーバー側で自動intentを生成・commitする。
- 方針C: スキル自動決定はフラグで有効化し、未有効時は「対象のみ自動、スキルは手動」の併用を許可する。

## 5. Detailed Implementation Plan

### Phase 1: Server helper for PvE auto-intents
1. 追加関数を `manager/battle/common_manager.py` に実装（例: `_apply_pve_auto_enemy_intents`）。
2. 入力:
- `state`（room_state）
- `battle_state`
- `room`（ログ/保存用）
3. 処理:
- `battle_mode != 'pve'` なら何もしない。
- `battle_state.slots` から行動可能敵スロットを抽出。
- 味方側の有効ターゲットスロットを抽出（死亡・未配置・行動不能除外）。
- 敵スロットごとにターゲットスロットを決定（初期はランダム、将来拡張可能）。
- スキル自動決定対象なら `ai_suggest_skill(char)` を使用してskill_id選択。
- 生成intentを `battle_state.intents[slot_id]` に保存し `committed=True` にする。
- `tags` は既存ルール準拠（`instant`,`mass_type`,`no_redirect`）で付与。
- `committed_by` は `"AI:PVE"` 等で識別。

### Phase 2: Round-start integration points
1. `process_round_start` の battle_state初期化直後に Phase1 helper を呼ぶ。
2. `process_select_resolve_round_start` でも同helperを呼ぶ。
- 理由: 現在2系統のラウンド開始口が存在するため、どちらからでも同結果にする。
3. 自動intent投入後、resolve準備状態を再計算できるようイベントフローを整える。

### Phase 3: Skill auto-decision gating
1. 判定フラグを定義（案）:
- `char.flags.auto_skill_select === true`
2. フラグON時のみ `ai_suggest_skill` を適用。
3. スキル未選択時のフォールバック:
- 案A: commitしない（対象のみpreview相当）
- 案B: 対象に対して既定通常攻撃を採用
- 推奨: 案A（誤スキル実行を防ぐ）

### Phase 4: Route fix for manual AI suggest
1. `events/battle/common_routes.py` にデコレータ追加:
- `@socketio.on('request_ai_suggest_skill')`
2. 既存GM補助ボタンが動作する状態に戻す。

### Phase 5: Optional UI refinements
1. 自動宣言スロットに識別表示（tooltip or badge）を追加。
2. PvE時の矢印初期表示ONを厳密化（必要であれば `battle_mode` と連動）。

## 6. Data/Rule Design
- 推奨追加フラグ（character.flags）:
- `auto_skill_select: bool`（既定false）
- `auto_target_select: bool`（既定true for enemy, 任意）
- intent構造は既存準拠:
- `slot_id`, `actor_id`, `skill_id`, `target`, `tags`, `committed`, `committed_at`, `committed_by`, `intent_rev`

## 7. Test Plan

### 7.1 Unit tests (Python)
- 追加先候補: `tests/test_pve_auto_intents.py`
- ケース:
1. PvE + 敵2スロット + 味方2スロット -> 敵2intentがcommit済みで生成される。
2. ターゲット候補なし -> 敵intentは生成されず安全終了。
3. auto_skill_select ON/OFFでskill_id挙動が変わる。
4. mass skillが選ばれた場合に `target.type` が mass系になる。

### 7.2 Flow tests
- 既存 `tests/test_select_resolve_smoke.py` に追記:
1. Round start直後、敵スロットが宣言済みとして反映される。
2. 未宣言スロット（主に味方）だけが `waiting_slots` に残る。

### 7.3 Frontend smoke
- 目視確認:
1. ラウンド開始直後に敵スロットから味方スロットへ矢印が表示。
2. DeclarePanelで敵スロットが宣言済み状態で見える。

## 8. Risks and Mitigations
- リスク: 2系統ラウンド開始の片側だけ改修し挙動が分岐。
  - 対策: helper共通化して両方から呼ぶ。
- リスク: スキル自動選択失敗時に不整合intent。
  - 対策: skill_id未決定ならcommitしないか既定スキルへ明示フォールバック。
- リスク: 旧 `ai_target_arrows` と新 `intents` の二重管理。
  - 対策: 新機能は intents を正として、`ai_target_arrows` は段階的縮退対象と明記。

## 9. Proposed Change List (Files)
- `manager/battle/common_manager.py`
- `events/battle/common_routes.py`
- `manager/battle/battle_ai.py`（必要に応じて `ai_suggest_skill` の堅牢化）
- `static/js/visual/visual_map.js`（任意: 自動宣言表示強化）
- `static/js/visual/visual_arrows.js`（任意: PvE可視性ルール調整）
- `tests/test_select_resolve_smoke.py`
- `tests/test_intent_authorization_routes.py`（必要なら補強）
- `tests/test_pve_auto_intents.py`（新規）

## 10. Acceptance Criteria
1. PvEモードでラウンド開始すると、対象自動選択エネミーの**各スロット**に宣言intentが入る。
2. マップ上に敵スロット -> 味方スロットの矢印が表示される。
3. auto_skill_select有効エネミーは、ラウンド開始時にskill_idも確定した宣言状態になる。
4. Resolve開始条件の判定が壊れず、既存Select/Resolveが継続動作する。

---
最終更新: 2026-02-23
