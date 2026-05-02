# 23. 自然言語JSON生成（3列入力運用）仕様案

## 1. 目的
- スプレッドシート運用の現行構造（`使用時効果` / `発動時効果` / `特記`）を維持したまま、`skill_json_rule_v2` のJSONを安定生成する。
- 完全自由文の直接変換を避け、運用上の記述揺れを抑えた「半構造化自然言語」から決定的に変換する。
- 変換不能・曖昧な入力は停止し、誤ったJSONを出力しない。

## 2. 対象範囲
- 対象データ
1. スキル特記JSON（`rule_data`）
2. バフ付与を含む効果定義（`effects`）
3. コスト定義（`cost`）

- 出力スキーマ
1. `schema: "skill_json_rule_v2"` を必須出力
2. `id` は任意入力（推奨）
3. `strict=false運用時でも、生成器はv2正規形で出力`

## 3. 入力インターフェース（運用固定）
- 必須入力
1. `使用時効果`（コスト欄）
2. `発動時効果`（effect欄）
3. `特記`（power_bonus/補助effect欄）

- 任意入力
1. `タグ`（例: `広域`, `マッチ不可`, `self_target`）
2. `target_scope`
3. `skill_id`（JSONの`id`）

## 4. 変換方針（列ごとの専用パーサ）

### 4.1 使用時効果 -> `cost[]`
- 例: `FPを2消費` -> `{"type":"FP","value":2}`
- 複数コストは句点・読点・改行で分割し、配列で出力。
- 正規化ルール
1. `FPをN消費` -> `FP:N`
2. `MPをN消費` -> `MP:N`
3. `HPをN消費` -> `HP:N`

### 4.2 発動時効果 -> `effects[]`
- timing語彙を固定辞書で正規化して `timing` に変換。
- 効果語彙を固定辞書で `type` / 必須キーへ展開。
- 1セルに複数効果がある場合は、文分割して個別effectに変換。

### 4.3 特記 -> `power_bonus[]` + 補助`effects[]`
- 原則、計算補正は `power_bonus` に変換。
- 条件付き付与や特殊処理（崩壊・爆発・再使用など）は `effects` へ追加。
- `最大N` は `max_bonus` / `max_value` へ変換する。

## 5. 正規化辞書（初期案）

### 5.1 timing辞書
1. `使用時` -> `PRE_MATCH`
2. `的中時` -> `HIT`
3. `中時` / `命中時` は互換入力として `HIT` 扱い
4. `勝利時` -> `WIN`
5. `敗北時` -> `LOSE`
6. `ラウンド終了時` -> `END_ROUND`
7. `マッチ終了時` -> `END_MATCH`

### 5.2 target辞書
1. `自分` / `このキャラクター` -> `self`
2. `対象` / `相手` -> `target`
3. `味方全体` -> `ALL_OTHER_ALLIES`（必要時）

### 5.3 state辞書
1. `出血` -> `state_name: "出血"`
2. `破裂` -> `state_name: "破裂"`
3. `亀裂` -> `state_name: "亀裂"`
4. `戦慄` -> `state_name: "戦慄"`

### 5.4 effect辞書（主要）
1. `NラウンドのXをM付与` -> `APPLY_STATE` + `extra_json.rounds`
2. `XをM付与` -> `APPLY_STATE`
3. `buff_id=Bu-xxを付与` -> `APPLY_BUFF`
4. `Xを解除` -> `REMOVE_BUFF`（`buff_id`必須）
5. `ダメージ+N` -> `DAMAGE_BONUS`
6. `基礎威力+N` -> `MODIFY_BASE_POWER` or `power_bonus.FIXED`

## 6. 文分割ルール（必須）
- 分割記号
1. `。`
2. 改行
3. `／`（運用で使う場合）

- 非分割記号
1. `,` は原則同文扱い
2. `()` 内は分割対象外

## 7. 曖昧性処理
- 次のケースはエラー停止（JSON未出力）
1. timingが特定できない
2. `APPLY_BUFF` / `REMOVE_BUFF` で `buff_id` が不明
3. 数値が抽出不能（例: `少し増加`）
4. 条件文の主語が不明（self/target未確定）

- エラー表示要件
1. 列名（使用時効果/発動時効果/特記）
2. 元文
3. 失敗理由
4. 修正例（1件）

## 8. 出力JSONルール
- 常に以下を満たすこと
1. `schema: "skill_json_rule_v2"` を付与
2. `effects` / `power_bonus` / `cost` は未指定でも配列型を維持
3. `APPLY_BUFF` / `REMOVE_BUFF` は `buff_id` を使用
4. 旧式 `buff_name` 単独出力は禁止

## 9. 例（2行）
```json
{"schema":"skill_json_rule_v2","id":"SKILL_EXAMPLE","cost":[{"type":"FP","value":2}],"power_bonus":[{"operation":"FIXED_IF_EXISTS","source":"target","param":"亀裂","threshold":1,"value":1}],"effects":[{"timing":"HIT","type":"APPLY_STATE","target":"target","state_name":"亀裂","value":1,"rounds":3}]}
```
```json
{"schema":"skill_json_rule_v2","id":"SKILL_EXAMPLE2","cost":[{"type":"FP","value":3}],"power_bonus":[{"operation":"PER_N_BONUS","source":"target","param":"亀裂","per_N":1,"value":1,"max_bonus":3}],"effects":[{"timing":"HIT","type":"CUSTOM_EFFECT","target":"target","value":"亀裂崩壊_DAMAGE","damage_per_fissure":3}]}
```

## 10. 実装フェーズ案
### Phase A（先行実装）
1. 3列入力UI + ルールベース変換器
2. timing/effect/stateの固定辞書
3. strict v2バリデーション
4. エラー停止 + 修正ガイド表示

### Phase B（拡張）
1. 同義語辞書の拡張
2. 特記の条件文パーサ強化
3. `[[W-xx]]` 記法の補助正規化

### Phase C（将来）
1. LLM補助生成（下書き）
2. ルールベース検証で最終確定
3. 候補A/B表示（自動確定禁止）

## 11. 決定が必要な事項
1. timing語彙の最終正規表（運用用語の固定）
2. 1セル複数効果の正式区切り（句点のみ/改行含む）
3. 特記で許可する範囲（`power_bonus`のみか、`effects`併用か）
4. `[[W-xx]]` 参照語の辞書化対象（最小集合）

