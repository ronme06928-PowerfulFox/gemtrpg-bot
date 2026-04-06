#set page(
  paper: "a4",
  margin: (x: 18mm, y: 16mm),
)

#set text(
  lang: "ja",
  size: 10.5pt,
)

#show heading.where(level: 1): set text(size: 18pt, weight: "bold")
#show heading.where(level: 2): set text(size: 14pt, weight: "bold")
#show heading.where(level: 3): set text(size: 11.5pt, weight: "bold")

#let section_table(title, headers, rows) = [
  == #title
  #table(
    columns: headers.len(),
    stroke: 0.4pt,
    align: left,
    ..headers.map(h => [*#h*]),
    ..rows.flatten().map(v => [#v]),
  )
]

= スキル定義・バフ定義 JSON 統合マニュアル

*版*: 2026-04-05  
*基準資料*: `manuals/implemented/15_JSON_Definition_Master.md`

== 1. 目的

この文書は、スキル定義JSON（`特記処理`）とバフ定義JSON（`effect`）を1本化し、  
編集・レビュー・運用時の基準を固定するための仕様書である。

== 2. Source of Truth

- スキル生成: `manager/data_manager.py`
- スキル実行: `manager/game_logic.py`
- スキルlint: `tests/test_skill_catalog_smoke.py`
- ターゲット範囲解釈: `events/battle/common_routes.py`
- バフ動的パターン: `manager/buff_catalog.py`

#section_table(
  "キャッシュファイル",
  ("種別", "パス"),
  (
    ("skills", "data/cache/skills_cache.json"),
    ("buff", "data/cache/buff_catalog_cache.json"),
    ("radiance", "data/cache/radiance_skills_cache.json"),
    ("passive", "data/cache/passives_cache.json"),
    ("item", "data/cache/items_cache.json"),
    ("summon", "data/cache/summon_templates_cache.json"),
  ),
)

== 3. Skill本体スキーマ

#section_table(
  "Skill基本キー",
  ("キー", "説明"),
  (
    ("スキルID", "ID"),
    ("チャットパレット", "式"),
    ("分類", "物理/魔法/防御/回避など"),
    ("距離", "近接/遠隔など"),
    ("属性", "斬撃など"),
    ("基礎威力", "定数威力"),
    ("ダイス威力", "ダイス式"),
    ("特記処理", "rule_data(JSON文字列)"),
    ("tags", "タグ配列"),
  ),
)

== 4. rule_data最小例

```json
{
  "tags": ["攻撃"],
  "cost": [{"type": "FP", "value": 2}],
  "power_bonus": [],
  "effects": []
}
```

== 5. timing / target / condition

#section_table(
  "timing一覧",
  ("timing", "用途"),
  (
    ("PRE_MATCH", "判定前"),
    ("BEFORE_POWER_ROLL", "威力ロール前"),
    ("WIN / LOSE / HIT / UNOPPOSED", "マッチ系"),
    ("AFTER_DAMAGE_APPLY", "ダメージ反映後"),
    ("RESOLVE_START / RESOLVE_STEP_END / RESOLVE_END", "Resolveフェーズ"),
    ("END_MATCH / END_ROUND", "終端処理"),
    ("IMMEDIATE / BATTLE_START", "即時/戦闘開始"),
  ),
)

#section_table(
  "target一覧",
  ("target", "対象"),
  (
    ("self", "自分"),
    ("target", "単体ターゲット"),
    ("ALL_ENEMIES", "敵全体"),
    ("ALL_ALLIES", "味方全体"),
    ("ALL_OTHER_ALLIES", "自分以外味方"),
    ("ALL", "全体"),
    ("NEXT_ALLY", "次行動の味方"),
  ),
)

#section_table(
  "condition",
  ("キー", "許容値"),
  (
    ("source", "self/target/target_skill/skill/actor_skill/relation"),
    ("operator", "CONTAINS/GTE/LTE/GT/LT/EQUALS"),
    ("param", "判定対象パラメータ名"),
    ("value", "判定値"),
  ),
)

== 6. Effect Type別仕様

#section_table(
  "Effect Typeと主要キー",
  ("type", "主要キー"),
  (
    ("APPLY_STATE", "state_name|name, value"),
    ("APPLY_STATE_PER_N", "state_name, source_param, per_N, value"),
    ("MULTIPLY_STATE", "state_name, value"),
    ("APPLY_BUFF", "buff_name または buff_id"),
    ("REMOVE_BUFF", "buff_name"),
    ("GRANT_SKILL", "skill_id, grant_mode, duration, uses"),
    ("DAMAGE_BONUS", "value"),
    ("MODIFY_ROLL", "value"),
    ("MODIFY_BASE_POWER", "value"),
    ("MODIFY_FINAL_POWER", "value"),
    ("FORCE_UNOPPOSED", "なし"),
    ("USE_SKILL_AGAIN", "max_reuses, consume_cost, reuse_cost"),
    ("CUSTOM_EFFECT", "value"),
    ("DRAIN_HP", "value(float)"),
    ("SUMMON_CHARACTER", "summon_template_id"),
  ),
)

== 7. JSON例（主要3パターン）

=== 7.1 APPLY_STATE

```json
{
  "timing": "HIT",
  "type": "APPLY_STATE",
  "target": "target",
  "state_name": "出血",
  "value": 2
}
```

=== 7.2 APPLY_BUFF + buff_id

```json
{
  "timing": "WIN",
  "type": "APPLY_BUFF",
  "target": "self",
  "buff_id": "Bu-11",
  "lasting": 2,
  "delay": 0
}
```

=== 7.3 SUMMON_CHARACTER

```json
{
  "timing": "HIT",
  "type": "SUMMON_CHARACTER",
  "target": "self",
  "summon_template_id": "T-01"
}
```

== 8. tags / target_scope

- `target_scope: same_team -> ally`
- `target_scope: opposing_team -> enemy`
- `target_scope: any -> any`
- 代表タグ: `ally_target`, `target_ally`, `enemy_target`, `target_enemy`, `no_damage`, `no_redirect`

== 9. Buff定義

#section_table(
  "Buff基本キー",
  ("キー", "説明"),
  (
    ("id", "バフID"),
    ("name", "バフ名"),
    ("description", "説明"),
    ("flavor", "フレーバー"),
    ("default_duration", "デフォルト持続"),
    ("effect", "効果定義"),
  ),
)

== 10. CUSTOM_EFFECT一覧

- 破裂爆発
- 亀裂崩壊_DAMAGE
- FISSURE_COLLAPSE
- 出血氾濫
- 戦慄殺到
- 荊棘飛散
- APPLY_SKILL_DAMAGE_AGAIN
- END_ROUND_IMMEDIATELY

== 11. バフプラグインID対応

- Bu-00 / Bu-01 / Bu-02 / Bu-03 / Bu-04 / Bu-05 / Bu-06
- Bu-07 / Bu-08 / Bu-09 / Bu-11 / Bu-12
- 別名: Bu-Provoke, Bu-Immobilize

== 12. CSV列名マップ

#section_table(
  "主要シート列",
  ("種別", "代表列"),
  (
    ("Skill", "スキルID, 分類, 距離, 属性, 特記処理"),
    ("Buff", "バフID, バフ名称, JSON定義, 持続ラウンド"),
    ("Radiance", "スキルID, JSON定義, 持続ラウンド"),
    ("Passive", "スキルID, JSON定義"),
    ("Item", "アイテムID, JSON定義, 消耗, 使用可能"),
    ("Summon", "ユニットID, 特記JSON, 持続設定"),
  ),
)

== 13. 運用チェックリスト

- [ ] `buff_id` が `buff_catalog_cache.json` に存在する
- [ ] `skill_id` が `skills_cache.json` に存在する
- [ ] `summon_template_id` が `summon_templates_cache.json` に存在する
- [ ] `CUSTOM_EFFECT.value` が `EFFECT_REGISTRY` に存在する
- [ ] `pytest -q tests/test_skill_catalog_smoke.py` が通る
- [ ] `pytest -q tests/test_target_scope_aliases.py` が通る
- [ ] `pytest -q tests/test_skill_target_tags.py` が通る

== 14. 実例カタログ（追加パターン）

=== 14.1 反撃型（LOSEで自己強化）

```json
{
  "tags": ["守備"],
  "effects": [
    {
      "timing": "LOSE",
      "type": "APPLY_BUFF",
      "target": "self",
      "buff_id": "Bu-11",
      "lasting": 1
    }
  ]
}
```

=== 14.2 同陣営支援（target_scope=same_team）

```json
{
  "tags": ["ally_target"],
  "target_scope": "same_team",
  "effects": [
    {
      "timing": "HIT",
      "type": "APPLY_STATE",
      "target": "target",
      "state_name": "FP",
      "value": 2
    }
  ]
}
```

=== 14.3 条件付き処理（HP閾値）

```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "DAMAGE_BONUS",
      "value": 3,
      "condition": {
        "source": "target",
        "param": "HP",
        "operator": "LTE",
        "value": 30
      }
    }
  ]
}
```

=== 14.4 スキル再使用（USE_SKILL_AGAIN）

```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "USE_SKILL_AGAIN",
      "max_reuses": 1,
      "consume_cost": false,
      "reuse_cost": [{"type": "FP", "value": 1}]
    }
  ]
}
```

=== 14.5 付与スキル（GRANT_SKILL）

```json
{
  "effects": [
    {
      "timing": "WIN",
      "type": "GRANT_SKILL",
      "target": "self",
      "skill_id": "Ps-10",
      "grant_mode": "usage_count",
      "uses": 1,
      "overwrite": true
    }
  ]
}
```

=== 14.6 吸収（DRAIN_HP）

```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "DRAIN_HP",
      "value": 0.5
    }
  ]
}
```

=== 14.7 状態の倍率変更（MULTIPLY_STATE）

```json
{
  "effects": [
    {
      "timing": "END_MATCH",
      "type": "MULTIPLY_STATE",
      "target": "target",
      "state_name": "出血",
      "value": 1.5
    }
  ]
}
```

=== 14.8 カスタム効果（CUSTOM_EFFECT）

```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "CUSTOM_EFFECT",
      "target": "target",
      "value": "破裂爆発"
    }
  ]
}
```

=== 14.9 召喚（SUMMON_CHARACTER）

```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "SUMMON_CHARACTER",
      "target": "self",
      "summon_template_id": "T-01",
      "summon_duration_mode": "duration_rounds",
      "summon_duration": 2
    }
  ]
}
```

=== 14.10 非ダメージ制御（no_damage）

```json
{
  "tags": ["no_damage", "ally_target"],
  "target_scope": "same_team",
  "effects": [
    {
      "timing": "WIN",
      "type": "APPLY_STATE",
      "target": "target",
      "state_name": "FP",
      "value": 2
    }
  ]
}
```

== 15. 迷ったときの設計順

1. まず `timing` を決める  
2. 次に `type` を決める  
3. `target` と `target_scope` を決める  
4. 必須キーを埋める  
5. 必要なら `condition` を追加  
6. 参照ID（`buff_id` / `skill_id` / `summon_template_id`）を検証する

== 16. AI質問セット

AIに質問するときは、次の2ファイルを一緒に渡すと誤答が減る。

- `manuals/implemented/15_JSON_Definition_Master.md`
- `manuals/implemented/18_JSON_AI_Assistant_Bundle.md`
