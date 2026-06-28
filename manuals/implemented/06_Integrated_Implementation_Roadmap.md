# 06 新スキル提案・実装プロトコル統合ロードマップ

**種別**: implemented（2026-06-28 全完了確認）
**更新日**: 2026-06-28（原文: 2026-05-09）
**対象**: `manuals/planned/03_*`, `manuals/planned/05_*`

Phase 1 / 2-A / 2-B / 2-C（委譲）/ Phase 3（文書統合）がすべて完了したため、
`planned/` から `implemented/` へ移動。

---

## 完了状況一覧

| フェーズ | 内容 | 状態 | 確認日 |
|---|---|---|---|
| Phase 0 | 仕様同期 | ✅ 完了 | 2026-05-09 |
| Phase 1 | スキル使用可否基盤 | ✅ 完了 | 2026-06-28 |
| Phase 2-A | 震盪・`state_receive_bonus` | ✅ 完了 | 2026-06-28 |
| Phase 2-B | ラウンド条件・ランダム対象・繰り返し | ✅ 完了 | 2026-05-09 |
| Phase 2-C | 逆襲・気合い・増援 | ✅ 委譲済み（下記参照） | 2026-06-28 |
| Phase 3 | 文書統合 | ✅ 完了（B01・C01 追記） | 2026-06-28 |

---

## Phase 1: スキル使用可否基盤 ✅

**変更ファイル**:
- `manager/battle/skill_access.py` — `evaluate_skill_access()` / `list_usable_skill_ids()` / `collect_skill_constraints()` / `get_effective_skill_cost()`
- `events/battle/common_routes.py` — `battle_intent_commit` ハンドラに再検証統合
- `manager/battle/resolve_effect_runtime.py` — `_apply_cost()` が `intent['effective_cost']` を優先使用
- `manager/battle/battle_ai.py` — 独自 `list_usable_skill_ids` を廃止、`skill_access.py` に統一
- `manager/battle/select_resolve_state.py` — `_build_usable_skill_ids()` 追加、`battle_state_updated` ペイロードに `usable_skill_ids` を同梱
- `manager/battle/system_skills.py` — `SYS-STRUGGLE`（どうにかもがく）定義
- `static/js/battle/components/DeclarePanel.js` — スキルピッカーにサーバー封印チェック（`is-sealed` 表示）を追加
- `static/js/battle/core/BattleStore.js` — `usableSkillIds` をストアに追加

**完了条件**:
- 使用不可スキルが commit できない ✅
- AI が候補ゼロ時に SYS-STRUGGLE フォールバックへ正しく落ちる ✅
- フロント UI で封印スキルが `is-sealed` 表示される ✅

---

## Phase 2-A: 震盪 ✅

**変更ファイル**:
- `manager/game_logic.py` — `calculate_state_receive_bonus()` 実装、`APPLY_STATE` / `APPLY_STATE_PER_N` へ統合
- `manager/battle/buff_power.py` — コアロジック（`consume` 消費処理含む）
- `data/cache/buff_catalog_cache.json` — `Bu-29`（震盪）定義

**テスト**: `tests/test_shindou_state_receive_bonus.py` — 11件全パス

---

## Phase 2-B: ラウンド条件・ランダム対象・繰り返し ✅ (2026-05-09)

**変更ファイル**:
- `manager/game_logic.py` — `source_type="battle"` 分岐追加、`_expand_repeated_effects()` 注入
- `events/battle/common_routes.py` — `random_single` 対応
- `manager/battle/resolve_queue_helpers.py` — `resolve_random_intents()` 追加
- `manager/battle/core.py` / `resolve_auto_runtime.py` / `resolve_auto_mass_phase.py` — `resolve_random_intents()` 呼び出し追加
- `CharaCreator/json_definition_builder.html` — フィールド追加

---

## Phase 2-C: 追加スキル案の受け皿（委譲）

逆襲・気合い・増援は以下の個別 Plan に委譲済み。
各 Plan が着手・完了するまでは `planned/` に残る。

| スキル | 個別 Plan | 難易度 | 状態 |
|---|---|---|---|
| 逆襲 | `manuals/planned/12_Retaliation_Plan.md` | 小 | 未着手 |
| 気合い | `manuals/planned/13_Charge_Kiai_Plan.md` | 中 | 未着手 |
| 増援 | `manuals/planned/16_Reinforcement_Feature_Separate_Plan.md` | 大 | 未着手 |

---

## Phase 3: 文書統合 ✅

以下の実装済み正本マニュアルへ仕様を追記した（2026-06-28）:

- `manuals/implemented/B01_Skill_Logic_Core.md` — §13 スキル使用可否基盤を追加
- `manuals/implemented/C01_JSON_Definition_Master.md` — §10 SYS-STRUGGLE / `state_receive_bonus` 記法を追加

---

## 主なリスク（完了後の記録）

1. **二重管理の回避** — フロント usable_skill_ids は表示用。コミット最終判定はサーバーが正本。
2. **repeat_count と連鎖干渉** — effects_array 展開方式で回避済み（干渉なし確認）。
3. **SYS-STRUGGLE へのスキル封印適用** — システムスキルは `evaluate_skill_access` で常に usable 扱い。
