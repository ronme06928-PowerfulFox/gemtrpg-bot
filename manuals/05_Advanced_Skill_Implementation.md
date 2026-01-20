# 高度なスキル・特殊効果の実装ガイド

このドキュメントでは、複雑な条件や特殊な挙動を持つスキル・バフの実装方法について解説します。
既存のシステムの枠組み（`buff_catalog.py`, `plugins/`, `game_logic.py`）を拡張して実装する具体的な手順を示します。

## 目次

1. [基本アーキテクチャ](#1-基本アーキテクチャ)
2. [実装ケーススタディ](#2-実装ケーススタディ)
    - [Case 1: 挑発と被ダメージ増加を同時付与](#case-1-挑発と被ダメージ増加を同時付与)
    - [Case 2: 攻撃を受ける度に出血付与（反撃デバフ）](#case-2-攻撃を受ける度に出血付与反撃デバフ)
    - [Case 3: 時限式破裂爆発](#case-3-時限式破裂爆発)
    - [Case 4: 破裂爆発連鎖（ダメージ条件で亀裂付与）](#case-4-破裂爆発連鎖ダメージ条件で亀裂付与)
    - [Case 5: 亀裂崩壊と破裂爆発の同時発動](#case-5-亀裂崩壊と破裂爆発の同時発動)
    - [Case 6: 出血の低下阻止](#case-6-出血の低下阻止)
    - [Case 7: 破裂付与量2倍](#case-7-破裂付与量2倍)
    - [Case 8: 状態異常値に応じた追加効果](#case-8-状態異常値に応じた追加効果)
    - [Case 9: ランダムターゲット選定](#case-9-ランダムターゲット選定)
3. [実装が必要なファイル一覧](#3-実装が必要なファイル一覧)

---

## 1. 基本アーキテクチャ

複雑な効果は主に以下の3つの要素を組み合わせて実現します。

1.  **静的バフ定義 (`buff_catalog_cache.json`)**:
    *   `plugin` タイプを指定して、カスタムロジック（Pythonコード）と連携させます。
2.  **動的バフパターン (`manager/buff_catalog.py`)**:
    *   命名規則（例: `_Burst2x`）に基づいて、効果を自動生成します。
3.  **プラグイン (`plugins/*.py`)**:
    *   特定のイベント（被ダメージ時、ラウンド終了時など）で発火するロジックを記述します。
4.  **スキル特記処理 (`特記処理` JSON)**:
    *   スキルの発動時（HIT, WINなど）に適用する効果をリストで定義します。

---

## 2. 実装ケーススタディ

### Case 1: 挑発と被ダメージ増加を同時付与

敵一人に対して、「挑発」と「被ダメージ増加」の2つのデバフを同時に付与します。

**実装アプローチ:**
スキルの `特記処理.effects` 配列に、2つの `APPLY_BUFF` 効果を記述します。

**ステップ1: バフ定義の追加 (`buff_catalog_cache.json`)**
「被ダメージ増加」バフを定義します。
```json
"Bu-XX": {
  "id": "Bu-XX",
  "name": "被ダメージ増加_15%",
  "description": "受けるダメージが1.15倍になる。",
  "effect": {
    "type": "plugin",
    "name": "damage_increase",
    "damage_multiplier": 1.15
  },
  "default_duration": 2
}
```

**ステップ2: スキルデータの設定**
スプレッドシート等のスキルデータ定義で以下のように記述します。
```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "APPLY_BUFF",
      "target": "target",
      "buff_id": "Bu-01",  // 既存の挑発バフ
      "lasting": 1
    },
    {
      "timing": "HIT",
      "type": "APPLY_BUFF",
      "target": "target",
      "buff_name": "被ダメージ増加_15%", // 上記で定義したバフ名、またはbuff_id
      "lasting": 2
    }
  ]
}
```

---

### Case 2: 攻撃を受ける度に出血付与（反撃デバフ）

攻撃を受けた際、攻撃してきた相手に対して「出血」を付与する状態になります。

**実装アプローチ:**
プラグイン型のバフを作成し、被ダメージ処理のフックポイントで反撃処理を実行します。

**ステップ1: バフ定義 (`buff_catalog_cache.json`)**
```json
"Bu-CounterBleed": {
  "id": "Bu-CounterBleed",
  "name": "反撃出血",
  "description": "攻撃を受ける度、攻撃者に出血を与える。",
  "effect": {
    "type": "plugin",
    "name": "counter_bleed",
    "value": 2 // 反撃で与える出血量
  },
  "default_duration": 3
}
```

**ステップ2: プラグイン実装 (`plugins/counter_bleed.py`)**
被ダメージ時に呼び出されるロジックを作成します。（※システム側で被ダメージフックの実装が必要です）

**ステップ3: スキルデータ設定**
```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "APPLY_BUFF",
      "target": "target",
      "buff_name": "反撃出血",
      "lasting": 3
    }
  ]
}
```

---

### Case 3: 時限式破裂爆発

付与してから数ターン後に効果が発動するバフです。

**実装アプローチ:**
バフの `delay` パラメータを活用します。ラウンド終了時に `delay` が 0 になったタイミングで発火する処理をシステムに組み込みます。

**ステップ1: スキルデータ設定**
```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "APPLY_BUFF",
      "target": "target",
      "buff_name": "時限破裂",
      "lasting": 1,
      "delay": 3, // 3ラウンド後に発動
      "data": {
        "burst_damage": 10,
        "burst_on_expire": true // 期限切れ(発動)時に破裂処理を行うフラグ
      }
    }
  ]
}
```

**ステップ2: システム処理の追加**
`manager/room_manager.py` などのラウンド進行処理において、バフの `delay` カウントダウン処理の中で、`burst_on_expire` フラグを持つバフがアクティブになった（delay=0になった）瞬間に効果を発動させるロジックを追加します。

---

### Case 4: 破裂爆発連鎖（ダメージ条件で亀裂付与）

破裂爆発によって一定以上のダメージを受けた場合、さらに「亀裂」を付与します。

**実装アプローチ:**
破裂爆発処理を行うプラグイン (`plugins/burst_explosion.py`) を拡張またはラップし、ダメージ量を監視します。

**ステップ1: バフ定義**
この効果を持つ特殊な状態（デバフ）を定義します。
```json
"Bu-BurstChain": {
  "name": "破裂連鎖",
  "effect": {
    "type": "plugin",
    "name": "burst_chain_monitor",
    "damage_threshold": 10,
    "fissure_amount": 2
  }
}
```

**ステップ2: プラグイン実装 (`plugins/burst_chain.py`)**
破裂ダメージ発生イベントをフックし、条件を満たせば `APPLY_STATE` (亀裂) を実行するロジックを記述します。

---

### Case 5: 亀裂崩壊と破裂爆発の同時発動

通常は別々の効果である「亀裂崩壊」と「破裂爆発」を一度に実行します。

**実装アプローチ:**
新しい `CUSTOM_EFFECT` プラグインを作成し、内部で既存の2つの処理を呼び出します。

**ステップ1: プラグイン実装 (`plugins/dual_collapse_burst.py`)**
```python
def apply(actor, target, effect, context):
    registry = context.get("registry", {})

    # 1. 亀裂崩壊を実行
    fissure_handler = registry.get("fissure_collapse")
    changes1, logs1 = fissure_handler.apply(...) if fissure_handler else ([], [])

    # 2. 破裂爆発を実行
    burst_handler = registry.get("burst_explosion")
    changes2, logs2 = burst_handler.apply(...) if burst_handler else ([], [])

    return changes1 + changes2, logs1 + logs2
```

**ステップ2: スキルデータ設定**
```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "CUSTOM_EFFECT",
      "target": "target",
      "value": "dual_collapse_burst" // プラグイン名
    }
  ]
}
```

---

### Case 6: 出血の低下阻止

ラウンド終了時の出血値の自然減少（通常は半減など）を防ぎます。

**実装アプローチ:**
自然減少処理のロジックにおいて、「減少阻止バフ」を持っているかチェックする条件分岐を追加します。

**ステップ1: バフ定義**
```json
"Bu-BleedSustain": {
  "name": "出血維持",
  "effect": { "type": "flag", "name": "prevent_bleed_decay" }
}
```

**ステップ2: システム修正 (`manager/room_manager.py`)**
ラウンド終了時の状態異常更新ループ内で：
```python
if char.has_buff_with_flag("prevent_bleed_decay"):
    # 出血減少処理をスキップ
    pass
else:
    # 通常の減少処理
```

---

### Case 7: 破裂付与量2倍

破裂を付与する際、その量が2倍になります。

**実装アプローチ:**
`manager/buff_catalog.py` の `DYNAMIC_PATTERNS` にパターンを追加するのが最も簡単です。

**ステップ1: パターン定義の追加 (`manager/buff_catalog.py`)**
```python
{
    "pattern": r"^(.*)_Burst2x$",
    "generator": lambda m: {
        "state_bonus": [{
            "stat": "破裂",
            "operation": "MULTIPLY",
            "value": 2,
            "consume": False
        }]
    }
}
```
これにより、バフ名に `_Burst2x` を付けるだけで自動的に破裂付与量が2倍になります。

---

### Case 8: 状態異常値に応じた追加効果

「相手の破裂値に応じて出血を付与する」などの動的な効果です。

**実装アプローチ:**
既存の `APPLY_STATE_PER_N` タイプを使用します。

**スキルデータ設定例:**
```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "APPLY_STATE_PER_N",
      "target": "target",
      "source": "target",      // 参照元: ターゲット自身
      "source_param": "破裂",   // 参照パラメータ: 破裂
      "state_name": "出血",     // 付与する状態: 出血
      "per_N": 2,              // 破裂2につき
      "value": 1,              // 出血1を付与
      "max_value": 5           // 最大5まで
    }
  ]
}
```

---

### Case 9: ランダムターゲット選定

「ランダムな敵1体」や「ランダムな味方1体」を対象にする効果です。

**実装アプローチ:**
`manager/game_logic.py` の `process_skill_effects` 関数に、新しいターゲット指定ロジックを追加します。

**ステップ1: ロジック拡張 (`manager/game_logic.py`)**
`process_skill_effects` 内で `target_type: "RANDOM_ENEMY"` などを処理する分岐を追加します。

```python
elif effect.get("target_select") == "RANDOM":
    # 候補リストの作成
    candidates = [c for c in all_characters if is_enemy(actor, c)]
    if candidates:
        import random
        target_obj = random.choice(candidates)
        # 以降、選ばれた target_obj に対して効果を適用
```

**ステップ2: スキルデータ設定**
```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "APPLY_BUFF",
      "target": "target",       // 基本ターゲット設定（無視される場合もあるが形式上必要）
      "target_select": "RANDOM", // 追加プロパティでランダム指定
      "target_filter": "ENEMY",  // 敵から選出
      "buff_name": "ランダムデバフ"
    }
  ]
}
```

---

### Case 10: 動的ダメージ倍率バフ（DaIn / DaCut）

バフ名に特定のパターンを含めることで、自動的に被ダメージ倍率を適用する機能が実装されました。
プラグインや個別のJSON定義を作成せずに、名前だけで効果を発揮します。

**パターン:**
*   `_DaIn[数値]`: 被ダメージ増加 (Damage Increase)
    *   例: `Weakness_DaIn20` -> 被ダメージ **1.2倍** (+20%)
*   `_DaCut[数値]`: 被ダメージ軽減 (Damage Cut)
    *   例: `Guard_DaCut30` -> 被ダメージ **0.7倍** (-30%)

**実装アプローチ:**
スキルデータの `APPLY_BUFF` で名前を指定するだけです。

**スキルデータ設定例:**
```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "APPLY_BUFF",
      "target": "target",
      "buff_name": "脆弱_DaIn20", // これだけで被ダメージ1.2倍の効果が発動
      "lasting": 2
    }
  ]
}
```

**Case 1 (挑発と被ダメージ増加) の簡略化:**
以前の手順では `buff_catalog_cache.json` にバフを定義する必要がありましたが、この新機能を使えば以下のように書くだけで済みます。

```json
{
  "effects": [
    {
      "type": "APPLY_BUFF",
      "buff_id": "Bu-01" // 挑発
    },
    {
      "type": "APPLY_BUFF",
      "buff_name": "被ダメ増_DaIn15", // 自動的に1.15倍
      "lasting": 2
    }
  ]
}
```

---

### Case 11: 被弾時トリガーバフ（BleedReact）

ダメージを受けた際に、自動的に自分のステータス（出血など）を変化させるバフです。
「攻撃を受けるたびに状態が悪化する」といった表現に使えます。

**パターン:**
*   `_BleedReact[数値]`: 被弾時出血増加 (Reactive Bleed)
    *   例: `Cursed_BleedReact2` -> ダメージを受けると自分の出血 **+2**

**実装アプローチ:**
通常のバフ付与と同様に、名前にサフィックスをつけるだけです。

**スキルデータ設定例:**
```json
{
  "effects": [
    {
      "type": "APPLY_BUFF",
      "buff_name": "傷口拡大_BleedReact1", // 被弾するたびに出血+1
      "lasting": 3
    }
  ]
}
```

---

### Case 12: バフへのフレーバーテキスト追加

バフの効果定義（JSON）に `flavor` フィールドを追加することで、キャラ詳細画面でバフの説明文の下に、イタリック体でフレーバーテキストを表示できます。
スプレッドシート（バフ図鑑）にあらかじめ定義されているフレーバーテキストよりも、このJSON定義が優先されます。

**優先順位:**
1.  **スキルJSON定義**: スキル使用時に指定された `flavor`（最優先）
2.  **スプレッドシート定義**: バフ図鑑に登録されているデフォルトのフレーバーテキスト
3.  **なし**: 何も表示されません

**実装アプローチ:**
`effects` リスト内の `APPLY_BUFF` 要素に、直接 `flavor` キーとテキストを追加します。

**スキルデータ設定例:**
```json
{
  "effects": [
    {
      "type": "APPLY_BUFF",
      "buff_name": "恐怖",
      "lasting": 1,
      "flavor": "足がすくんで思うように動けない……。"
    },
    {
      "type": "APPLY_BUFF",
      "buff_name": "加護_DaCut20",
      "lasting": 3,
      "flavor": "聖なる光が身体を包み込む。"
    }
  ]
}
```

---

## 3. 実装が必要なファイル一覧
(以下変更なし)
(以下変更なし)
(以下変更なし)

上記の実装を行うために、主に以下のファイルを編集・作成する必要があります。

| ファイルパス | 役割 | 編集内容 |
| :--- | :--- | :--- |
| `buff_catalog_cache.json` | バフ定義データベース | 新規バフID、名前、説明、効果プラグインの登録 |
| `manager/buff_catalog.py` | バフ効果ロジック | `DYNAMIC_PATTERNS`へのパターン追加（2倍系など） |
| `manager/game_logic.py` | スキル処理コア | `process_skill_effects`の拡張（ランダムターゲットなど） |
| `manager/room_manager.py` | 部屋・ゲーム進行管理 | ラウンド終了処理（時限発動、出血維持など）の修正 |
| `plugins/*.py` | カスタム効果実装 | 個別の特殊効果ロジック記述（新規作成） |
