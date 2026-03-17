**最終更新日**: 2026-03-15
**対象バージョン**: Current
**対象機能**: 新スキル「震盪」(受け手側デバフ版) / スキル拡張時のマニュアル・図鑑更新プロトコル

---

## 1. 目的

本書は次の2点を定義する。

1. 新スキル **「震盪」** の実装案（受け手側デバフとしての実現可能性、実装方式、テスト観点）
2. 今後スキル拡張を行う際に、**内部ロジックだけでなく各種マニュアル・用語図鑑・バフ/デバフ図鑑まで一貫して更新する運用ルール**

既存の提案（`manuals/13_*`, `manuals/14_*` に記載した案）にも適用する。

---

## 2. 新スキル「震盪」実装案（受け手側デバフ）

## 2.1 要件

- 名称: `震盪`
- 種別: `デバフ`
- 効果: **このデバフを受けた対象が「破裂」をスキル効果で付与される時、増加量を +N する**

---

## 2.2 現状ロジックとの適合性

結論: **中〜高。既存基盤 + 軽微なロジック拡張で実装可能。**

理由:

- `manager/game_logic.py::APPLY_STATE` は正値付与時に `calculate_state_apply_bonus(...)` を呼ぶ
- ただし `calculate_state_apply_bonus(...)` は **実行者(actor)側の `special_buffs` のみ参照** しており、受け手(target)側デバフは参照しない
- よって、要件どおり「付与される側」で判定するには target 側参照を追加する必要がある

補足:

- 効果適用アクションは `APPLY_DEBUFF` ではなく、現行仕様どおり `APPLY_BUFF` を使って target に付与する
- `APPLY_STATE_PER_N` には現状 `state_bonus` 適用処理がないため、震盪対象にしたい場合は同時に拡張する

---

## 2.3 推奨実装方式

## 方式A（推奨）: `state_receive_bonus` を新設

`state_bonus`（付与する側）とは分離し、受ける側専用ルールとして `state_receive_bonus` を導入する。

デバフ定義例:

```json
{
  "name": "震盪",
  "effect": {
    "state_receive_bonus": [
      {
        "stat": "破裂",
        "operation": "FIXED",
        "value": 2,
        "consume": false
      }
    ]
  }
}
```

スキル側（デバフ付与）:

```json
{
  "timing": "HIT",
  "type": "APPLY_BUFF",
  "target": "target",
  "buff_name": "震盪",
  "lasting": 1,
  "delay": 0
}
```

ロジック変更ポイント:

1. `manager/game_logic.py` に `calculate_state_receive_bonus(receiver, source, stat_name, context=None)` を追加
2. `APPLY_STATE` 正値処理で、既存の `state_bonus` に加えて `state_receive_bonus` を加算
3. `APPLY_STATE_PER_N` 正値処理にも同じボーナス加算処理を追加
4. `consume=true` は **受け手(target)側のデバフを消費** する

## 方式B（代替）: `state_bonus` に方向フラグを追加

`state_bonus` へ `applies_on: "source" | "target"` を追加して共通化する方式。

- 利点: キーを増やさずに済む
- 欠点: 既存定義の後方互換と解釈が複雑になる

運用上は、影響範囲を分離しやすい方式Aを推奨。

---

## 2.4 実装時の重要注意点

- 震盪の上乗せは「正の破裂付与」にのみ適用する
  - `破裂-3` のような減少には適用しない
- 適用対象は「スキル効果として処理される付与」に限定する
  - `APPLY_STATE` / `APPLY_STATE_PER_N` 経由
  - `SET_STATUS` など直接代入には適用しない
- 震盪（受け手側）と既存の付与側ボーナスが同時にある場合の扱いを固定する
  - 原則: 合算（例: 付与側+1, 受け手側+2 -> 合計+3）
- `consume=true` の消費元が target であることを厳密に検証する

---

## 2.5 推奨テスト（チェック観点）

- 震盪+2を受けた対象に `破裂+3` を付与すると `+5` になる
- 震盪なしでは `+3` のまま
- 破裂以外（出血、亀裂）には影響しない
- `破裂-3` には上乗せしない
- `consume=true` は1回目のみ上乗せし、2回目は上乗せしない
- `APPLY_STATE_PER_N` 由来の破裂付与にも上乗せされる
- 付与側ボーナスと受け手側ボーナス同時時の合算結果が仕様通り

---

## 3. 変更対象ファイル（震盪）

最低更新:

- `manager/game_logic.py`
  - 受け手側ボーナス計算関数の追加
  - `APPLY_STATE` / `APPLY_STATE_PER_N` への受け手側加算の組み込み
- バフ/デバフ図鑑データソース（Google Sheets 側）
  - 震盪デバフの追加（`state_receive_bonus`）
- スキルデータ
  - `APPLY_BUFF` で target に震盪を付与
- キャッシュ更新（`manager/data_manager.py` のデータ更新フロー）

必要に応じて:

- `manager/buff_catalog.py`（動的パターン化する場合）
- `static/js/buff_data.js`（UI説明の同期）

---

## 4. 実装と同時に行うドキュメント更新プロトコル

## 4.1 基本原則

スキル機能追加時は **「コード変更」と「情報導線更新」を同一PRで完了** させる。

情報導線に含むもの:

- 開発者向け仕様書
- プレイヤー向け説明
- GM向け説明
- 用語図鑑
- バフ/デバフ図鑑表示

---

## 4.2 更新先チェックリスト（標準）

## A. 内部仕様（開発者向け）

- `manuals/03_Integrated_Data_Definitions.md`
  - 新しい `effect` 定義（今回なら `state_receive_bonus`）
  - effect JSON 拡張項目（例: `repeat_count`）の既定値・上限・エラー条件
- `manuals/07_Skill_Logic_Reference.md`
  - 処理順、条件判定、適用タイミング、consume対象
  - 反復実行系の順序（展開タイミング、1回ごとの判定、ログ仕様）
- `manuals/08_SelectResolve_Spec.md`
  - Select/Resolve で影響がある場合（対象選択・宣言可否・resolve順）

## B. 利用者向けマニュアル

- `manuals/01_Integrated_Player_Manual.md`
  - プレイヤー視点の効果説明
- `manuals/02_Integrated_GM_Creator_Manual.md`
  - 設定方法、入力例、裁定時注意
- `manuals/04_Character_Build_Guide.md`
  - ビルド選択に影響する場合のみ追記

## C. 図鑑/辞書

- 用語図鑑データ（Glossaryシート）
  - 新語追加（例: 震盪）
  - 関連語リンク更新（破裂、状態異常、付与）
- バフ/デバフ図鑑データ（Buff Catalogシート）
  - 名称、種別（debuff）、説明、effect JSON
- フロント表示定義
  - `static/js/buff_data.js` の説明整合

## D. テスト

- 単体テスト（震盪あり/なし、consume挙動）
- 仕様テスト（スキル定義lint、smoke）
- 既存回帰（破裂/亀裂まわり）
- JSON拡張時の lint 項目追加（例: `repeat_count` の型・範囲）

---

## 4.3 effect JSON 拡張時の追加ルール

`effects[]` の新フィールドや新記法（例: 同一効果複数回発動）を導入する場合は、以下を必須とする。

1. **03に仕様を明記**
   - フィールド名
   - 型
   - 既定値
   - 許容範囲
   - 異常値の扱い
2. **07に実行順を明記**
   - 展開タイミング
   - 1回ごとの条件判定有無
   - target再解決の有無
3. **lint/smoke を更新**
   - `tests/test_skill_catalog_smoke.py` の shape/field 検証
4. **上限を設定**
   - 大量展開で処理が不安定化しないよう、上限値を必ず持つ
5. **後方互換を明示**
   - 既存データが未指定でも従来動作になること

---
## 4.4 実装完了条件（Definition of Done）

以下を全て満たした時に「完了」とする。

1. 受け手側デバフとしてのロジック実装が完了
2. `APPLY_STATE` / `APPLY_STATE_PER_N` のテストが追加・更新済み
3. 03/07（必要なら08）へ仕様反映済み
4. 01/02（必要なら04）へユーザー説明反映済み
5. 用語図鑑に新語・リンクが反映済み
6. バフ/デバフ図鑑表示が反映済み
7. データ更新手順（キャッシュ反映）を実施済み
8. JSON拡張がある場合、03/07/lint の3点同期が完了

---

## 5. 既存提案（manuals/13, 14）への適用方針

## 5.1 「これまでの分」も同じ更新ルールで扱う

既存提案群:

- 行動阻害/封印/追加コスト
- フォールバック技
- 逆襲
- 気合い
- 経過ターン条件
- ランダムターゲット
- 同一効果の複数回発動 JSON 記法
- （今回）震盪（受け手側デバフ）

全てに対して、4章の更新先チェックリストを適用する。

## 5.2 追記優先度

1. まず `03` と `07` を更新（仕様が曖昧なまま実装しない）
2. 影響がUI/宣言フローに及ぶ場合は `08` を更新
3. その後 `01` / `02` / 図鑑系を更新
4. 最後にビルドガイド系（`04`）を必要分のみ更新

---

## 6. 震盪のドキュメント反映テンプレート（コピペ用）

## 6.1 03（Data Definitions）追記テンプレ

- 受け手側状態ボーナス `state_receive_bonus` を追記
- 例:
  - `stat="破裂"`
  - `operation="FIXED"`
  - `value=2`
  - `consume=false/true`

## 6.2 07（Skill Logic）追記テンプレ

- `APPLY_STATE` 正値処理時に `state_receive_bonus` を評価すること
- `APPLY_STATE_PER_N` 正値処理時も同様に評価すること
- `consume=true` は target 側の震盪を消費すること

## 6.3 01/02（プレイヤー・GM）追記テンプレ

- 「震盪: 受ける破裂付与量を増やすデバフ」
- 使用例（誰に付けると有効か）
- 重複可否と持続条件

## 6.4 用語図鑑追記テンプレ

- 新語ID: 例 `W-SHINDOU`
- 表示名: `震盪`
- short: `受ける破裂付与量を増やすデバフ`
- long: `このデバフを受けた対象がスキル効果で破裂を付与される際、その増加量を+Nする`
- links: `破裂`, `状態異常`, `付与`

## 6.5 バフ/デバフ図鑑追記テンプレ

- 名称: `震盪`
- 種別: `debuff`
- 説明: `受ける破裂付与量 +N`
- effect JSON: `state_receive_bonus` 定義
- UI説明（`static/js/buff_data.js`）も同文言に合わせる

## 6.6 効果JSON拡張（repeat等）追記テンプレ

- 追加キー: 例 `repeat_count`
- 型/既定値/範囲: 例 `int`, default `1`, range `1..20`
- 実行意味:
  - `repeat_count=N` は同一 effect を N 回手書きした場合と同等
- lint条件:
  - 0以下や上限超過はエラー
- 実装参照:
  - `manager/game_logic.py`（展開処理）
  - `tests/test_skill_catalog_smoke.py`（field検証）

---

本書は「震盪（受け手側デバフ）」導入時の設計・運用ガイドであり、同時に今後のスキル拡張全体に適用する更新プロトコルである。実装後は `03/07/08` の統合仕様へ確定反映すること。
