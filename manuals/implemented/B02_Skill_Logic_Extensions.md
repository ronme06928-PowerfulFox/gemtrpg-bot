<!-- 旧: 11_Advanced_Skill_Extensions_Spec / 19_Fallback_Struggle_Spec / 22_Special_Stack_Resource_Variants_Spec を統合 (2026-05-09) -->

# スキルロジック実装リファレンス Part 2: 拡張機能

**最終更新日**: 2026-05-09
**系統**: B — 戦闘・スキル仕様
**統合元**: 11_Advanced_Skill_Extensions_Spec / 19_Fallback_Struggle_Spec / 22_Special_Stack_Resource_Variants_Spec

---

## 本書の構成

- Part 1: → B01_Skill_Logic_Core.md（effect処理基本・条件・亀裂）
- Part 2（本書）: 拡張機能 — スキル付与/召喚/自滅/フォールバック/スタックVariant
- 戦闘進行: → B03_SelectResolve_Spec.md

---

**最終更新日**: 2026-02-23
**対象バージョン**: Current
**対象機能**: `GRANT_SKILL` / 召喚（次ラウンド行動開始） / 自滅タグ / 死亡時効果の設計指針

---

## 1. 目的

本ドキュメントは、以下の新規拡張仕様を定義する実装ガイドです。

- 既存スキルIDを指定して味方へスキル付与する `GRANT_SKILL`
- 召喚体を「召喚ラウンドは行動不可、次ラウンドから行動可」にする
- スキルに `自滅` タグが付与されている場合、スキル処理完了後に術者が死亡する
- 死亡時効果（`on_death`）を持つスキル/バフの実装見通し

---

## 2. `GRANT_SKILL` 仕様

### 2.1 概要

`GRANT_SKILL` は `effects[].type` として定義し、対象キャラクターへ既存スキルを一時または永続で付与します。

- 付与対象スキルは `skill_id` で指定する（`all_skill_data` に存在するID）
- 付与はキャラの `commands` へ反映し、通常のスキル選択UIから使用可能にする

### 2.2 データ定義

```json
{
  "timing": "HIT",
  "type": "GRANT_SKILL",
  "target": "target",
  "target_scope": "ally",
  "skill_id": "Ps-10",
  "grant_mode": "duration_rounds",
  "duration": 3,
  "overwrite": true
}
```

### 2.3 パラメータ

- `timing` (必須)
  - 既存の任意タイミングを使用可能（`HIT`, `WIN`, `PRE_MATCH`, `END_MATCH` など）
- `target` (必須)
  - `target` (単体), `ALL_ALLIES` (術者を含む味方全体), `ALL_OTHER_ALLIES` (術者を除く味方全体)
- `target_scope` (任意, `target` の時のみ有効)
  - `enemy` / `ally` / `any`
  - 未指定時の既定値は `enemy`
  - `target_scope` 未指定時でも、`tags` の `味方指定` / `ally_target` / `target_ally` は `ally` として解釈される
- `skill_id` (必須)
  - 付与する既存スキルID
  - 未定義IDは不発（ログ出力）
- `grant_mode` (必須)
  - `permanent` : 永続
  - `duration_rounds` : 一定ラウンド継続
  - `usage_count` : 一定回数使用可能
- `duration` (任意)
  - `grant_mode=duration_rounds` の時に必須
- `uses` (任意)
  - `grant_mode=usage_count` の時に必須
- `custom_name` (任意)
  - `commands` 表示名の上書き。未指定時はデフォルト名
- `overwrite` (任意)
  - 同一 `skill_id` が既に付与済みの場合の挙動
  - `true`: 既存付与を上書き（今回の標準運用）
  - `false`: 既存付与を維持して新規付与を無視

### 2.4 3パターンの管理方式

#### A. 永続 (`permanent`)

- 付与時に `commands` に追記
- 解除処理なし
- 重複付与時は多重追記を防止

#### B. 一定ラウンド (`duration_rounds`)

- 付与時に `granted_skills` 管理配列へ登録
  - 例: `{ skill_id, mode: 'duration_rounds', remaining_rounds: 2 }`
- ラウンド終了時に `remaining_rounds--`（付与ラウンド終了時を含む）
- `0` になったら該当スキル行を `commands` から削除

#### C. 一定回数 (`usage_count`)

- 付与時に `granted_skills` へ登録
  - 例: `{ skill_id, mode: 'usage_count', remaining_uses: 3 }`
- 該当スキルが実際に使用されたタイミングで `remaining_uses--`
- `0` 到達で `commands` から削除

### 2.5 付与情報の推奨保持形式

対象キャラに以下の配列を追加する。

```json
"granted_skills": [
  {
    "skill_id": "Ps-10",
    "mode": "duration_rounds",
    "remaining_rounds": 2,
    "remaining_uses": null,
    "source_actor_id": "char_x",
    "source_skill_id": "Ps-99",
    "granted_at_round": 5,
    "custom_name": null,
    "injected": true
  }
]
```

補足:

- `commands` は最終表示・選択の実体
- `granted_skills` は寿命管理の実体
- `injected=true` は「付与時に commands へ行を追加した」ことを示す
  - 元々そのスキルを所持していた場合は `injected=false` とし、解除時に元スキル行を消さない
- どちらか一方だけだと保守性が下がるため、二層管理を推奨

### 2.6 実装適用ポイント（現実装）

- 効果生成: `manager/game_logic.py::process_skill_effects`
  - `GRANT_SKILL` と `ALL_OTHER_ALLIES` を解釈
  - 補助処理は `manager/battle/skill_effect_helpers.py` に分離
- 効果反映:
  - `manager/battle/core.py`（Select/Resolve）
  - `manager/battle/duel_solver.py`（通常マッチ/即時）
  - `manager/battle/wide_solver.py`（広域）
  - `manager/skill_effects.py`（双方向適用ヘルパー）
- 付与実体管理: `manager/granted_skills/service.py`
  - 付与/上書き、回数消費、ラウンド減衰、コマンド行追加/削除
- ラウンド終了減衰:
  - `manager/battle/common_manager.py::process_full_round_end`
  - `manager/battle/core.py::process_simple_round_end`
- 単体対象のチーム制約:
  - サーバー: `events/battle/common_routes.py` で `target_scope` 検証
  - UI: `static/js/battle/components/DeclarePanel.js` で候補フィルタ
  - Resolve: `target_scope=ally` のスキルは redirect に参加せず、同一陣営相互指定でも `clash` を組まず `one_sided` 扱い

### 2.7 UI表示仕様（利用者向け）

- 付与スキルはキャラクター詳細の `Skills` 一覧で黄色系に強調表示される
- 付与スキルをクリックしたスキル詳細では、上部に付与状態バッジを表示する
  - `付与スキル`
  - `残りX R`（`duration_rounds` の時）
  - `残りX回`（`usage_count` の時）
  - `永続`（`permanent` の時）
- 表示ソースは対象キャラの `granted_skills[]` を参照し、`skill_id` 単位で照合する

---

## 3. 召喚仕様（次ラウンド行動開始 + 持続モード）

### 3.1 仕様要件

- 召喚体は召喚されたラウンドでは行動不可
- 次の `RoundStart` から通常通りスロット生成され、行動可能になる
- 召喚体は「永続」または「一定ラウンド継続」を設定可能

### 3.2 データ定義（推奨）

```json
{
  "timing": "HIT",
  "type": "SUMMON_CHARACTER",
  "target": "self",
  "summon_template_id": "SMN-01",
  "summon_duration_mode": "duration_rounds",
  "summon_duration": 3
}
```

### 3.3 持続モード

- `summon_duration_mode: permanent`
  - 永続召喚
  - 明示的な解除処理（死亡、手動削除、別効果）まで残る

- `summon_duration_mode: duration_rounds`
  - 一定ラウンド継続
  - `summon_duration` ラウンド経過後に自動消滅

### 3.4 推奨保持フィールド

召喚体キャラに以下を保持する。

- `summoned_round`: 召喚されたラウンド番号
- `can_act_from_round`: `summoned_round + 1`
- `summon_duration_mode`: `permanent` または `duration_rounds`
- `remaining_summon_rounds`: `duration_rounds` の場合のみ保持
- `summoner_id`: 召喚者キャラID（ログ・参照用）

### 3.5 行動開始制御

`process_select_resolve_round_start(...)` の行動可能判定で以下を追加:

- `state.round < char.can_act_from_round` の場合、そのキャラのスロットを生成しない

### 3.6 消滅処理

- `summon_duration_mode=duration_rounds` の召喚体は、ラウンド終了処理で `remaining_summon_rounds--`
- `0` になった時点で盤面から除去（`characters` から削除）
- 除去時はログを残す（例: `○○は時間切れで消滅した`）

これにより、Select/Resolve の全ロジックを壊さず要件を満たせる。

### 3.7 UI上の扱い（利用者向け）

- 期限切れで消滅した召喚体、および戦闘不能になった召喚体は、未配置モーダルに表示しない
- 召喚体の継続情報はキャラクター詳細の「特殊効果 / バフ」内に表示する
  - `duration_rounds` のみ `残りX R` を表示
  - `permanent` はラウンド数を表示しない

---

## 4. 自滅タグ仕様

### 4.1 要件

- スキルに `自滅` タグがある場合、スキル効果の処理が完了した後で術者が死亡する
- 「処理完了後」であることが重要（先に死なない）

### 4.2 推奨発火順

1. 通常の効果解決（ダメージ・付与・再使用差し込みなど）
2. すべての変更反映完了
3. タグ判定（`自滅`）
4. 術者のHPを `0` に設定
5. 既存の死亡フック（`process_on_death`）を通常通り起動

### 4.3 実装ポイント

- 共通ヘルパー: `apply_self_destruct_if_needed(room, actor, skill_data)`
- `skill_data.tags` と `rule_data.tags` の両方を見て判定する
- 現行（2026-02-25時点）では、Select/Resolve本体 (`manager/battle/core.py`) で
  - 通常マッチ（clash）後
  - 一方攻撃（one_sided）後
  に自滅判定を実行する
- 自滅した行動者には再使用予約（`USE_SKILL_AGAIN`）を積まない

---

## 5. 死亡時効果持ちスキルの実装見通し

### 5.1 既存基盤

現行コードには以下が既にある。

- HPが0以下になった時に `process_on_death` が呼ばれる
- `special_buffs` / パッシブの `on_death` を `process_skill_effects(..., timing='IMMEDIATE')` で処理できる

このため「死亡時効果を持つ"スキル"」は、実質的に次の2方式で実現可能。

### 5.2 方式A（推奨）: スキルで死亡時バフを付与する

1. スキルの通常効果で `APPLY_BUFF` を自分や味方へ付与
2. 付与されるバフ定義に `on_death` を記述
3. 対象が死亡した時に自動発火

利点:

- 既存の `process_on_death` をそのまま使える
- 管理がバフ定義に集約される
- スキル本体ロジックを増やしにくい

### 5.3 方式B: スキル単位の死亡予約を直接持つ

- スキル使用時にキャラへ `death_triggers` を直接積む方式
- 実装自由度は高いが、既存のバフ基盤と二重管理になりやすい

結論:

- まずは方式Aで十分。特殊要件が出た場合のみ方式Bを検討する。

### 5.4 注意点（設計）

- 多段死亡ダメージで `process_on_death` が複数回走らないよう再入防止を入れる
  - 例: `flags.on_death_processed_round = state.round`
- 自滅タグと死亡時効果が連鎖する場合の順序を固定する
  - 「スキル効果完了 -> 自滅 -> 死亡時効果」
- 蘇生がある場合は `on_death` 再発条件を明文化する

---

## 6. 実装チェックリスト

- `GRANT_SKILL` を `process_skill_effects` の `effect_type` に追加
- `commands` 追記/削除ユーティリティを実装（重複防止あり）
- `granted_skills` のラウンド減算処理をラウンド終了処理へ追加
- `usage_count` 減算処理をスキル実行確定箇所へ追加
- 召喚体の `can_act_from_round` 判定を RoundStart スロット生成に追加
- `自滅` タグの共通処理ヘルパーを各解決経路から呼び出し
- 回帰テスト追加（grant3種、召喚遅延、自滅順序、死亡時連動）

---

## 7. テスト観点（最小）

- `GRANT_SKILL/permanent`: 再ログイン後も使用可能
- `GRANT_SKILL/duration_rounds`: 指定ラウンド後に自動消滅
- `GRANT_SKILL/usage_count`: 使用回数0で自動消滅
- 召喚体: 召喚ラウンドはスロット0件、次ラウンドでスロット生成
- 自滅タグ: ダメージ適用後に術者HP0化し、死亡時効果が発火

---

本書は実装着手前の設計合意用ドキュメントです。実装後は `C01_JSON_Definition_Master.md` / `B01_Skill_Logic_Core.md` へ仕様統合してください。

---

## フォールバックスキル: SYS-STRUGGLE / どうにかもがく（統合）

**最終更新日**: 2026-04-24  
**対象バージョン**: Current  
**対象機能**: `SYS-STRUGGLE / どうにかもがく`

---

## 1. この仕様の目的（SYS-STRUGGLE）

`SYS-STRUGGLE` は、通常の使用可能スキルが 1 つもない状況で「行動不能にならない」ための最終手段スキルです。  
このスキルは直接攻撃を行うためではなく、解決フェーズ中に自動防御の準備を行うために使います。

---

## 2. スキルの基本情報（SYS-STRUGGLE）

- スキルID: `SYS-STRUGGLE`
- スキル名: `どうにかもがく`
- 分類: `防御`
- 対象: `自分`
- 基礎威力: `0`
- ダイス威力: `0`

説明文:

- 特記: 物理補正もしくは魔法補正のうち、より高い方の値をこのスキルの威力として扱う。
- 発動時効果: (ラウンド終了時):物理補正を参照したなら、FPを1得る。魔法補正を参照したなら、MPを1得る。

---

## 3. 出現条件（SYS-STRUGGLE）

`SYS-STRUGGLE` は次の条件を満たすときだけ使用可能です。

- 通常スキルの使用可能候補が 0 件

通常スキルが 1 件でも使える場合は候補に出ません。  
この判定は UI だけでなく、`battle_intent_commit` と `battle_intent_change_skill` でもサーバー側で再検証します。

---

## 4. 威力の決まり方（SYS-STRUGGLE）

`どうにかもがく` の威力は、ダイスではなく補正値の比較で決まります。

- 威力 = `max(物理補正, 魔法補正)`
- 同値なら `物理補正` を優先

例:

1. `物理補正=4`, `魔法補正=7` の場合: 威力は `7`（魔法補正参照）
2. `物理補正=6`, `魔法補正=6` の場合: 威力は `6`（物理補正参照）

---

## 5. 自動防御の流れ（SYS-STRUGGLE）

### 5.1 宣言時

`どうにかもがく` を宣言すると、その解決フェーズ中のみ有効な自動防御チャージを 1 つ獲得します。

### 5.2 発動時

チャージを持つキャラクターが一方攻撃を受けたとき、チャージを 1 つ消費して自動防御を発動します。  
解決は通常の `attack vs defense` マッチとして扱います。

### 5.3 複数回宣言した場合

同じ解決フェーズ中に複数回 `どうにかもがく` を使用していれば、使用回数分だけチャージを持てます。  
一方攻撃を受けるたびに 1 つずつ消費されます。

### 5.4 持ち越し

未使用チャージは次の解決フェーズに持ち越しません。

---

## 6. ラウンド終了時の回復（SYS-STRUGGLE）

回復は「自動防御が実際に発動し、威力参照まで行われた回数」に対して発生します。

- 物理補正を参照した防御 1 回ごとに `FP +1`
- 魔法補正を参照した防御 1 回ごとに `MP +1`

複数回自動防御が発動した場合は、その回数分だけ回復します。

---

## 7. ログ表示の方針（SYS-STRUGGLE）

自動防御専用の特別ログは追加しません。  
通常のマッチと同じ表示ルールで、解決フェーズと結果ログに出力します。

---

## 8. 処理順の要点（SYS-STRUGGLE）

処理順の意図をまとめると次の通りです。

1. 使用可能スキル判定で通常候補が 0 件なら `SYS-STRUGGLE` を許可
2. `SYS-STRUGGLE` 宣言時に自動防御チャージを獲得
3. 一方攻撃を受けた時にチャージを消費して `clash` として解決
4. 解決時にどの補正を参照したかを保持
5. ラウンド終了時に保持情報を見て `FP` または `MP` を回復
6. 解決フェーズ終了時に未使用チャージを破棄

---

## 9. 実装ファイル（SYS-STRUGGLE）

- システムスキル定義: `manager/battle/system_skills.py`
- 使用可能判定: `manager/battle/skill_access.py`
- プレビュー/威力計算: `manager/game_logic.py` 互換入口、実体は `manager/battle/power_preview.py` / `manager/battle/buff_power.py`
- 宣言検証: `events/battle/common_routes.py`
- 単体解決/自動防御消費: `manager/battle/resolve_auto_single_phase.py`
- ラウンド終了時回復: `manager/battle/common_manager.py`
- 宣言UI: `static/js/battle/components/DeclarePanel.js`

---

## 10. 検証済みテスト（SYS-STRUGGLE）

- `tests/test_sys_struggle.py`
- `tests/test_target_scope_aliases.py`
- `tests/test_skill_catalog_smoke.py`
- `tests/test_select_resolve_smoke.py`

---

## 特殊スタックリソースVariant仕様（統合）

最終更新: 2026-05-05

## 1. 目的（スタックVariant）

本書は、`凝魔` / `蓄力` の「特殊化（variant化）」仕様を、実装ベースで一元化する。

- 対象コード:
  - `manager/utils.py`
  - `manager/game_logic.py`
  - `manager/battle/dice_command.py`
  - `manager/battle/condition_eval.py`
  - `manager/battle/skill_effect_helpers.py`
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

## 5. UI表示仕様（スタックVariant）

- `Bu-31 + blood_plasma` は表示上 `Bu-48`（凝魔-血漿）として扱う
- `Bu-30 + burst_guidance系` は表示上 `Bu-49`（蓄力-誘爆）として扱う
- 対象実装: `static/js/modals.js`

## 6. JSONビルダー運用（スタックVariant）

自然言語からの変換では、以下の解釈を使う。

- `血漿転化`:
  - `CONVERT_STACK_RESOURCE_VARIANT`
  - `buff_name: "凝魔"`
  - `to_variant: "blood_plasma"`
- `爆破誘導`:
  - `CONVERT_STACK_RESOURCE_VARIANT`
  - `buff_name: "蓄力"`
  - `to_variant: "burst_guidance"`

## 7. 実装上の注意点（スタックVariant）

1. variantを使う設計では、既存の通常スタック基礎補正と二重適用しないこと
2. variant情報は `APPLY_BUFF` の再適用時に消さないこと（`data.variant` 維持）
3. 破裂爆発の共通実装（`plugins/burst.py`）を使い、特殊蓄力だけ別実装に分岐させないこと

## 8. 現時点の未確定事項（拡張検討）

1. `蓄力-誘爆` の1ターン発動上限を設けるか
2. 連続再使用（`USE_SKILL_AGAIN`）時の誘爆回数制御を行うか
3. 将来的な「特殊蓄力variant」追加時に aliasポリシーをどう統一するか
