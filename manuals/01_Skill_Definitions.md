# スキル (Skills) 定義マニュアル

`skill_data.json` における通常のスキル定義および「特記処理 (`Special Effects`)」の詳細マニュアルです。

## JSON構造

```json
"E-00": {
  "スキルID": "E-00",
  "チャットパレット": "2+1d2+1d{物理補正} 【E-00 殴る】",
  "デフォルト名称": "殴る",
  "分類": "物理",
  "距離": "近接",
  "属性": "打撃",
  "取得コスト": "0",
  "基礎威力": "2",
  "ダイス威力": "+1d2",
  "使用時効果": "",
  "特記": "",
  "発動時効果": "",
  "特記処理": "{...}",  // JSON文字列として記述
  "tags": ["攻撃"]
}
```

- **特記処理**: JSON形式の文字列として記述する必要があります。エスケープ処理に注意してください。
- **tags**: `"攻撃"`, `"守備"`, `"広域"`, `"即時発動"`, `"宝石の加護スキル"` など。

---

## 特記処理 (Special Effects) の構造

特記処理フィールドは、内部的には以下のJSON構造を持ちます。

```json
{
  "tags": ["攻撃"],
  "power_bonus": [],
  "cost": [{"type": "MP", "value": 5}],
  "effects": []
}
```

### 1. Cost (コスト定義)

スキルの使用コストを定義します。（システム的には表示用ですが、将来的に自動減算に対応可能です）

```json
"cost": [
  {"type": "MP", "value": 5},
  {"type": "FP", "value": 2}
]
```

### 2. Power Bonus (威力ボーナス)

条件に応じて基礎威力を加算するルールです。

```json
"power_bonus": [
  {
    "source": "target",          // 参照先 ("self", "target")
    "param": "戦慄",             // 参照パラメータ
    "operation": "PER_N_BONUS",  // 計算ルール
    "per_N": 5,                  // Nごとに
    "value": 1,                  // +1
    "max_bonus": 2               // 最大+2まで
  }
]
```

- **Operations**:
  - `PER_N_BONUS`: パラメータ N ごとに value 加算
  - `FIXED_IF_EXISTS`: パラメータが1以上あれば value 加算
  - `MULTIPLY`: パラメータ × value_per_param を加算

### 3. Effects (発動効果)

スキル命中時や使用時に発動する効果のリストです。

#### 共通フィールド

- `timing`: 発動タイミング
  - `"HIT"`: 命中時
  - `"WIN"`: マッチ勝利時
  - `"LOSE"`: マッチ敗北時
  - `"PRE_MATCH"`: マッチ開始前 (即時発動など)
  - `"END_ROUND"`: ラウンド終了時
  - `"END_MATCH"`: マッチ終了時
  - `"UNOPPOSED"`: 一方攻撃（相手が防御・回避を持たない、または行動不能時）の攻撃時
- `target`: 効果対象 (`"self"`, `"target"`)
- `condition`: 発動条件 (任意)

#### 効果タイプ (Type)

**APPLY_STATE (状態異常付与)**
ステータスや状態異常値を加算します。

```json
{
  "type": "APPLY_STATE",
  "state_name": "出血",
  "value": 3
}
```

**APPLY_BUFF (バフ付与)**
バフ図鑑のバフ、または動的バフを付与します。

```json
{
  "type": "APPLY_BUFF",
  // ID指定: カタログや特殊ロジック(Bu-07等)を利用する場合は必須
  "buff_id": "Bu-01",
  // 名前指定: 動的バフを指定する場合、または既存IDの表示名を上書きする場合に使用
  "buff_name": "Power_Atk5",
  "lasting": 1,            // 持続ラウンド (省略時: 1)
  "delay": 0,              // 発動遅延ラウンド (省略時: 0)
  "flavor": "力が湧く！"     // フレーバーテキストの上書き/設定 (任意)
}
```

**設定例: 表示名の変更と時限発動**
`Bu-07` (時限破裂) のロジックを使いつつ、名前を「時限式魔力爆弾」にし、3ターン後に爆発・消滅させる例:

```json
{
  "type": "APPLY_BUFF",
  "buff_id": "Bu-07",
  "buff_name": "時限式魔力爆弾",
  "delay": 3,   // 3ラウンド後に発動
  "lasting": 0  // 発動と同時に消滅
}
```

**APPLY_STATE_PER_N (動的付与)**
パラメータに応じて付与量を変動させます。

```json
{
  "type": "APPLY_STATE_PER_N",
  "state_name": "亀裂",
  "source": "self",
  "source_param": "戦慄",
  "per_N": 2,
  "value": 1
}
```

**CUSTOM_EFFECT (特殊効果)**
プラグインとして実装された特殊な処理を実行します。

```json
{
  "type": "CUSTOM_EFFECT",
  "value": "破裂爆発"
}
```

**使用可能な CUSTOM_EFFECT 一覧**:

| 値 (Value) | 説明 | 実装 |
| :--- | :--- | :--- |
| `破裂爆発` | 対象の破裂値に応じたダメージを与え、破裂を消費する。 | `BurstEffect` |
| `出血氾濫` | 出血Lvに応じて全体にダメージを拡散する等の処理。 | `BleedOverflowEffect` |
| `戦慄殺到` | 戦慄Lvに応じてMP減少や行動不能を付与する。 | `FearSurgeEffect` |
| `荊棘飛散` | 荊棘Lvに応じて他対象に荊棘を拡散する。 | `ThornsScatterEffect` |
| `亀裂崩壊_DAMAGE` | 亀裂による追加ダメージ処理（通常は自動計算だが強制発動用）。 | `FissureEffect` |
| `APPLY_SKILL_DAMAGE_AGAIN` | 同じスキルのダメージ処理をもう一度実行する（連撃）。 | `SimpleEffect` |
