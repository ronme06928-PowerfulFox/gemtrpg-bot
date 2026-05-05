# 22. 特殊蓄力・特殊凝魔（variant）仕様書
最終更新: 2026-05-05

## 1. 目的
本書は、`凝魔` / `蓄力` の「特殊化（variant化）」仕様を、実装ベースで一元化する。

- 対象コード:
  - `manager/utils.py`
  - `manager/game_logic.py`
  - `plugins/burst.py`
  - `static/js/modals.js`
- 対象テスト:
  - `tests/test_stack_resource_variants.py`
  - `tests/test_rupture_burst_consumption.py`

## 2. 共通モデル（特殊凝魔・特殊蓄力）
`凝魔` / `蓄力` は、いずれも「スタック資源 + variant」の共通モデルで扱う。

- 資源本体:
  - `凝魔`: `Bu-31`
  - `蓄力`: `Bu-30`
- variantキー:
  - `variant`（buff row直下 or `data.variant`）
- 変換エフェクト:
  - `CONVERT_STACK_RESOURCE_VARIANT`
- 基本ルール:
  1. variant変換はスタック数を保持する
  2. 変換対象スタックが不足（通常 `require_count_gte=1`）なら不発
  3. 一度variant化した後も、加算/消費後にvariantは保持される

## 3. 特殊凝魔（凝魔-血漿）
### 3.1 variant名
- `blood_plasma`

### 3.2 変換
- `CONVERT_STACK_RESOURCE_VARIANT` で `to_variant: "blood_plasma"` を指定

### 3.3 効果差し替え
- 通常凝魔の基礎効果（魔法補正への10刻み加算）を無効化
- 代替で以下を有効化:
  - 自分以外へ出血付与時: `floor(凝魔スタック / 10)` を加算
  - 自分の出血参照値: `凝魔スタック` を加算

## 4. 特殊蓄力（蓄力-誘爆）
### 4.1 variant名
- 正式: `burst_guidance`
- 互換alias:
  - `explosion_guidance`
  - `induce_burst`
  - `induced_burst`

### 4.2 変換（爆破誘導）
- `CONVERT_STACK_RESOURCE_VARIANT` で `to_variant: "burst_guidance"` を指定

### 4.3 効果差し替え
- 通常蓄力の基礎効果（物理補正への10刻み加算）を無効化
- 代替で以下を有効化（HIT時の自動誘爆）:
  1. 攻撃者と対象が敵対陣営
  2. 対象の破裂が `1` 以上
  3. 攻撃者の蓄力variantが `burst_guidance` 系
  4. 攻撃者の蓄力スタックが `10` 以上
  5. 条件を満たしたら蓄力を `10` 消費して `破裂爆発` を発動
  6. この誘爆由来の破裂爆発は `no_rupture_consume=True` で実行し、対象の破裂を消費しない

### 4.4 1ヒット解釈
- 実装上は `HIT` タイミング解決単位で判定
- 範囲攻撃は対象ごとに `HIT` 解決するため、対象ごとに個別判定される

## 5. UI表示仕様
- `Bu-31 + blood_plasma` は表示上 `Bu-48`（凝魔-血漿）として扱う
- `Bu-30 + burst_guidance系` は表示上 `Bu-49`（蓄力-誘爆）として扱う
- 対象実装: `static/js/modals.js`

## 6. JSONビルダー運用
自然言語からの変換では、以下の解釈を使う。

- `血漿転化`:
  - `CONVERT_STACK_RESOURCE_VARIANT`
  - `buff_name: "凝魔"`
  - `to_variant: "blood_plasma"`
- `爆破誘導`:
  - `CONVERT_STACK_RESOURCE_VARIANT`
  - `buff_name: "蓄力"`
  - `to_variant: "burst_guidance"`

## 7. 実装上の注意点
1. variantを使う設計では、既存の通常スタック基礎補正と二重適用しないこと
2. variant情報は `APPLY_BUFF` の再適用時に消さないこと（`data.variant` 維持）
3. 破裂爆発の共通実装（`plugins/burst.py`）を使い、特殊蓄力だけ別実装に分岐させないこと

## 8. 現時点の未確定事項（拡張検討）
1. `蓄力-誘爆` の1ターン発動上限を設けるか
2. 連続再使用（`USE_SKILL_AGAIN`）時の誘爆回数制御を行うか
3. 将来的な「特殊蓄力variant」追加時に aliasポリシーをどう統一するか

