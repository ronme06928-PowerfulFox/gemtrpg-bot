# アイテム (Items) 定義マニュアル

消費アイテムや、使用することで効果を発揮するアイテムの定義です。

## ファイル構造
- **ファイル名**: `items_cache.json` (キャッシュとして生成)
- **形式**: JSON Object (Key: Item ID)

## フィールド定義

| フィールド | 型 | 必須 | 説明 | 備考 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | string | ✅ | アイテムID | 例: "I-00" |
| `name` | string | ✅ | アイテム名 | |
| `description` | string | ✅ | 効果説明文 | UI表示用 |
| `flavor` | string | | フレーバーテキスト | UI表示用 |
| `consumable` | boolean | ✅ | 消費フラグ | `true`なら使用後に個数が減る |
| `usable` | boolean | ✅ | 使用可能フラグ | `true`ならアイテム欄から使用可能 |
| `round_limit` | integer | | ラウンド使用制限 | 1Rあたりの使用回数 (-1は無制限) |
| `effect` | object | ✅ | 効果定義 | `heal` または `buff` タイプ |

---

## Effect Object の種類

### 1. 回復 (Heal)
HPやMPを回復します。

```json
"effect": {
  "type": "heal",
  "target": "single",
  "hp": 15
}
```

- `type`: `"heal"`
- `target`: 現在は `"single"` (単体) のみ対応
- `hp`: HP回復量 (任意)
- `mp`: MP回復量 (任意)

### 2. バフ付与 (Buff)
バフ図鑑に定義されたバフを付与します。

```json
"effect": {
  "type": "buff",
  "target": "single",
  "buff_id": "Bu-00"
}
```

- `type`: `"buff"`
- `target`: `"single"`
- `buff_id`: `buff_catalog_cache.json` で定義されているバフIDを指定

## 定義例

### HP回復ポーション
```json
  "I-00": {
    "id": "I-00",
    "name": "ギルド印の安物ポーション",
    "description": "味方1人のHPを15回復する。",
    "flavor": "パン一切れくらいの値段で売っている粗悪な回復薬。",
    "consumable": true,
    "usable": true,
    "round_limit": -1,
    "effect": {
      "type": "heal",
      "target": "single",
      "hp": 15
    }
  }
```

### バフ付与アイテム
```json
  "I-01": {
    "id": "I-01",
    "name": "鋭敏の魔力薬",
    "description": "味方1人を選び、1ラウンドの間スキルの基礎威力を+1する。",
    "consumable": true,
    "usable": true,
    "round_limit": 1,
    "effect": {
      "type": "buff",
      "target": "single",
      "buff_id": "Bu-00"
    }
  }
```
