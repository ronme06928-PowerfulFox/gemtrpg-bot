# ジェムリアTRPGダイスボット データ定義統合マニュアル

**最終更新日**: 2026-02-05
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

---

## 1. スキル定義 (`skill_data.json` / 特記処理)

スキルの挙動は、基本パラメータに加えて `特記処理` フィールド（JSON文字列）で制御されます。

### JSON構造 (特記処理)

```json
{
  "tags": ["攻撃", "即時発動", "広域", "宝石の加護スキル"],
  "cost": [{"type": "MP", "value": 5}],
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

#### 1.2 効果 (effects)

スキル発動時に適用されるアクションのリストです。

**共通パラメータ:**

* `timing`: 発動タイミング（必須）。
  * `HIT` (命中時), `WIN` (勝利時), `LOSE` (敗北時), `PRE_MATCH` (開始前), `END_MATCH` (終了時), `UNOPPOSED` (一方攻撃時)
* `target`: 効果対象。
  * `self` (自分), `target` (対象), `ALL_ENEMIES` (敵全体), `ALL_ALLIES` (味方全体), `ALL` (全員), `NEXT_ALLY` (次手番の味方)
* `condition`: 発動条件（任意）。
  * 例: `{"source": "target", "param": "HP", "operator": "LTE", "value": 10}`

**Effect Type 一覧:**

| Type | 説明 | パラメータ例 |
| :--- | :--- | :--- |
| `APPLY_STATE` | 状態異常（数値）を付与 | `state_name`: "出血", `value`: 3 |
| `APPLY_BUFF` | 定義済みバフを付与 | `buff_id`: "Bu-01", `buff_name`: "Power_Atk5", `flavor`: "演出テキスト" |
| `REMOVE_BUFF` | バフを削除 | `buff_name`: "Bu-01" |
| `MODIFY_BASE_POWER` | 基礎威力を変更 (PRE_MATCH用) | `value`: 2 |
| `DAMAGE_BONUS` | 追加ダメージ (HIT/WIN用) | `value`: 5 |
| `MODIFY_ROLL` | ロール結果値の修正 | `value`: -1 |
| `FORCE_UNOPPOSED` | 相手の抵抗を封じる（一方攻撃化） | なし |
| `CUSTOM_EFFECT` | プラグイン効果を実行 | `value`: "破裂爆発" |

**Custom Effects (Plugin):**

* `破裂爆発`: 対象の「破裂」値ｘ5ダメージを与え、破裂を消費。
  * オプション: `rupture_remainder_ratio` (消費後の残りかす率, default: 0)
* `亀裂崩壊_DAMAGE`: 「亀裂」関連の追加ダメージ処理。`damage_per_fissure` で倍率指定。
* `出血氾濫`: 「出血」値分のダメージを与える。
* `戦慄殺到`: 「戦慄」値に応じたMP減少・行動不能判定。
* `荊棘飛散`: 「荊棘」値に応じて拡散処理。
* `APPLY_SKILL_DAMAGE_AGAIN`: このスキルのダメージ計算をもう一度実行する（連撃）。

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

---

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
| `_BleedReact{N}` | 被弾時、自身に出血+N | `Blood_BleedReact2` |
| `_Crack{N}` | 亀裂付与量+N (消費せず) | `Earth_Crack1` |
| `_CrackOnce{N}` | 亀裂付与量+N (1回で消費) | `Quake_CrackOnce2` |

### 2.2 システムバフ (Plugins)

`plugins/buffs/` に実装されている特殊効果を持つバフIDです。

| ID | 名称 (代表) | 効果概要 |
| :--- | :--- | :--- |
| `Bu-04` | 拘束系 | (`immobilize`) 行動不能にする。 |
| `Bu-05` | 再回避ロック | (`dodge_lock`) 回避のみ可能、攻撃不可。 |
| `Bu-06` | 破裂保護 | (`burst_no_consume`) 破裂爆発時、破裂値を消費しない。 |
| `Bu-07` | 時限破裂 | (`timebomb_burst`) `delay` ラウンド経過後に爆発ダメージを与える。 |
| `Bu-08` | 出血維持 | (`bleed_maintenance`) ラウンド終了時の出血減少（半減）を無効化。 |
| `Bu-09` | 爆縮 | (`implosion`) 攻撃時、追加ダメージを与える。 |
| `Bu-10` | 豊穣の風 | (`latium`) ラウンド開始時効果（実装依存）。 |

---

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

---

## 4. 輝化スキル・出身ボーナス定義

### 4.1 輝化スキル (`radiance_skills_cache.json`)

ID `S-XX` で定義されるパッシブスキルです。

* **Stat Bonus**: 常時ステータス底上げ。

    ```json
    "effect": { "type": "STAT_BONUS", "stat": "HP", "value": 10 }
    ```

* **Battle Start Effect**: 戦闘開始時に自動発動。

    ```json
    "effect": {
      "battle_start_effect": [
        { "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 2 }
      ]
    }
    ```

### 4.2 出身ボーナス (Origin Bonuses)

`manager/utils.py` 等でハードコード処理されている自動効果です。

* **ラティウム (ID:3)**: R開始時 FP+1。
* **マホロバ (ID:5)**: R終了時 HP+3。
* **ギァン・バルフ (ID:8)**: デュエル防御成功時、余剰反射ダメージ。
* **綿津見 (ID:9)**: 斬撃スキル威力(ダイス)補正+1。
* **シンシア (ID:10)**: 戦闘開始時「爆縮」バフ（ダメージ+5 / 8回）所持。
* **ヴァルヴァイレ (ID:13)**: 対峙相手の最終達成値-1。

---

## 5. アセット管理・外部画像

キャラクター画像は `Cloudinary` への外部保存に対応しています。

* **環境変数**: `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` が必須。
* **アップロード**: キャラクター詳細設定からアップロードAPI (`/api/upload_image`) を経由して保存されます。
