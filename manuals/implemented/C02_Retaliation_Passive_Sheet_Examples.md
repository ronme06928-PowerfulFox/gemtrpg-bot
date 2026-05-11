<!-- 旧: C02_Retaliation_Passive_Sheet_Examples.md を仕様書として改訂 (2026-05-12) -->

# C02. 被弾反応パッシブ仕様（on_damage_reaction）

**最終更新日**: 2026-05-12
**系統**: C — データ定義（JSON）
**主題**: 特殊パッシブバフの `on_damage_reaction` キーの仕様とシート記入例

---

## 本書の位置づけ

本書は `on_damage_reaction` による被弾反応パッシブの **正式仕様** をまとめたものです。

実装の中心は次の 2 箇所です。

- `manager/utils.py::apply_passive_effect_buffs` — 特殊パッシブの `effect` を `special_buffs` へ展開する入口
- `manager/battle/runtime_actions.py::process_on_damage_buffs` — 被弾反応の主処理

特殊パッシブシートの `JSON効果` 列には `effect` オブジェクト本体をそのまま入れます。スキル JSON のような `schema` や `effects` の外枠は不要です。

---

## 1. 仕様：対応フィールド一覧

| フィールド | 型 | 必須 | 概要 |
| :--- | :--- | :---: | :--- |
| `target` | string | ○ | 反応対象。現在は `"attacker"` のみ正式対応 |
| `damage` | int | — | 対象へ与える固定ダメージ |
| `apply_state` | array | — | 対象へ付与する状態異常のリスト |
| `apply_buff` | array | — | 対象へ付与するバフのリスト |
| `condition` | object | — | 発動条件。現在は `damage_gte` のみ正式対応 |

`damage` / `apply_state` / `apply_buff` はいずれか、または複数を同時に指定できます。

---

## 2. フィールド詳細

### 2.1 target

```json
"target": "attacker"
```

- `"attacker"`: 被弾したキャラクターを攻撃した側
- `attacker_char` が特定できない場合（攻撃者情報なし）は発動しない

### 2.2 damage

```json
"damage": 3
```

- 対象の現在 HP から直接減算する固定値
- `0` 以下は無視される

### 2.3 apply_state

```json
"apply_state": [
  { "name": "出血", "value": 2 },
  { "name": "亀裂", "value": 1, "rounds": 2 }
]
```

**出血**

| フィールド | 必須 | 説明 |
| :--- | :---: | :--- |
| `name` | ○ | `"出血"` |
| `value` | ○ | 付与量 |

**亀裂**

| フィールド | 必須 | 説明 |
| :--- | :---: | :--- |
| `name` | ○ | `"亀裂"` |
| `value` | ○ | 付与量 |
| `rounds` | ○ | 継続ラウンド数（省略すると不発になる） |

> **注意**: 亀裂の `rounds` が未指定の場合、反応は発動したが効果は不発というログが出て終わる。

> **亀裂の枠ルール**: 被弾反応の亀裂付与は、通常スキルの「1 ラウンド 1 回の亀裂付与制限」とは別枠で動作する。

### 2.4 apply_buff

```json
"apply_buff": [
  {
    "buff_id": "Bu-58",
    "buff_name": "毒晶侵食",
    "lasting": 2,
    "delay": 0,
    "data": { "value": 2 }
  }
]
```

各エントリのフィールド:

| フィールド | 必須 | 説明 |
| :--- | :---: | :--- |
| `buff_id` | △ | バフの実体 ID（`buff_id` か `buff_name` の少なくとも一方が必要） |
| `buff_name` | △ | バフの表示名（`buff_id` がある場合は省略可） |
| `lasting` | ○ | 継続ラウンド数 |
| `delay` | ○ | 発動ディレイ（通常 `0`） |
| `data` | — | バフへ渡す追加データ。`value` で効果強度を指定する |
| `data.count` | — | スタック系バフ（蓄力・凝魔など）の初期スタック数 |

`buff_id` のみで指定した場合、ログとバフ名の表示に `buff_id` 文字列がそのまま使われます。

**蓄力・凝魔など count 系バフを付与する例**

```json
"apply_buff": [
  {
    "buff_id": "Bu-Charge",
    "buff_name": "蓄力",
    "lasting": 1,
    "delay": 0,
    "data": { "count": 3 }
  }
]
```

### 2.5 condition

```json
"condition": {
  "damage_gte": 1
}
```

- `damage_gte`: 実際に受けたダメージがこの値以上のときだけ反応する
- 現時点で正式対応している条件は `damage_gte` のみ

---

## 3. 再帰防止仕様

被弾反応で発生したダメージが、さらに被弾反応を呼び出すことはない。

`process_on_damage_buffs` は `context.damage_source == "on_damage_reaction"` のとき即座に `return 0` する。反応ダメージは `_update_char_stat` を直接呼ぶため、この文脈は伝播しない。

---

## 4. シート記入例

### 最小例：被弾時に攻撃者へ 3 ダメージ

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "damage": 3
  }
}
```

### 状態異常付与：被弾時に攻撃者へ出血 2

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

### 状態異常付与：被弾時に攻撃者へ 2 ラウンドの亀裂 1

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

### バフ付与：被弾時に攻撃者へ Bu-58 を付与

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

`buff_name` を省略して `buff_id` のみにすることもできます。

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "apply_buff": [
      {
        "buff_id": "Bu-58",
        "lasting": 2,
        "delay": 0
      }
    ]
  }
}
```

### バフ付与（count 系）：被弾時に攻撃者へ蓄力 3 を付与

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "apply_buff": [
      {
        "buff_id": "Bu-Charge",
        "buff_name": "蓄力",
        "lasting": 1,
        "delay": 0,
        "data": { "count": 3 }
      }
    ]
  }
}
```

### 複合：被弾時に攻撃者へ 2 ダメージと出血 2

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

### 複合：被弾時に攻撃者へ出血 2 と 2 ラウンドの亀裂 1

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

### 条件付き：1 以上の実ダメージを受けた時だけ反応

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

---

## 5. 推奨シート記入例

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

---

## 6. 運用ルール

- 被弾反応の亀裂付与は、通常スキルの「1 ラウンド 1 回制限」とは別枠
- 戦闘ログはプレイヤー向けの自然文で出力する（例: `CrystalScorpionの被弾反応でAttackerに出血3を付与。`）
- `target` は基本的に `"attacker"` を使う
- 反応ダメージで再帰発火しない（セクション 3 参照）
- `apply_buff` は `buff_id` か `buff_name` の少なくとも一方が必要。両方省略した行はスキップされる

---

## 7. テスト確認先

`tests/test_retaliation_passive.py` に以下のケースが実装されている。

| テスト | 確認内容 |
| :--- | :--- |
| `test_on_damage_reaction_damages_attacker` | 攻撃者への固定ダメージ |
| `test_on_damage_reaction_applies_bleed_to_attacker` | 出血付与 |
| `test_on_damage_reaction_applies_fissure_round_buff_to_attacker` | rounds 付き亀裂付与 |
| `test_on_damage_reaction_skips_positive_fissure_without_rounds` | rounds 未指定亀裂は不発 |
| `test_on_damage_reaction_is_suppressed_by_context` | context 抑制（再帰防止） |
| `test_on_damage_reaction_requires_attacker_target` | attacker_char なし時はスキップ |
| `test_on_damage_reaction_apply_buff_id_only` | buff_id のみでバフ付与 |
| `test_on_damage_reaction_apply_buff_data_count` | data.count 経由で count を渡す |
