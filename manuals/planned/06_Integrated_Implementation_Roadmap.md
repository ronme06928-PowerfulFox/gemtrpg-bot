# 06 新スキル提案・実装プロトコル統合ロードマップ

**更新日**: 2026-03-17  
**対象**: `manuals/planned/03_*`, `manuals/planned/05_*`
**補足**: planned/04 由来の UI/演出改善は `manuals/planned/04_TRPG_Session_Improvement_Feasibility_Plan.md`, `manuals/implemented/09_SelectResolve_Spec.md`, `manuals/implemented/06_Visual_Battle_Architecture.md` へ統合済みであり、本書の対象外とする。

---

## 1. この文書の位置づけ

本書は、Manual13 と Manual15 に残っている実装課題だけをまとめた実装ロードマップである。  
以前含めていた Manual14 由来の UI/演出改善はすでに整理済みのため、本書から除外した。

本書で扱うのは次の2系統である。

1. Manual13 由来の新スキル基盤と新効果
2. Manual15 由来の `state_receive_bonus` と文書統合プロトコル

---

## 2. 残スコープ

### 2.1 Manual13 由来

- スキル使用可否の統一判定
- `SYS-STRUGGLE` フォールバック
- `condition.source=battle,param=round`
- `target.type=random_single`
- `effects[].repeat_count`
- 追加スキル案の実装受け皿整備

### 2.2 Manual15 由来

- 新デバフ「震盪」の仕様実装
- `state_receive_bonus` の追加
- `APPLY_STATE` / `APPLY_STATE_PER_N` への受け手側補正統合
- 実装後に `03/07/08` へ仕様を戻し、図鑑系はユーザーのシート/DB更新手順として案内するプロトコル

---

## 3. 実装フェーズ

## Phase 0: 仕様同期
**目的**: 実装前に仕様の正本をそろえる。

- 更新先
  - `manuals/implemented/03_Integrated_Data_Definitions.md`
  - `manuals/implemented/08_Skill_Logic_Reference.md`
  - `manuals/implemented/09_SelectResolve_Spec.md`
- そろえる項目
  - `state_receive_bonus`
  - `condition.source=battle,param=round`
  - `target.type=random_single`
  - `effects[].repeat_count`
  - `SYS-STRUGGLE` の扱い

**完了条件**

- 03/07/08 の3冊で用語と effect JSON の意味が矛盾しない
- 以降の実装PRが参照する仕様先が明示されている

---

## Phase 1: スキル使用可否基盤
**目的**: Manual13 系スキルを安全に選択・commit できる土台を作る。

- 主な変更先
  - `manager/battle/skill_access.py`
  - `events/battle/common_routes.py`
  - `manager/battle/core.py`
  - `manager/battle/battle_ai.py`
  - `manager/battle/common_manager.py`
  - `static/js/battle/components/DeclarePanel.js`
- 実装内容
  - `evaluate_skill_access(...)` / `get_usable_skill_ids(...)`
  - commit 時の使用可否再検証
  - `_apply_cost` と整合する候補制御
  - UI はサーバー候補のみ表示
  - `SYS-STRUGGLE` を通常候補ゼロ時のフォールバックとして扱う

**完了条件**

- 使用不可スキルが commit できない
- AI が候補ゼロ時に不正状態へ落ちない
- フォールバックと通常候補が競合しない

---

## Phase 2: 新スキル仕様の実装
**目的**: Manual13 / 15 の中核ロジックを実装する。

### 2-A 震盪

- 主な変更先
  - `manager/game_logic.py`
  - スキル/バフ定義データ
- 実装内容
  - `calculate_state_receive_bonus(...)`
  - `APPLY_STATE` / `APPLY_STATE_PER_N` への受け手側補正統合
  - `consume=true` の消費処理

### 2-B ラウンド条件・ランダム対象・繰り返し

- 主な変更先
  - `manager/game_logic.py`
  - `events/battle/common_routes.py`
  - `tests/test_skill_catalog_smoke.py`
- 実装内容
  - `condition.source=battle,param=round`
  - `target.type=random_single`
  - `effects[].repeat_count`

### 2-C 追加スキル案の受け皿

- 主な変更先
  - `manager/battle/core.py`
  - `manager/battle/common_manager.py`
  - `manager/battle/duel_solver.py`
  - `manager/battle/wide_solver.py`
  - `manager/skill_effects.py`
- 実装内容
  - 新条件・新対象・新反復指定が既存解決系で破綻しないよう整備する

**完了条件**

- 震盪が仕様どおりに加算・消費される
- round/random_single/repeat_count が Select/Resolve で一貫して動作する
- 既存スキルの挙動を壊さない

---

## Phase 3: 文書統合
**目的**: Manual15 の更新プロトコルに従って、確定仕様を正本へ戻し、図鑑系はユーザー更新フローへ接続する。

- 更新先
  - `manuals/implemented/03_Integrated_Data_Definitions.md`
  - `manuals/implemented/08_Skill_Logic_Reference.md`
  - `manuals/implemented/09_SelectResolve_Spec.md`
  - 必要に応じて `manuals/implemented/01_Integrated_Player_Manual.md`
  - 必要に応じて `manuals/implemented/02_Integrated_GM_Creator_Manual.md`
  - 必要に応じて `manuals/implemented/04_Character_Build_Guide.md`
- ユーザー向け更新案内
  - Glossary シート
  - Buff Catalog シート
  - スキル正本シート
  - DB / キャッシュ反映手順

**完了条件**

- 実装内容が 03/07/08 に反映されている
- ユーザー向け・GM向け説明が必要な項目だけ 01/02/04 に戻されている
- 図鑑系データについては、AIが直接ファイル更新せず、ユーザー向けに更新手順が提示されている
- ユーザーがシート/DB反映を行う前提の確認項目まで整理されている
- 一時計画書にしか存在しない仕様が残っていない

---

## 4. 主なリスク

1. スキル候補制御と commit 再検証が二重管理になる
2. `repeat_count` と既存の連鎖ロジックが干渉する
3. `random_single` が `no_redirect` や対象消失時に曖昧になる
4. 震盪の受け手側補正と既存バフ補正の優先順が崩れる
5. 実装済みでも文書正本への反映漏れが起きる

---

## 5. PR分割案

1. **PR-1 仕様同期**: Phase 0
2. **PR-2 スキル使用可否基盤**: Phase 1
3. **PR-3 新スキル仕様実装A**: 震盪 / `state_receive_bonus`
4. **PR-4 新スキル仕様実装B**: round / random_single / repeat_count
5. **PR-5 文書統合**: Phase 3

---

## 6. Manual14 の扱い

- Manual14 由来の UI/演出改善は、本書から除外した。
- 実施結果の要約は `manuals/planned/04_TRPG_Session_Improvement_Feasibility_Plan.md`
- Select/Resolve の恒常仕様は `manuals/implemented/09_SelectResolve_Spec.md`
- Visual Battle 側の構造整理は `manuals/implemented/06_Visual_Battle_Architecture.md`

今後、UI関係の追記は 17 ではなく上記3冊へ直接反映する。
