# JSON定義AI質問バンドル（単体投入用）

最終更新: 2026-04-05  
用途: この1ファイルをAIに渡して、JSON定義の質問に答えさせる

---

## 1. 使い方

1. このファイル全文をAIに渡す  
2. その後に質問を書く  
3. 返答で必ず「どのルールに基づいたか」を明示させる

推奨質問テンプレート:

```text
このバンドルのルールだけを使って答えてください。
目的: {やりたい効果}
前提: {対象/タイミング/コストなど}
出力形式:
1) 完成JSON
2) 各キーの理由
3) lint観点のセルフチェック
```

---

## 2. 厳守ルール（AI向け）

以下以外の `effect.type` / `timing` / `target` を創作してはいけない。

### 2.1 `effect.type` 許可値

- `APPLY_STATE`
- `APPLY_STATE_PER_N`
- `MULTIPLY_STATE`
- `APPLY_BUFF`
- `GRANT_SKILL`
- `REMOVE_BUFF`
- `DAMAGE_BONUS`
- `MODIFY_ROLL`
- `USE_SKILL_AGAIN`
- `CUSTOM_EFFECT`
- `FORCE_UNOPPOSED`
- `MODIFY_BASE_POWER`
- `MODIFY_FINAL_POWER`
- `DRAIN_HP`
- `SUMMON_CHARACTER`

### 2.2 `timing` 許可値

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

### 2.3 `target` 許可値

- `self`
- `target`
- `ALL_ENEMIES`
- `ALL_ALLIES`
- `ALL_OTHER_ALLIES`
- `ALL`
- `NEXT_ALLY`

### 2.4 `condition` 許可値

- `source`: `self` / `target` / `target_skill` / `skill` / `actor_skill` / `relation`
- `operator`: `CONTAINS` / `GTE` / `LTE` / `GT` / `LT` / `EQUALS`

---

## 3. 参照整合ルール

- `APPLY_BUFF.buff_id` はバフカタログのIDであること
- `GRANT_SKILL.skill_id` はスキルカタログのIDであること
- `SUMMON_CHARACTER.summon_template_id` は召喚テンプレートIDであること
- `CUSTOM_EFFECT.value` は実装登録済み値であること

---

## 4. 実装登録済み CUSTOM_EFFECT

- `破裂爆発`
- `亀裂崩壊_DAMAGE`
- `FISSURE_COLLAPSE`
- `出血氾濫`
- `戦慄殺到`
- `荊棘飛散`
- `APPLY_SKILL_DAMAGE_AGAIN`
- `END_ROUND_IMMEDIATELY`

---

## 5. 実装登録済み バフプラグインID

- `Bu-00`
- `Bu-01`, `Bu-Provoke`
- `Bu-02`, `Bu-03`
- `Bu-04`, `Bu-Immobilize`
- `Bu-05`
- `Bu-06`
- `Bu-07`
- `Bu-08`
- `Bu-09`
- `Bu-11`, `Bu-12`

---

## 6. rule_data テンプレート

```json
{
  "tags": [],
  "target_scope": "opposing_team",
  "cost": [],
  "power_bonus": [],
  "effects": []
}
```

---

## 7. 実例セット（AIが参照する雛形）

### 7.1 基本: 命中で状態付与

```json
{
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

### 7.2 勝利時に自己バフ

```json
{
  "effects": [
    {
      "timing": "WIN",
      "type": "APPLY_BUFF",
      "target": "self",
      "buff_id": "Bu-11",
      "lasting": 2
    }
  ]
}
```

### 7.3 敗北時に自己強化

```json
{
  "effects": [
    {
      "timing": "LOSE",
      "type": "MODIFY_BASE_POWER",
      "target": "self",
      "value": 2
    }
  ]
}
```

### 7.4 条件付き追加ダメージ

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

### 7.5 同陣営対象支援

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

### 7.6 スキル再使用

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

### 7.7 吸収

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

### 7.8 召喚

```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "SUMMON_CHARACTER",
      "target": "self",
      "summon_template_id": "T-01"
    }
  ]
}
```

### 7.9 カスタム効果

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

---

## 8. 回答品質ルール（AI向け）

AIは回答時に必ず以下を出力する:

1. 完成JSON  
2. 採用した `timing/type/target` の理由  
3. 必須キー漏れがないかの確認  
4. 参照整合（ID）確認  
5. 代替案がある場合は1案だけ示す

