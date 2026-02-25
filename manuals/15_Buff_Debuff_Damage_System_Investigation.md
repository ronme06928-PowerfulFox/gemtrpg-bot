# 15_Buff_Debuff_Damage_System_Investigation.md

更新日: 2026-02-25
対象: Gem_DiceBotTool バトル処理（duel / wide / select-resolve）

## 1. 調査スコープ

本書は以下を調査した。

- 被ダメージアップ / 被ダメージダウン / 与ダメージアップ / 与ダメージダウンの現状実装
- 状態異常・バフ・デバフの再付与時挙動（上書き / スタック加算 / 無視）
- 異なるスキル・名称による同等効果バフ（例: `ATK5` と `ATK3`）の合算可否
- バフ・デバフ付与経路の設計妥当性
- 新規実装推奨内容

---

## 2. 4種ダメージ増減バフ・デバフの現状

### 2.1 被ダメージアップ / 被ダメージダウン

実装あり。

- 動的命名規則で `DaIn` / `DaCut` を定義
- `DaIn`: 被ダメ倍率 `1.0 + x%`
- `DaCut`: 被ダメ倍率 `1.0 - x%`（下限0）

参照:

- `manager/buff_catalog.py:146` (`DaIn`)
- `manager/buff_catalog.py:155` (`DaCut`)
- `manager/game_logic.py:1237` (`calculate_damage_multiplier`)
- `manager/battle/core.py:1783`（select-resolveの最終ダメージに倍率適用）
- `manager/battle/wide_solver.py:345`（wideの最終ダメージに倍率適用）
- `manager/battle/duel_solver.py:720` ほか（duelの多くの分岐で倍率適用）

補足:

- `calculate_damage_multiplier` は `special_buffs` の各要素から `damage_multiplier` を読んで乗算する実装（加算ではなく乗算）。

### 2.2 与ダメージアップ / 与ダメージダウン

「与ダメージ倍率」としては未実装。

現状あるものは次の代替ルート。

- スキル威力の定数補正（`_AtkN` / `_AtkDownN` の `power_bonus`）
- 固定追加ダメージ（例: 爆縮 +5）

参照:

- `manager/buff_catalog.py:24` (`_AtkN`)
- `manager/buff_catalog.py:48` (`_AtkDownN`)
- `plugins/buffs/implosion.py:34`（与ダメ固定+5）

結論:

- 「最終ダメージに対する与ダメ倍率アップ/ダウン」は現状存在しない。

### 2.3 実データ確認

スキル定義には以下が存在。

- `猛攻の輝き_Atk5`（威力補正）
- `アイツを狙え！_DaIn20`（被ダメアップ）

参照:

- `data/cache/skills_cache.json:15`
- `data/cache/skills_cache.json:1524`

---

## 3. 再付与時挙動（上書き / 加算 / 無視）

### 3.1 状態異常（`states` / `APPLY_STATE`）

基本挙動は「加算」。

- `APPLY_STATE` は現在値に `+value` で適用
- `SET_STATUS` は絶対値上書き
- `set_status_value` は同名stateがあれば更新、なければ追加

参照:

- `manager/game_logic.py:513`（`APPLY_STATE`処理）
- `manager/utils.py:89`（`set_status_value`）

無視されるケース:

- `亀裂` は1ラウンド1回制限（`fissure_received_this_round`）で2回目以降を無視

参照:

- `manager/game_logic.py:522`
- `manager/game_logic.py:587`

### 3.2 バフ・デバフ（`special_buffs`）

#### A. `apply_buff` 経由（主経路）

同名バフは「上書き更新」。

- 同名を1件検索し、既存があれば `existing.update(payload)`
- `lasting` / `delay` は `max()` で延長方向
- 例外: `Bu-11`/`Bu-12`（加速/減速）は `count` を加算スタック

参照:

- `manager/utils.py:118`（`apply_buff`）
- `manager/utils.py:123`（同名検索）
- `manager/utils.py:153`（Bu-11/Bu-12例外）
- `manager/utils.py:179`（update）

#### B. プラグイン `apply()` / 直接append経由

多くは「同名でも別インスタンスを追加（実質スタック）」。

- 例: `confusion.py`, `immobilize.py`, `dodge_lock.py`, `stat_mod.py` は `append`
- 例外: `speed_mod.py` は同 `buff_id` を見て `count` 加算

参照:

- `plugins/buffs/confusion.py:54`
- `plugins/buffs/immobilize.py:50`
- `plugins/buffs/dodge_lock.py:58`
- `plugins/buffs/stat_mod.py:56`
- `plugins/buffs/speed_mod.py:36`

### 3.3 無視ロジック（on_damage系）

`newly_applied=True` のバフは被弾トリガーを発動しない。

参照:

- `manager/utils.py:131`（付与時に `newly_applied=True`）
- `manager/battle/core.py:4055`（on_damageでスキップ）

ただし `newly_applied` のクリアは `duel_solver` にしか明示実装がない。

参照:

- `manager/battle/duel_solver.py:1264`

このため、duel以外の経路では on_damage が長期に発動しない可能性がある（要修正）。

### 3.4 削除挙動

`remove_buff` は「同名を全削除」。

参照:

- `manager/utils.py:183`

---

## 4. 同等効果・別名バフは加算されるか

### 4.1 `ATK5` + `ATK3`

結論: 加算される（最終 +8）。

理由:

- それぞれ別バフ名なら別エントリとして `special_buffs` に残る
- `calculate_buff_power_bonus_parts` が全バフの `power_bonus` を合算

参照:

- `manager/game_logic.py:271`
- `manager/game_logic.py:370`

実測（ローカル確認）:

- `A_Atk5` と `B_Atk3` で `{'final': 8}` を確認

### 4.2 `DaIn20` + `DaIn10`

結論: 加算ではなく乗算（1.2 * 1.1 = 1.32）。

理由:

- `calculate_damage_multiplier` が逐次 `*=` するため

参照:

- `manager/game_logic.py:1259`

### 4.3 同名を再付与した場合

`apply_buff` 経由では別スタック化せず、同一レコード更新。

参照:

- `manager/utils.py:123`
- `manager/utils.py:179`

---

## 5. 付与ルートの整理と妥当性評価

### 5.1 現在の主な付与ルート

1. スキル効果 (`process_skill_effects`) -> `APPLY_BUFF` change -> `apply_buff`
2. アイテム効果 (`plugins/items/buff.py`) -> プラグイン `buff_instance.apply()` or 直接append
3. 輝化スキル (`manager/radiance/applier.py`) -> 直接append
4. 出身ボーナス (`apply_origin_bonus_buffs`) -> `apply_buff`
5. 直接呼び出し（duel/wide/coreで `apply_buff` / `remove_buff` を個別実行）

参照:

- `manager/game_logic.py:625`
- `plugins/items/buff.py:61`
- `plugins/items/buff.py:93`
- `manager/radiance/applier.py:63`
- `events/socket_char.py:70`
- `manager/battle/duel_solver.py:151`
- `manager/battle/wide_solver.py:266`
- `manager/battle/core.py:1598`

### 5.2 評価

現状は「部分的に統一されているが、合理的にまとまり切ってはいない」。

理由:

- 付与経路ごとに「同名再付与ポリシー」が異なる（更新 / append / count加算）
- ダメージ倍率適用が経路で揺れる（duel一部分岐は `混乱` 名だけの手動倍率）
- `newly_applied` のライフサイクルが経路統一されていない
- `skill_effects.py` の重複防止が実質無効（`continue` がコメントアウト）
- `skill_effects.py` の `GRANT_SKILL` 処理で未定義変数 `attacker_char` を参照

参照:

- `manager/battle/duel_solver.py:585`
- `manager/battle/duel_solver.py:610`
- `manager/skill_effects.py:87`
- `manager/skill_effects.py:88`
- `manager/skill_effects.py:168`

---

## 6. 新規実装推奨（優先順）

### P1. 与ダメージ倍率アップ/ダウンの正式実装

目的:

- 4種（被ダメUP/DOWN, 与ダメUP/DOWN）を対称仕様にする

提案:

- バフ効果キーを追加
  - `incoming_damage_multiplier`（現行`damage_multiplier`と統合 or 互換）
  - `outgoing_damage_multiplier`（新規）
- 動的パターンを追加
  - 例: `_DaOutN`（与ダメ+x%）
  - 例: `_DaOutDownN`（与ダメ-x%）

### P2. ダメージ倍率計算の単一路線化

目的:

- duel / wide / select-resolve の挙動差をなくす

提案:

- `compute_damage_multipliers(attacker, defender, context)` を新設
- 全ルートでこの関数のみ使用
- `混乱` 特例の手動実装（duelの一部）を撤去

### P3. バフ再付与ポリシーを明文化して実装一本化

推奨ポリシー例:

- `refresh`: 同名/同IDは1件維持で時間更新
- `stack_count`: countのみ加算（加速・減速・爆縮など）
- `stack_instances`: 同名でも複数保持
- `ignore_if_exists`: 既存時は無視

提案:

- これを `buff_catalog` 側に持たせ、`apply_buff` 一箇所で処理
- プラグイン `apply()` は直接appendせず `apply_buff` を呼ぶ

### P4. `newly_applied` ライフサイクル統一

提案:

- round/phaseの明確なタイミングで全経路共通クリア
- クリア処理を duel 専用から共通管理へ移す

### P5. 既存バグ修正

- `manager/skill_effects.py:168` の未定義 `attacker_char` を修正
- 重複防止の `continue` を仕様に沿って有効化するか、重複許可仕様ならログ文言を修正

### P6. 回帰テスト追加

最低限:

- 与ダメUP/DOWNの倍率適用順テスト
- 同名再付与ポリシー別テスト（refresh/stack/ignore）
- `newly_applied` クリアの全経路テスト
- duel/wide/select-resolve で同入力同結果になる整合テスト

---

## 7. まとめ

- 被ダメUP/DOWNは実装済み、与ダメUP/DOWN（最終ダメ倍率）は未実装。
- 再付与挙動は経路により不統一（更新型とappend型が混在）。
- 別名同等効果（ATK5+ATK3）は加算される。
- 現状の設計は機能追加の蓄積で分散しており、共通化余地が大きい。

