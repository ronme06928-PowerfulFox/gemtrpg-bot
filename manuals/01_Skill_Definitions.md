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

## スキル威力の計算仕様 (Skill Power Calculation)

TRPGの記述ルールに基づき、以下の優先順位とロジックで最終的なダイスコマンドが構築されます。

### 1. 基礎威力 (Base Power)

- `基礎威力` の値に、バフや補正による `基礎威力+X` の効果が直ちに加算されます。
- **例**: `基礎威力: 2` に対して `基礎威力+1` のバフがある場合、基礎値は **3** となります。
- コマンド記述: `X` が `X+1` に変化する挙動と等価です。

### 2. 変数ダイスの解決 (Variable Dice Resolution)

- コマンド内の `1d{ステータス名}` 形式の記述は、その時点のステータス値（バフ込み）に置換されます。
- `ダイス威力` や `物理補正` へのバフ（例: `ダイス威力+1`）は、ステータス値自体を加算させるため、結果としてダイス面数が増加します。
- **例**: `1d{ダイス威力}` において、ステータス「ダイス威力」が6で、バフにより+1されている場合 -> `1d7` として解決されます。
- コマンド記述: `1dY` が `1d(Y+1)` に変化する挙動と等価です。

### 3. ダイス威力と補正 (Dice Power & Corrections)

- 最終的なコマンドは「(補正済み基礎威力) + (解決済みダイス部分)」の形式で結合されます。
- **例**: `3 + 2d6 + 1d7`

### 4. 最終威力補正 (Final Power Correction)

- 「最終威力+1」や「威力補正+1」などの効果は、ダイスロール後の**最終合計値**に対して加算されます。
- 計算上はコマンドの末尾に固定値として追加され、マッチの勝敗判定に用いられます。
- **例**: `3 + 2d6 + 5 + 1` (最後の+1が最終威力補正)

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
  {"type": "MP", "value": 5},
  {"type": "FP", "value": 2},
  {"type": "HP", "value": 10}
]
```

- **type**: `MP`, `FP`, `TP` に加え、**`HP`** も指定可能です。
  - **HPコストの挙動**: 現在HPを消費します。HPが足りない場合は発動できません（戦闘不能にはなりません）。

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
- `target`: 効果対象
  - `"self"`: 自分自身
  - `"target"`: 選択した対象
  - **`"NEXT_ALLY"`**: タイムライン上で自分の次に行動する味方
  - **`"ALL_ENEMIES"`**: 敵全体 (ターゲット選択不要)
  - **`"ALL_ALLIES"`**: 味方全体 (自分含む)
  - **`"ALL"`**: 敵味方全員
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

**MULTIPLY_STATE (状態異常値の乗算)**
対象の状態異常値（スタック数）を指定した倍率で乗算します。結果は標準的な四捨五入（0.5は切り上げ）で整数に丸められます。

```json
{
  "type": "MULTIPLY_STATE",
  "state_name": "出血",
  "value": 2.0,      // 2倍にする
  "target": "target"
}
```

- **value**: 乗算する倍率（浮動小数点数）。
  - `2.0`: 2倍 (例: 5 -> 10)
  - `0.5`: 半分 (例: 5 -> 3, 4 -> 2)
  - `0`: 消去 (0にする)

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
| `破裂爆発` | 対象の破裂威力に応じたダメージを与え、破裂を消費する。 | `BurstEffect` |
| `出血氾濫` | 対象が持つ出血威力だけダメージを与える。 | `BleedOverflowEffect` |
| `戦慄殺到` | 戦慄威力に応じてMP減少や行動不能を付与する。 | `FearSurgeEffect` |
| `荊棘飛散` | 荊棘威力に応じて他対象に荊棘を拡散する。 | `ThornsScatterEffect` |
| `亀裂崩壊_DAMAGE` | 亀裂による追加ダメージ処理（通常は自動計算だが強制発動用）。 | `FissureEffect` |
| `APPLY_SKILL_DAMAGE_AGAIN` | 同じスキルのダメージ処理をもう一度実行する（連撃）。 | `SimpleEffect` |

#### その他の効果タイプ (Advanced Types)

**APPLY_STATE_PER_N (定数比例付与)**
「自分の【ステータスA】Xにつき、【ステータスB】をY与える」といった効果を実現します。

```json
{
  "type": "APPLY_STATE_PER_N",
  "state_name": "亀裂",
  "source": "self",
  "source_param": "戦慄",
  "per_N": 2,
  "value": 1,
  "max_value": 5
}
```

**MULTIPLY_STATE (状態異常値の乗算)**
対象の状態異常値（スタック数）を指定した倍率で乗算します。

```json
{
  "type": "MULTIPLY_STATE",
  "state_name": "出血",
  "value": 2.0,
  "target": "target"
}
```

**ランダムターゲット選定 (Random Target)**
`effects` 内のフィールドとして記述することで、効果対象をランダムに決定します。

- `target_select`: `"RANDOM"`
- `target_filter`: `"ENEMY"`, `"ALLY"`, `"ALL"`
- `target_count`: 選択数

```json
{
  "type": "APPLY_STATE",
  "target_select": "RANDOM",
  "target_filter": "ENEMY",
  "target_count": 2,
  "state_name": "出血",
  "value": 3
}
```

**フレーバーテキスト (Flavor Text)**
バフ付与などのログに演出テキストを追加します。

```json
{
  "type": "APPLY_BUFF",
  "buff_name": "勇気の印",
  "flavor": "「負ける気がしない！」心に勇気が湧いてくる。"
}
```
