# C02. Retaliation Passive Sheet Examples

**作成日**: 2026-05-11  
**対象**: 特殊パッシブシートの `JSON効果` 記入例  
**主題**: `on_damage_reaction` の実用例

---

## 1. 前提

特殊パッシブシートでは、`JSON効果` 列に `effect` オブジェクト本体をそのまま入れる。

スキル JSON のような `schema` や `effects` の外枠は不要。

---

## 2. 最小例

### 被弾時、攻撃者に 3 ダメージ

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "damage": 3
  }
}
```

---

## 3. 状態異常付与

### 被弾時、攻撃者に出血 2

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "apply_state": [
      { "name": "出血", "value": 2 }
    ]
  }
}
```

### 被弾時、攻撃者に 2 ラウンドの亀裂 1

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "apply_state": [
      { "name": "亀裂", "value": 1, "rounds": 2 }
    ]
  }
}
```

注意:

- `亀裂` は `rounds` 必須
- `rounds` が無い正の `亀裂` は不発になる

---

## 4. 複合例

### 被弾時、攻撃者に 2 ダメージと出血 2

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "damage": 2,
    "apply_state": [
      { "name": "出血", "value": 2 }
    ]
  }
}
```

### 被弾時、攻撃者に出血 2 と 2 ラウンドの亀裂 1

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "apply_state": [
      { "name": "出血", "value": 2 },
      { "name": "亀裂", "value": 1, "rounds": 2 }
    ]
  }
}
```

---

## 5. バフ付与

### 被弾時、攻撃者に `Bu-58` を付与

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "apply_buff": [
      {
        "buff_id": "Bu-58",
        "buff_name": "毒晶侵食",
        "lasting": 2,
        "delay": 0,
        "data": { "value": 2 }
      }
    ]
  }
}
```

---

## 6. 条件付き

### 1 以上の実ダメージを受けた時だけ反応

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "damage": 3,
    "condition": {
      "damage_gte": 1
    }
  }
}
```

現時点で正式対応している条件は `damage_gte` のみ。

---

## 7. 現在の運用ルール

- 被弾反応の `亀裂` は通常スキルの「1 ラウンド 1 回の亀裂付与制限」とは別枠
- 戦闘ログはプレイヤー向けの自然文で出力する
- `target` は基本的に `attacker` を使う

---

## 8. 推奨シート記入例

### 毒晶外殻

- `スキルID`: `Pa-05`
- `スキル名`: `毒晶外殻`
- `消費コスト`: `0`
- `スキル説明`: `自分がダメージを受けた時、攻撃者に出血2を与える。`
- `JSON効果`:

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "apply_state": [
      { "name": "出血", "value": 2 }
    ]
  }
}
```

### 毒晶断裂殻

- `スキルID`: `Pa-06`
- `スキル名`: `毒晶断裂殻`
- `消費コスト`: `0`
- `スキル説明`: `自分がダメージを受けた時、攻撃者に2ラウンドの亀裂1を与える。`
- `JSON効果`:

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "apply_state": [
      { "name": "亀裂", "value": 1, "rounds": 2 }
    ]
  }
}
```
