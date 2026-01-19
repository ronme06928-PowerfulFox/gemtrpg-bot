# 輝化スキル (Radiance Skills) 定義マニュアル

輝化スキルはキャラクターのステータス（HP, MP）を永続的に強化するパッシブスキルです。

## ファイル構造
- **ファイル名**: `radiance_skills_cache.json` (キャッシュとして生成)
- **形式**: JSON Object (Key: Skill ID)

## フィールド定義

| フィールド | 型 | 必須 | 説明 | 備考 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | string | ✅ | スキルID | 例: "S-00" |
| `name` | string | ✅ | スキル名 | |
| `cost` | integer | ✅ | 習得コスト | 現在はシステム的には未使用(1固定) |
| `description` | string | ✅ | 効果説明文 | UI表示用 |
| `flavor` | string | | フレーバーテキスト | UI表示用 |
| `effect` | object | ✅ | 効果定義 | `STAT_BONUS` タイプ |
| `duration` | integer | | 持続時間 | パッシブのため通常 `-1` (無限) |

### Effect Object (Stat Bonus)
ステータスを恒久的に増加させる効果です。

```json
"effect": {
  "type": "STAT_BONUS",
  "stat": "MP",
  "value": 1
}
```

- `type`: 固定値 `"STAT_BONUS"`
- `stat`: 対象ステータス (`"HP"` または `"MP"`)
- `value`: 増加させる値 (数値)

## 定義例

```json
  "S-00": {
    "id": "S-00",
    "name": "魔力の解放",
    "cost": 1,
    "description": "MPの上限を1上げる。",
    "flavor": "幾度も魔力を費やす経験を積み、精神の限界を遠ざけることに成功した証。",
    "effect": {
      "type": "STAT_BONUS",
      "stat": "MP",
      "value": 1
    },
    "duration": -1
  }
```
