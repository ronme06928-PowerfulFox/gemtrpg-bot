# 15. JSON定義マスター（Skill/Buff中心）

最終更新: 2026-04-08  
対象: 実装済み（Current）

---

## 0. この資料の目的

このドキュメントは、以下を一元化するための「大元資料」です。

- スキル定義JSON（`skills_cache.json` の `特記処理`）
- バフ定義JSON（`buff_catalog_cache.json` の `effect`）
- 関連参照（付与スキル/召喚/コスト/ターゲット範囲）

実装コード・テストを基準に、現行仕様として整理しています。

---

## 1. Source of Truth（実装基準）

データ生成/ロード:

- スキル生成: `manager/data_manager.py` (`fetch_and_save_sheets_data`)
- スキル実行: `manager/game_logic.py` (`process_skill_effects`)
- スキルlint: `tests/test_skill_catalog_smoke.py`
- ターゲット範囲解釈: `events/battle/common_routes.py`, `manager/battle/skill_rules.py`
- バフローダー: `manager/buffs/loader.py`
- バフ動的パターン: `manager/buff_catalog.py`

キャッシュ格納先:

- `data/cache/skills_cache.json`
- `data/cache/buff_catalog_cache.json`
- `data/cache/radiance_skills_cache.json`
- `data/cache/passives_cache.json`
- `data/cache/items_cache.json`
- `data/cache/summon_templates_cache.json`

2026-04-05 時点のキャッシュ件数（ローカル確認値）:

- Skills: 102
- Buffs: 29
- Radiance: 9
- Passives: 2
- Items: 2
- Summon templates: 2

---

## 2. Skill本体スキーマ（`skills_cache.json`）

1スキルの基本キー:

- `スキルID`
- `チャットパレット`
- `デフォルト名称`
- `分類`
- `距離`
- `属性`
- `取得コスト`
- `基礎威力`
- `ダイス威力`
- `使用時効果`
- `発動時効果`
- `特記`
- `特記処理`（JSON文字列）
- `tags`（配列）

実運用では `特記処理` がJSON文字列で保存されるため、編集時はJSON整形してから貼り付けること。

---

## 3. `特記処理`（rule_data）トップレベル

現行で使われているトップキー:

- `tags`
- `cost`
- `power_bonus`
- `effects`
- `target_scope`

最小例:

```json
{
  "tags": ["攻撃"],
  "cost": [{"type": "FP", "value": 2}],
  "power_bonus": [],
  "effects": []
}
```

---

## 4. `effects[]` 共通仕様

各要素は object。共通キー:

- `timing`（必須）
- `type`（必須）
- `target`（任意）
- `condition`（任意）

`timing` 許可値（lint基準）:

- `PRE_MATCH`
- `BEFORE_POWER_ROLL`
- `WIN`
- `LOSE`
- `HIT`
- `UNOPPOSED`
- `AFTER_DAMAGE_APPLY`
- `RESOLVE_START`
- `RESOLVE_STEP_END`
- `RESOLVE_END`
- `END_MATCH`
- `END_ROUND`
- `IMMEDIATE`
- `BATTLE_START`

`target` 許可値（lint基準）:

- `self`
- `target`
- `ALL_ENEMIES`
- `ALL_ALLIES`
- `ALL_OTHER_ALLIES`
- `ALL`
- `NEXT_ALLY`

---

## 5. `condition` 仕様

形:

```json
{
  "source": "target",
  "param": "HP",
  "operator": "LTE",
  "value": 30
}
```

`source`:

- `self`
- `target`
- `target_skill`
- `skill`（=`actor_skill`）
- `actor_skill`
- `relation`

`operator`:

- `CONTAINS`
- `GTE`
- `LTE`
- `GT`
- `LT`
- `EQUALS`

---

## 6. Effect Type別 必須/主要キー

### 6.1 状態系

- `APPLY_STATE`
  - 必須: `state_name`（または `name`）, `value`
  - 例: `{"type":"APPLY_STATE","timing":"HIT","target":"target","state_name":"出血","value":2}`
- `APPLY_STATE_PER_N`
  - 必須: `state_name`, `source_param`, `per_N`, `value`
  - 推奨: `source`（`self` or `target`）, `max_value`
- `MULTIPLY_STATE`
  - 必須: `state_name`, `value`（数値）

### 6.2 バフ/スキル付与

- `APPLY_BUFF`
  - 必須: `buff_name` または `buff_id`
  - 任意: `lasting`, `delay`, `data`
  - スタック付与が必要な場合は `data.count` を使用
    - 例: 震盪2スタック付与 -> `{"type":"APPLY_BUFF","buff_name":"震盪","data":{"count":2}}`
- `REMOVE_BUFF`
  - 必須: `buff_name`
- `GRANT_SKILL`
  - 必須: `skill_id`（または `grant_skill_id`）
  - 任意: `grant_mode`, `duration`, `uses`, `overwrite`, `custom_name`
  - `grant_mode`: `permanent` / `duration_rounds` / `usage_count`

### 6.3 威力/ダメージ

- `DAMAGE_BONUS`
  - 必須: `value`（int）
- `MODIFY_ROLL`
  - 必須: `value`（int）
- `MODIFY_BASE_POWER`
  - 必須: `value`（int）
- `MODIFY_FINAL_POWER`
  - 必須: `value`（int）
- `DRAIN_HP`
  - 必須: `value`（float, 例 `0.5`）

### 6.4 制御/拡張

- `FORCE_UNOPPOSED`
  - 追加キーなし
- `USE_SKILL_AGAIN`
  - 任意: `max_reuses`, `consume_cost`, `reuse_cost`
- `CUSTOM_EFFECT`
  - 必須: `value`（効果名）
- `SUMMON_CHARACTER`
  - 必須: `summon_template_id`（または `template_id` / `summon_id`）
  - 任意: 座標、期間、初期スキル、SPassive、params など

---

## 7. `tags` と対象範囲/挙動

代表タグ:

- `攻撃`, `守備`
- `ally_target`, `target_ally`, `味方対象`, `同陣営対象`
- `enemy_target`, `target_enemy`, `敵対象`, `相手陣営対象`
- `no_redirect`, `対象変更不可`
- `no_damage`, `non_damage`, `非ダメージ`
- `mass_individual`, `mass_summation`（または同義語）

`target_scope` の解釈:

- `same_team` -> `ally`
- `opposing_team` -> `enemy`
- `any` -> `any`

同陣営対象スキルは Select/Resolve の redirect 対象外として扱われる。

---

## 8. `cost` と `power_bonus`

`cost`:

```json
[{"type":"HP","value":5},{"type":"FP","value":2}]
```

`power_bonus` ルール:

- `operation`: `FIXED` / `MULTIPLY` / `FIXED_IF_EXISTS` / `PER_N_BONUS`
- `apply_to`: `base` / `dice` / `final`（未指定は `base`）
- 任意: `condition`, `max_bonus`, `min_bonus`

---

## 9. Buff定義（`buff_catalog_cache.json`）

1エントリの基本キー:

- `id`
- `name`
- `description`
- `flavor`
- `default_duration`
- `effect`

`effect` の現行主タイプ:

- `type: "stat_mod"`
  - 例: `{"type":"stat_mod","stat":"基礎威力","value":1}`
- `type: "plugin"`
  - 例: `{"type":"plugin","name":"immobilize","category":"control"}`

補助キー（バフにより任意）:

- `category`
- `name`
- `damage_multiplier`
- `restore_mp_on_end`

---

## 10. 動的バフ命名規則（`manager/buff_catalog.py`）

代表パターン:

- `_AtkN` / `_DefN`
- `_AtkDownN` / `_DefDownN`
- `_PhysN` / `_PhysDownN`
- `_MagN` / `_MagDownN`
- `_ActN`
- `_DaInN` / `_DaCutN` / `_DaOutN` / `_DaOutDownN`
- `_CrackN` / `_CrackOnceN`
- `_BleedReactN`

例:

- `Power_Atk5` -> 攻撃系最終威力 +5
- `Guard_DaCut20` -> 被ダメージ 0.8 倍

---

## 11. 参照整合ルール（壊れやすい箇所）

- `APPLY_BUFF.buff_id` は `buff_catalog_cache.json` のIDと一致させる
- `GRANT_SKILL.skill_id` は `skills_cache.json` のIDと一致させる
- `SUMMON_CHARACTER.summon_template_id` は `summon_templates_cache.json` のIDと一致させる
- `CUSTOM_EFFECT.value` は `plugins/__init__.py` の `EFFECT_REGISTRY` に存在させる

---

## 12. 実運用チェック（推奨）

スキル定義変更時は最低限これを実行:

```powershell
pytest -q tests/test_skill_catalog_smoke.py
pytest -q tests/test_target_scope_aliases.py
pytest -q tests/test_skill_target_tags.py
```

---

## 13. 編集テンプレート（コピペ用）

```json
{
  "tags": ["攻撃"],
  "target_scope": "opposing_team",
  "cost": [{"type":"FP","value":2}],
  "power_bonus": [],
  "effects": [
    {
      "timing": "HIT",
      "type": "APPLY_STATE",
      "target": "target",
      "state_name": "出血",
      "value": 2
    }
  ]
}
```

---

## 14. CUSTOM_EFFECT 一覧（実装登録済み）

`plugins/__init__.py` の `EFFECT_REGISTRY` 基準:

- `破裂爆発`
- `亀裂崩壊_DAMAGE`
- `FISSURE_COLLAPSE`
- `出血氾濫`
- `戦慄殺到`
- `荊棘飛散`
- `APPLY_SKILL_DAMAGE_AGAIN`
- `END_ROUND_IMMEDIATELY`

---

## 15. バフプラグインID対応（実装登録済み）

`plugins/buffs/*.py` の `BUFF_IDS` 基準:

- `Bu-00`（stat_mod）
- `Bu-01`, `Bu-Provoke`（provoke）
- `Bu-02`, `Bu-03`（confusion）
- `Bu-04`, `Bu-Immobilize`（immobilize）
- `Bu-05`（dodge_lock）
- `Bu-06`（burst_no_consume）
- `Bu-07`（time_bomb）
- `Bu-08`（bleed_maintenance）
- `Bu-09`（implosion）
- `Bu-11`, `Bu-12`（speed_mod）

---

## 16. CSV列名マップ（ローダー基準）

### 16.1 スキル（`manager/data_manager.py`）

読み取り列（代表）:

- `スキルID`
- `チャットパレット`
- `デフォルト名称`
- `分類`
- `距離`
- `属性`
- `取得コスト`
- `基礎威力`
- `ダイス威力`
- `使用時効果`
- `特記`
- `発動時効果`
- `特記処理`

### 16.2 バフ（`manager/buffs/loader.py`）

- `バフID`
- `バフ名称`
- `バフ説明`
- `フレーバーテキスト`
- `JSON定義`
- `持続ラウンド`

### 16.3 輝化（`manager/radiance/loader.py`）

- `スキルID`
- `スキル名`
- `習得コスト`
- `スキル効果`
- `フレーバーテキスト`
- `JSON定義`
- `持続ラウンド`

### 16.4 パッシブ（`manager/passives/loader.py`）

- `スキルID`
- `スキル名`
- `習得コスト`
- `スキル効果`
- `フレーバーテキスト`
- `JSON定義`

### 16.5 アイテム（`manager/items/loader.py`）

- `アイテムID`
- `アイテム名`
- `効果説明`
- `フレーバーテキスト`
- `JSON定義`
- `消耗`
- `使用可能`
- `ラウンド制限`

### 16.6 召喚テンプレート（`manager/summons/loader.py`）

代表列:

- `ユニットID`
- `表示名`
- `HP`, `最大HP`
- `MP`, `最大MP`
- `速度`
- `物理補正`, `魔法補正`
- `戦闘スキル`
- `パッシブスキル`
- `輝化スキル`
- `秘匿スキル`
- `所持アイテム`
- `持続設定`
- `重複`
- `特記JSON`

---

## 17. 補足

本資料は「Skill/Buff中心」の統合版です。  
アイテム/輝化/パッシブ/召喚/用語辞書は次版で同一フォーマット化し、同じ章立て（キー一覧・必須条件・lint条件）に揃える。

---

## 18. 震盪（W-64）JSON定義

### 18.1 バフ定義（buff catalog / effect）

`震盪` は受け手側補正のため、`effect.state_receive_bonus` で定義する。

```json
{
  "id": "Bu-XX",
  "name": "震盪",
  "description": "受ける破裂付与量 +N",
  "effect": {
    "state_receive_bonus": [
      {
        "stat": "破裂",
        "operation": "FIXED",
        "value": 2,
        "consume": false
      }
    ]
  },
  "default_duration": 3
}
```

### 18.2 スキル側定義（特記処理 / rule_data）

ユーザー要件の例（使用時FP2/MP3、勝利時に震盪2スタック3R、命中時に破裂3）:

```json
{
  "tags": [],
  "target_scope": "opposing_team",
  "cost": [
    { "type": "FP", "value": 2 },
    { "type": "MP", "value": 3 }
  ],
  "power_bonus": [],
  "effects": [
    {
      "timing": "WIN",
      "type": "APPLY_BUFF",
      "target": "target",
      "buff_name": "震盪",
      "lasting": 3,
      "delay": 0,
      "data": { "count": 2 }
    },
    {
      "timing": "HIT",
      "type": "APPLY_STATE",
      "target": "target",
      "state_name": "破裂",
      "value": 3
    }
  ]
}
```

### 18.3 挙動上の注意

- `state_receive_bonus` は「受ける側（target）」の `special_buffs` を参照する。
- 破裂増量は正値付与（`APPLY_STATE` / `APPLY_STATE_PER_N`）時のみ適用される。
- `consume: true` を指定した場合、増量適用時に受け手側の震盪バフが消費される。
- `Bu-29` を再付与した場合:
  - `count` は加算される（`data.count` 省略時は +1）。
  - `lasting` は `max(既存, 新規)` が採用される。
