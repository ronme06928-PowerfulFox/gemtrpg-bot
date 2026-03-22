# ジェムリアTRPGダイスボット データ定義統合マニュアル

**最終更新日**: 2026-03-17
**対象バージョン**: Current

---

## はじめに

本ドキュメントは、ジェムリアTRPGダイスボットにおける各種データ（スキル、バフ、アイテム、輝化・出身）の詳細な定義仕様と実装状況を網羅したものです。
GMや開発者が新しいデータを追加・カスタマイズする際のリファレンスとして使用します。

---

## 目次

1. [スキル定義 (`skill_data.json` / 特記処理)](#1-スキル定義-skill_datajson--特記処理)
2. [バフ・状態異常定義 (Static / Dynamic / Plugin)](#2-バフ状態異常定義-static--dynamic--plugin)
3. [アイテム定義 (`items_cache.json`)](#3-アイテム定義-items_cachejson)
4. [輝化スキル・出身ボーナス定義](#4-輝化スキル出身ボーナス定義)
5. [アセット管理・外部画像](#5-アセット管理外部画像)

<div style="page-break-after: always;"></div>

## 1. スキル定義 (`skill_data.json` / 特記処理)

スキルの挙動は、基本パラメータに加えて `特記処理` フィールド（JSON文字列）で制御されます。

### JSON構造 (特記処理)

```json
{
  "tags": ["攻撃", "即時発動", "広域", "宝石の加護スキル"],
  "cost": [{"type": "MP", "value": 5}, {"type": "HP", "value": 10}],
  "power_bonus": [],
  "effects": []
}
```

### 主要フィールド仕様

#### 1.1 タグ (tags)

システムの挙動を変えるキーワードです。

| タグ名 | 効果 |
| :--- | :--- |
| `攻撃` | 攻撃スキルとして扱われる（バフの `_Atk` 補正などが乗る）。 |
| `守備` | 防御・回避スキルとして扱われる（バフの `_Def` 補正などが乗る）。 |
| `広域` | ターゲット選択後、広域マッチ（Wide Match）画面へ遷移する。 |
| `即時発動` | マッチを行わず、宣言と同時に効果を発揮・消費する。 |
| `宝石の加護スキル` | 1戦闘に1回しか使用できない回数制限がかかる。 |
| `回復` | 回復スキルとして認識される（UI表示などで考慮される場合あり）。 |
| `対象変更不可` (`no_redirect`) | Select/Resolve の引き寄せ（redirect）を行わず、受けもしない。 |
| `味方指定` (`ally_target`/`target_ally`) | 単体対象の対象陣営を味方側として扱う。Select/Resolve では `target_scope=ally` 相当。 |
| `非ダメージ` (`no_damage`/`non_damage`) | `deals_damage=false` の省略指定。命中してもHP減算を行わない。 |

#### mass種別の自動推論（Select/Resolve）

`mass_type` を明示しない既存データは、以下の文字列から自動推論されます。

- `mass_summation` 判定: `mass_summation`, `summation`, `sum`, `広域-合算`, `合算`
- `mass_individual` 判定: `mass_individual`, `individual`, `広域-個別`, `個別`
- `広域` のみ判定可能な場合は `mass_individual` 扱い

参照キーは `mass_type` / `target_type` / `targeting` / `distance` / `距離` / `射程` / `範囲` / `tags` などです。

#### 1.2 効果 (effects)

スキル発動時に適用されるアクションのリストです。

**共通パラメータ:**

* `timing`: 発動タイミング（必須）。
  * **<span style="color:#e74c3c; font-weight:bold;">HIT</span>** (命中時), **<span style="color:#e74c3c; font-weight:bold;">WIN</span>** (勝利時), **<span style="color:#3498db; font-weight:bold;">LOSE</span>** (敗北時), **<span style="color:#f1c40f; font-weight:bold;">PRE_MATCH</span>** (開始前), **<span style="color:#f1c40f; font-weight:bold;">END_MATCH</span>** (終了時), **<span style="color:#e74c3c; font-weight:bold;">UNOPPOSED</span>** (一方攻撃時)
  * **<span style="color:#1abc9c; font-weight:bold;">RESOLVE_START</span>** (戦闘開始時 / 解決フェーズ開始), **<span style="color:#1abc9c; font-weight:bold;">BEFORE_POWER_ROLL</span>** (実威力ロール前), **<span style="color:#1abc9c; font-weight:bold;">AFTER_DAMAGE_APPLY</span>** (ダメージ反映直後), **<span style="color:#1abc9c; font-weight:bold;">RESOLVE_STEP_END</span>** (1処理表示完了), **<span style="color:#1abc9c; font-weight:bold;">RESOLVE_END</span>** (戦闘終了時 / 解決フェーズ終了)
* `target`: 効果対象。
  * `self` (自分), `target` (対象), `ALL_ENEMIES` (敵全体), `ALL_ALLIES` (味方全体/術者含む), `ALL_OTHER_ALLIES` (味方全体/術者除く), `ALL` (全員), `NEXT_ALLY` (次手番の味方)
* `target_scope`: 単体対象（`target`）の対象陣営制御（任意）
  * `enemy` / `ally` / `any`
  * 未指定時は `enemy`
  * `target_scope` 未指定でも、`tags` に `味方指定` / `ally_target` / `target_ally` がある場合は `ally` として解釈されます。
* `condition`: 発動条件（任意）。
  * 例: `{"source": "target", "param": "HP", "operator": "LTE", "value": 10}`
  * `param: "速度値"` は通常ステータスではなく initiative 参照。`context.timeline` / `context.battle_state.slots` / `actor.totalSpeed` の順で評価されます。

**Effect Type 一覧:**

| Type | 説明 | パラメータ例 |
| :--- | :--- | :--- |
| **<span style="color:#9b59b6; font-weight:bold;">APPLY_STATE</span>** | 状態異常（数値）を付与 | `state_name`: "出血", `value`: 3 |
| **<span style="color:#9b59b6; font-weight:bold;">APPLY_BUFF</span>** | 定義済みバフを付与 | `buff_id`: "Bu-01", `buff_name`: "Power_Atk5", `flavor`: "演出テキスト" |
| **<span style="color:#9b59b6; font-weight:bold;">REMOVE_BUFF</span>** | バフを削除 | `buff_name`: "Bu-01" |
| **<span style="color:#2ecc71; font-weight:bold;">MODIFY_BASE_POWER</span>** | 基礎威力を変更 (PRE_MATCH用) | `value`: 2 |
| **<span style="color:#2ecc71; font-weight:bold;">MODIFY_FINAL_POWER</span>** | 最終威力を変更 (PRE_MATCH / BEFORE_POWER_ROLL用) | `value`: -1 |
| **<span style="color:#e74c3c; font-weight:bold;">DAMAGE_BONUS</span>** | 追加ダメージ (HIT/WIN用) | `value`: 5 |
| **<span style="color:#2ecc71; font-weight:bold;">MODIFY_ROLL</span>** | ロール結果値の修正 | `value`: -1 |
| **<span style="color:#2ecc71; font-weight:bold;">USE_SKILL_AGAIN</span>** | 同スキルを同対象スロットへ再使用 | `max_reuses`: 1, `consume_cost`: false, `reuse_cost`: [{"type":"FP","value":1}] |
| **<span style="color:#2ecc71; font-weight:bold;">GRANT_SKILL</span>** | 既存スキルIDを対象へ付与 | `skill_id`: "Ps-10", `grant_mode`: "permanent\|duration_rounds\|usage_count", `duration`, `uses`, `overwrite` |
| **<span style="color:#e67e22; font-weight:bold;">FORCE_UNOPPOSED</span>** | 相手の抵抗を封じる（一方攻撃化） | なし |
| **<span style="color:#34495e; font-weight:bold;">CUSTOM_EFFECT</span>** | プラグイン効果を実行 | `value`: "破裂爆発" |

**Custom Effects (Plugin):**

* `破裂爆発`: 対象の「破裂」値ｘ5ダメージを与え、破裂を消費。
  * オプション: `rupture_remainder_ratio` (消費後の残りかす率, default: 0)
* `亀裂崩壊_DAMAGE`: 「亀裂」関連の追加ダメージ処理。`damage_per_fissure` で倍率指定。
* `出血氾濫`: 出血ダメージ処理イベントを即時に1回実行する。
  * 与ダメージは「現在の出血値」。`Bu-08` が残っていれば1消費して出血値維持、なければ `floor(出血/2)` へ減衰。
* `戦慄殺到`: 「戦慄」値に応じたMP減少・行動不能判定。
* `荊棘飛散`: 「荊棘」値に応じて拡散処理。
* `APPLY_SKILL_DAMAGE_AGAIN`: 旧仕様。ダメージ再適用を直接行う後方互換用。
* `DRAIN_HP`: 与えたダメージの一定割合をHPとして吸収する。`value`: 吸収率(1.0=100%)。

`USE_SKILL_AGAIN` は `CUSTOM_EFFECT` ではなく通常 `effects[].type` として定義します。  
デフォルトでは再使用時コストは消費せず、`consume_cost: true` を指定した場合のみ再使用分も消費します。  
`reuse_cost` を指定した場合は差し込み時に即時支払い判定され、不足時はその再使用だけスキップされます。  
連鎖回数は `max_reuses` を尊重しつつ、実装上限（20）で打ち止めされます。

#### 1.3 威力ボーナス (power_bonus)

基礎威力に対する補正ルールです。

```json
"power_bonus": [
  {
    "source": "self", "param": "HP", "operator": "PER_N_BONUS", "per_N": 10, "value": 1
  }
]
```

* `PER_N_BONUS`: Nごとに+Value。
* `FIXED_IF_EXISTS`: 値が1以上あれば+Value。
* `MULTIPLY`: 値 × Value_per_param。
* `max_bonus`: 加算値の上限を設定。
* `apply_to`: 補正の適用先を指定 (`base`: 基礎威力(デフォルト), `dice`: ダイス面数, `final`: 最終威力)。
  * 例: `{"source": "self", "param": "HP", "operator": "PER_N_BONUS", "per_N": 10, "value": 2, "apply_to": "dice"}` -> HP10ごとにダイスサイズ+2
  * 例: `{"condition": {"source": "skill", "param": "tags", "operator": "CONTAINS", "value": "攻撃"}, "operation": "FIXED", "value": 5, "apply_to": "final"}` -> 攻撃スキルの最終威力+5

---

## 1.4 パッシブスキル定義 (Passive Skills)

`passives_cache.json` で定義される、ステータス常時補正スキルです。

```json
"Pa-00": {
  "name": "迅速",
  "effect": {
    "stat_mods": {
      "行動回数": 1,
      "物理補正": 2
    }
  }
}
```

* **stat_mods**: ステータスへの加算値を Key-Value で指定します。

<div style="page-break-after: always;"></div>

## 2. バフ・状態異常定義 (Static / Dynamic / Plugin)

バフは3つのレイヤーで定義されます。優先順位: Logic > Static > Spreadsheet > Dynamic。

### 2.1 動的定義 (Dynamic Patterns)

名称によって自動的に効果が決まるバフです（定義登録不要）。

| パターン | 効果 | 例 |
| :--- | :--- | :--- |
| `_Atk{N}` | 攻撃威力 +N | `Power_Atk5` |
| `_Def{N}` | 守備威力 +N | `Shield_Def3` |
| `_Phys{N}` | 物理補正 +N | `Boost_Phys2` |
| `_Mag{N}` | 魔法補正 +N | `Mind_Mag2` |
| `_Act{N}` | 行動回数 +N | `Haste_Act1` |
| `_DaIn{N}` | 被ダメ N% 増加 | `Vuln_DaIn20` |
| `_DaCut{N}` | 被ダメ N% 軽減 | `Guard_DaCut10` |
| `_DaOut{N}` | 与ダメ N% 増加 | `Fury_DaOut20` |
| `_DaOutDown{N}` | 与ダメ N% 減少 | `Weaken_DaOutDown15` |
| `_BleedReact{N}` | 被弾時、自身に出血+N | `Blood_BleedReact2` |
| `_Crack{N}` | 亀裂付与量+N (消費せず) | `Earth_Crack1` |
| `_CrackOnce{N}` | 亀裂付与量+N (1回で消費) | `Quake_CrackOnce2` |

補足:
- 戦闘計算は `manager/buff_catalog.py` の動的パターンを基準に解釈される。
- ツールチップ説明文は `static/js/buff_data.js` の `DYNAMIC_PATTERNS` で生成される。
- `_DaIn/_DaCut/_DaOut/_DaOutDown` はサーバー効果とクライアント説明文を同時更新すること。

### 2.2 システムバフ (Plugins)

`plugins/buffs/` に実装されている特殊効果を持つバフIDです。

| ID | 名称 (代表) | 効果概要 |
| :--- | :--- | :--- |
| `Bu-04` | 拘束系 | (`immobilize`) 行動不能にする。 |
| `Bu-05` | 再回避ロック | (`dodge_lock`) 回避のみ可能、攻撃不可。 |
| `Bu-06` | 破裂保護 | (`burst_no_consume`) 破裂爆発時、破裂値を消費しない。 |
| `Bu-07` | 時限破裂 | (`timebomb_burst`) `delay` ラウンド経過後に爆発ダメージを与える。 |
| `Bu-08` | 出血遷延 | (`bleed_maintenance`) 出血ダメージ処理イベント発生時に `count` を1消費し、消費した回は出血減衰（半減）を無効化する。 |
| `Bu-09` | 爆縮 | (`implosion`) 攻撃時、追加ダメージを与える。 |
| `Bu-10` | 豊穣の風 | (`latium`) ラウンド開始時効果（実装依存）。 |
| `Bu-11` | 加速 | (`speed_up`) ラウンド開始時の速度ロール補正（+スタック数）。ロール後に解除。 |
| `Bu-12` | 減速 | (`speed_down`) ラウンド開始時の速度ロール補正（-スタック数）。ロール後に解除。 |

### 2.2.1 `Bu-08`（出血遷延）の付与データ仕様

- `Bu-08` は `lasting` ではなく `count`（残回数）で管理される。
- `count` は `effects[].count` または `effects[].data.count` のどちらでも受理される（運用推奨は `data.count`）。
- 既存の `Bu-08` がある対象へ再付与した場合は、`count` を加算スタックする。
- 旧データ互換として `count` 未設定の `Bu-08` は 1 回分として扱う。
- 「出血ダメージ処理イベント」は以下の2経路で発生する。
  - ラウンド終了時の出血処理
  - `CUSTOM_EFFECT: 出血氾濫` 発動時の即時処理

定義例（推奨）:

```json
{
  "timing": "HIT",
  "type": "APPLY_BUFF",
  "target": "target",
  "buff_id": "Bu-08",
  "data": { "count": 2 }
}
```

### 2.3 特殊起動タイミング効果

バフやパッシブには、特定のイベントで自動発動する効果を定義できます。

#### 戦闘突入時効果 (`battle_start_effect`)

戦闘フェーズへ参加したとき（キャラクターが配置されたとき）に自動発動します。

* タイミング指定は不要（自動的に`IMMEDIATE`として処理）
* スキル効果と同じ形式で定義可能（`APPLY_STATE`, `APPLY_BUFF`など）
* 輝化スキルやパッシブで使用可能
* 本書では「戦闘開始時」は `RESOLVE_START` を指し、`battle_start_effect` とは区別します。

#### 死亡時効果 (`on_death`)

キャラクターのHPが0以下になって死亡したときに自動発動します。

**基本仕様:**

* タイミングは`IMMEDIATE`として処理されます
* 死亡したキャラクター自身が`actor`として効果を発動
* ターゲット指定が可能（`ALL_ENEMIES`, `ALL_ALLIES`, `NEXT_ALLY`など）
* バフの`special_buffs`フィールドまたはパッシブスキルに定義可能

**定義例:**

```json
{
  "name": "呪詛の刻印",
  "on_death": [
    {
      "timing": "IMMEDIATE",
      "type": "APPLY_STATE",
      "target": "ALL_ENEMIES",
      "state_name": "呪い",
      "value": 2
    },
    {
      "timing": "IMMEDIATE",
      "type": "APPLY_BUFF",
      "target": "NEXT_ALLY",
      "buff_name": "Power_Atk3",
      "lasting": 2
    }
  ]
}
```

このバフを持つキャラクターが死亡すると:

1. 全ての敵に「呪い」スタックを2付与
2. 次の手番の味方に「Power_Atk3」バフを2ラウンド付与

**使用可能な効果タイプ:**

* `APPLY_STATE`: 状態異常を付与
* `APPLY_BUFF`: バフを付与
* その他、スキル効果で使用可能な全てのタイプ

<div style="page-break-after: always;"></div>

## 3. アイテム定義 (`items_cache.json`)

`items_cache.json` に定義される消費・使用可能アイテムです。

```json
"I-01": {
  "name": "ポーション",
  "consumable": true, // 使用後に消失するか
  "usable": true,     // アイテム欄から使用可能か
  "round_limit": 1,   // 1Rあたりの使用回数制限 (-1:無限)
  "effect": {
    "type": "heal",   // "heal" or "buff"
    "hp": 15,
    "target": "single"
  }
}
```

<div style="page-break-after: always;"></div>

## 4. 輝化スキル・出身ボーナス定義

### 4.1 輝化スキル (`radiance_skills_cache.json`)

ID `S-XX` で定義されるパッシブスキルです。

* **Stat Bonus**: 常時ステータス底上げ。

    ```json
    "effect": { "type": "STAT_BONUS", "stat": "HP", "value": 10 }
    ```

* **Battle Start Effect**: 戦闘突入時に自動発動。

    ```json
    "effect": {
      "battle_start_effect": [
        { "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 2 }
      ]
    }
    ```

* **Death Effect**: 死亡時に自動発動。

    ```json
    "effect": {
      "on_death": [
        {
          "timing": "IMMEDIATE",
          "type": "APPLY_STATE",
          "target": "ALL_ENEMIES",
          "state_name": "戦慄",
          "value": 3
        }
      ]
    }
    ```

    このキャラクターが死亡すると、全ての敵に「戦慄」を3スタック付与します。

### 4.2 出身ボーナス (Origin Bonuses)

`manager/utils.py` 等でハードコード処理されている自動効果です。

* **ラティウム (ID:3)**: R開始時 <span style="color:#f1c40f; font-weight:bold;">FP+1</span>。
* **マホロバ (ID:5)**: R終了時 <span style="color:#f1c40f; font-weight:bold;">HP+3</span>。
* **ギァン・バルフ (ID:8)**: デュエル防御成功時、余剰反射ダメージ。
* **綿津見 (ID:9)**: <span style="color:#e74c3c; font-weight:bold;">斬撃</span>スキル威力(ダイス)補正+1。
* **シンシア (ID:10)**: 戦闘突入時「爆縮」バフ（ダメージ+5 / 8回）所持。
* **ヴァルヴァイレ (ID:13)**: 対峙相手の最終達成値-1。

<div style="page-break-after: always;"></div>

## 5. アセット管理・外部画像

キャラクター画像は `Cloudinary` への外部保存に対応しています。

* **環境変数**: `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` が必須。
* **アップロード**: キャラクター詳細設定からアップロードAPI (`/api/upload_image`) を経由して保存されます。

---

## 6. 用語図鑑データ定義（Glossary）

### 6.1 主要列
- `ID`（または `term_id`）: 用語ID。重複不可。
- `名称`（または `display_name`）: 画面表示名。
- `分類`（または `category`）: 用語カテゴリ。
- `短文説明`（または `short`）: ツールチップ向け短文。
- `本説明`（または `long` / `説明`）: ポップアップ向け本文。
- `フレーバー`（または `flavor` / `フレーバーテキスト`）: 補足文。
- `関連用語ID`（または `links`）: 関連IDのリスト。
- `別名`（または `synonyms`）: 別名のリスト。
- `アイコン`（または `icon`）: アイコン名またはURL。
- `表示順`（または `sort_order`）: 並び順。
- `表示の有無`（または `is_enabled`）: TRUE/FALSE。
- `追加JSON`（または `extra_json`）: 将来拡張用JSON。

### 6.2 区切りルール
- `関連用語ID` / `別名` はカンマ区切りで入力する。
- `,` と `、` の両方を区切り文字として扱う。

入力例:
- `関連用語ID`: `W-00,W-01,W-15`
- `別名`: `Bleed,継続ダメージ`

### 6.3 スキル文への埋め込み記法
- `[[TERM_ID|表示名]]`
- `[[TERM_ID]]`

例:
- `対象に[[W-00|出血]]を2付与する。`
- `自身が[[W-12]]状態なら威力+2。`

### 6.4 表示時の説明文選択ルール
- バトル画面（Glossary本体）:
  - hover: `短文説明` を優先表示（未登録なら非表示または代替挙動）
  - click/tap popup: `本説明` を優先表示（未登録時は `短文説明` を使用）
- `GEMDICEBOT_CharaCreator.html` の簡易ツールチップ:
  - 本文は `短文説明` を優先し、空の場合は `本説明` を表示
  - 両方空の場合に「説明未登録」を表示

### 6.5 読み込み経路（キャラ作成HTMLツール）
- `GEMDICEBOT_CharaCreator.html` は用語図鑑を Google Sheets `gviz` から読み込む。
- `gviz` 取得に失敗した場合は公開CSV URLへのフォールバックを行う。
- そのため、図鑑更新直後に表示が古い場合はブラウザのハードリロード（`Ctrl+F5`）を推奨。

---

## 付録: 効果タイミング実行時期一覧（実装準拠 / 2026-02）

この節は、`effects[].timing` が「いつ」「どこで」実行されるかを、運用順にまとめた参照表です。

### A. 判定の共通仕様
- 効果の実行可否は `manager/game_logic.py` の `process_skill_effects(...)` で判定されます。
- 判定条件は `effect.timing == timing_to_check` の完全一致です。
- したがって、データ側の `timing` 名と呼び出し側で渡す `timing_to_check` の一致が必須です。
- 同一 `effects[]` 内では先行効果の反映結果を後続効果の条件判定に利用します（逐次シミュレーション）。

### B. 「使用時」はどこで処理されるか
現在、`使用時` は専用タイミング名ではなく、以下で表現されています。

1. 即時発動スキルの宣言確定時（実質的な使用時）
- 実行箇所: `manager/battle/duel_solver.py`
- `IMMEDIATE` を実行
- 続けて `PRE_MATCH` も実行（即時系の互換運用）

2. 通常解決フローの実行直前（解決フェーズ中の使用時相当）
- 実行箇所: `manager/battle/core.py`
- マッチ/一方攻撃の解決前に `PRE_MATCH` を実行

### C. タイミング別 実行時期一覧

- `IMMEDIATE`
  - 実行時期: 宣言確定直後（主に即時発動）
  - 主呼び出し: `manager/battle/duel_solver.py`

- `PRE_MATCH`
  - 実行時期: 実行直前（威力ロール前）
  - 主呼び出し: `manager/battle/core.py`, `manager/battle/duel_solver.py`

- `BEFORE_POWER_ROLL`
  - 実行時期: 威力レンジ表示後、実威力ロールの直前
  - 主呼び出し: `manager/battle/core.py`

- `UNOPPOSED`
  - 実行時期: 一方攻撃の成立後、ダメージ算出の処理中
  - 主呼び出し: `manager/battle/core.py`, `manager/battle/duel_solver.py`, `manager/battle/wide_solver.py`

- `HIT`
  - 実行時期: 命中処理中（ダメージ計算の文脈）
  - 主呼び出し: `manager/battle/core.py`, `manager/battle/duel_solver.py`, `manager/battle/wide_solver.py`

- `WIN` / `LOSE`
  - 実行時期: 勝敗確定後
  - 主呼び出し: `manager/skill_effects.py`（`apply_skill_effects_bidirectional`）

- `AFTER_DAMAGE_APPLY`
  - 実行時期: HP反映直後
  - 主呼び出し: `manager/battle/core.py`

- `END_MATCH`
  - 実行時期: 1マッチ解決の末尾
  - 主呼び出し: `manager/battle/duel_solver.py`, `manager/battle/wide_solver.py`

- `RESOLVE_STEP_END`
  - 実行時期: 1処理（1マッチ/1一方攻撃/1広域）表示完了時
  - 主呼び出し: `manager/battle/core.py`

- `RESOLVE_START`
  - 実行時期: 戦闘開始時（解決フェーズ開始直後）
  - 主呼び出し: `manager/battle/core.py`

- `RESOLVE_END`
  - 実行時期: 戦闘終了時（解決フェーズ全体の表示完了後）
  - 主呼び出し: `manager/battle/core.py`

- `END_ROUND`
  - 実行時期: ラウンド終了処理時
  - 主呼び出し: `manager/battle/common_manager.py`

- `BATTLE_START`
  - 実行時期: 戦闘突入時（バトル参加時 / 配置時）
  - 主呼び出し: `manager/game_logic.py`（戦闘開始効果処理）

### D. 実装上の注意
- `使用時効果` テキスト列は主に表示/互換用途で、実際の効果発火は `特記処理.effects[]` が基準です。
- 新規効果を追加する際は、`timing` の定義（データ）と呼び出し点（コード）の両方を合わせて更新してください。
- `速度値` 条件はスロット initiative（最大値）を参照するため、通常 `params` の `速度` とは別物です。
- Select/Resolve での再使用演算・表示ラベル規則は `manuals/implemented/09_SelectResolve_Spec.md` の 9.2 / 付録A-6 を参照してください。
- 用語整理:
  - `戦闘開始時` = `RESOLVE_START`
  - `戦闘終了時` = `RESOLVE_END`
  - `戦闘突入時` = `BATTLE_START` / `battle_start_effect`
  - `戦闘離脱時` = 戦闘フェーズから離れる概念用語（現時点では専用の標準timing未定義。死亡時は `on_death` を使用）

---

## 追補A: 2026-02 統合拡張（実装確定）

### A-1. スキル追加フィールド
- `deals_damage: false`
  - one-sided / clash でHP減算を行わない非ダメージスキル指定。
  - `HIT` などのタイミング効果は通常どおり評価。
- タグ省略記法:
  - `tags` に `非ダメージ` / `no_damage` / `non_damage` がある場合も `deals_damage=false` 相当として扱う。

### A-2. 条件ソース拡張
- `condition.source: relation`
  - `param: same_team | target_is_ally | target_is_enemy`
  - 戻り値は 0/1（`EQUALS 1` 等で判定）

### A-3. ダメージ倍率キー拡張
- 既存: `damage_multiplier`（被ダメ倍率）
- 追加:
  - `incoming_damage_multiplier`（被ダメ倍率）
  - `outgoing_damage_multiplier`（与ダメ倍率）
- 動的命名:
  - `_DaInN`, `_DaCutN`, `_DaOutN`, `_DaOutDownN`

### A-4. PvE敵行動チャート定義
`character.flags.behavior_profile`:

```json
{
  "enabled": true,
  "version": 1,
  "initial_loop_id": "phase_1",
  "loops": {
    "phase_1": {
      "repeat": true,
      "steps": [
        {
          "actions": ["SKILL_A"],
          "next_loop_id": "phase_2",
          "next_reset_step_index": true
        }
      ],
      "transitions": [
        {
          "priority": 10,
          "when_all": [{"source": "self", "param": "HP", "operator": "LTE", "value": 50}],
          "to_loop_id": "phase_2",
          "reset_step_index": true
        }
      ]
    }
  }
}
```

補足:
- `steps[].next_loop_id` は任意。指定時はそのstep使用後に遷移します。
- `steps[].next_reset_step_index` は任意。`true` なら遷移先loopの先頭stepから開始します（既定 `true`）。

`battle_state.behavior_runtime`:

```json
{
  "<actor_id>": {
    "active_loop_id": "phase_1",
    "step_index": 0,
    "last_round": 3,
    "last_skill_ids": ["SKILL_A"]
  }
}
```

### A-5. プリセット保存スキーマ v2
- ルーム保存:

```json
{
  "version": 2,
  "created_at": 1760000000000,
  "enemies": [ ... ]
}
```

- JSON搬出入:

```json
{
  "schema": "gem_dicebot_enemy_preset.v1",
  "exported_at": "2026-02-26T00:00:00Z",
  "preset_name": "BossPhase",
  "payload": { "version": 2, "enemies": [ ... ] }
}
```

運用確定:
- プリセット関連 Socket はサーバー側で GM 権限チェックを必須とする。
- 保存/読込時は v1/v2 の互換正規化を通して `payload.version=2` へ寄せる。
- `behavior_profile` を含む敵定義は、ルーム保存・JSON搬出入の双方で同じ schema で扱う。

### A-6. `target_scope=ally` の Select/Resolve 固定ルール
- `target_scope=ally`（または `味方指定` 系タグ）スキルは redirect（引き寄せ）に参加しない。
  - 発生させない
  - 受けない
- 同一陣営どうしの相互指定で、どちらかが `target_scope=ally` の場合は `clash` を組まず `one-sided` として解決する。
- 同一陣営どうしの上記ペアでは、再回避差し込み（evade insert）を行わない。
