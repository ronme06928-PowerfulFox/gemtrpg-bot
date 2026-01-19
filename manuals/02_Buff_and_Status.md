# バフ・ステータス (Buff & Status) 定義マニュアル

バフ図鑑 (`buff_catalog_cache.json`) で定義されるバフおよびデバフのデータ構造です。

## ファイル構造
- **ファイル名**: `buff_catalog_cache.json` (キャッシュとして生成)
- **形式**: JSON Object (Key: Buff ID)

## フィールド定義

| フィールド | 型 | 必須 | 説明 | 備考 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | string | ✅ | バフID | 例: "Bu-00" |
| `name` | string | ✅ | バフ名 | |
| `description` | string | ✅ | 効果説明文 | UI表示用 |
| `flavor` | string | | フレーバーテキスト | UI表示用 |
| `default_duration`| integer | ✅ | デフォルト持続時間 | ラウンド数 |
| `effect` | object | ✅ | 効果詳細オブジェクト | `stat_mod` または `plugin` タイプ |

---

## Effect Object の種類

### 1. ステータス補正 (Stat Mod)
キャラクターのステータス（威力、ダイス、補正値など）を数値的に変動させます。

```json
"effect": {
  "type": "stat_mod",
  "stat": "基礎威力",
  "value": 1
}
```

- `type`: `"stat_mod"`
- `stat`: 補正対象パラメータ
  - `"基礎威力"`: スキルの固定値部分を加算
  - `"物理補正"`: 物理攻撃のダイスロールなどに影響
  - `"魔法補正"`: 魔法攻撃のダイスロールなどに影響
- `value`: 加算する値 (マイナスなら減少)

#### 定義例: 鋭敏 (Bu-00)
```json
"Bu-00": {
  "id": "Bu-00",
  "name": "鋭敏",
  "description": "1ラウンドの間スキルの基礎威力を+1する。",
  "effect": {
    "type": "stat_mod",
    "stat": "基礎威力",
    "value": 1
  },
  "default_duration": 1
}
```

### 2. プラグイン効果 (Plugin)
Pythonコード (`plugins/buffs/`) で実装された特殊なロジックを適用します。

```json
"effect": {
  "type": "plugin",
  "name": "provoke",
  "category": "debuff"
}
```

- `type`: `"plugin"`
- `name`: プラグイン識別子 (実装コード内のクラス定義と紐づく)
  - `"provoke"`: 挑発 (ターゲット強制)
  - `"confusion"`: 混乱 (行動順ランダム・FP操作等)
  - `"immobilize"`: 行動不能
  - `"dodge_lock"`: 再回避ロック
- `category`: `"buff"` (有利) または `"debuff"` (不利)
- `params`: プラグインが必要とする追加パラメータ (任意)

#### 定義例: 挑発 (Bu-01)
```json
"Bu-01": {
  "id": "Bu-01",
  "name": "挑発",
  "description": "このラウンドで全ての相手の攻撃対象を自分に固定する。",
  "effect": {
    "type": "plugin",
    "name": "provoke",
    "category": "debuff"
  },
  "default_duration": 1
}
```

#### 定義例: 混乱 (Bu-02)
```json
"Bu-02": {
  "id": "Bu-02",
  "name": "混乱",
  "description": "受けるダメージが1.5倍になり、行動できない。",
  "effect": {
    "type": "plugin",
    "name": "confusion",
    "category": "debuff",
    "damage_multiplier": 1.5,
    "restore_mp_on_end": false
  },
  "default_duration": 2
}
```
