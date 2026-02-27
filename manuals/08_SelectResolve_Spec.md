# 08 Select/Resolve 確定仕様書 v1.2

**最終更新日**: 2026-02-27
**文書バージョン**: v1.5
**対象実装**: `events/battle/common_routes.py` / `manager/battle/common_manager.py` / `manager/battle/core.py`
**版注記**: 本更新で v1.5 相当の仕様差分（味方指定タグの固定ルール）を反映

## 1. 目的・スコープ
本仕様は、現行の逐次手番式を廃止し、1ラウンドを `RoundStart -> Select -> Resolve` で処理するための確定仕様を定義する。

- RoundStart: スロット生成、initiative 決定、timeline 確定
- Select: 全員が全スロットを選択し commit
- Resolve: Mass を最優先し、その後 Single を解決

対象はバトル進行ロジック、選択制約、引き寄せ、解決判定、イベント入出力である。

## 2. 用語（slot, initiative, intent, commit, redirect, no_redirect, mass_individual, mass_summation, one-sided, clash, resolve trace）
- `slot`: 1ラウンド中の1回行動単位。キャラクターの行動回数ぶん生成される。
- `initiative`: スロット単位の行動優先値。RoundStart でロールしてラウンド中固定。
- `intent`: スロットに対する選択内容（`skill_id` と `target`）。
- `commit`: intent を確定する操作。Resolve 進行条件に使用。
- `redirect`: 単体指定時に initiative 差で対象を強制変更する自動処理（引き寄せ）。
- `no_redirect`: 引き寄せ不可/被引き寄せ不可タグ。
- `mass_individual`: 広域-個別。敵全員へ個別に解決する mass。
- `mass_summation`: 広域-合算。攻撃値 A と防御合計 D を対決する mass。
- `one-sided`: 相互指定が成立しない一方的解決。
- `clash`: 相互指定が成立した対決解決。
- `resolve trace`: Resolve 中の各判定結果を逐次記録するログ列。

## 3. フェーズと遷移（select / resolve_mass / resolve_single / round_end）
フェーズは次の固定順で遷移する。

1. `select`
2. `resolve_mass`
3. `resolve_single`
4. `round_end`

遷移条件:
- `select -> resolve_mass`: 行動可能者の全スロットが commit 済み
- `resolve_mass -> resolve_single`: mass 対象の解決完了
- `resolve_single -> round_end`: single 対象の解決完了

## 4. RoundStart（行動回数→スロット生成→スロットごとinitiativeロール→timeline、同速は同速グループだけ追加ロール）
RoundStart は次の順序で処理する。

1. 各キャラクターの行動回数を確定する。
2. 行動回数ぶん `slot` を生成する。
3. 各 `slot` ごとに `initiative` をロールし、ラウンド中固定する。
4. `initiative` 降順で `timeline` を作成する。
5. 同速が存在する場合、同一 initiative の同速グループのみ追加ロールで順序確定する。
6. `加速(Bu-11)` / `減速(Bu-12)` は initiative 計算にのみ反映し、ロール後に解除する。
7. legacy互換として `state.timeline` も同スロットIDで再構築し、`hasActed=false` を初期化する。

## 5. Select（行動可能者のみ、全スロット選択→commitでのみ進行、instantはcommit時発動でスロット消費なし、全公開矢印）
- 選択可能なのは行動可能キャラクターのみ（混乱・行動不能は除外）。
- 対象キャラクターの全スロットに対し `skill_id` と `target` を選択する。
- Resolve への進行は全対象スロットの `commit` 完了時のみ。
- `instant` タグのスキルは `commit` 時に即時発動し、スロットを消費しない（Resolve 対象外）。
- 目標指定は全公開矢印として可視化する。
- `required slots` は「行動可能かつ未消費」のスロットのみ。行動不能者や `committed+instant` は Resolve 必須条件から除外する。

### 5.1 Select UI補正（対象先行）
- 対象選択後、対象条件に合致するスキルのみ候補表示する（逆方向フィルタ）。
- 既に選択済みスキルが新しい対象と非整合になった場合、そのスキル選択は自動で解除する。
- 目的は「宣言可能でない組み合わせ」の commit 前検出。

### 5.2 Select時の権限・入力バリデーション（実装準拠）
- `battle_intent_preview` / `battle_intent_commit` / `battle_intent_uncommit` は、対象 `slot_id` が存在しない場合 `battle_error: unknown slot_id` を返し、状態を変更しない。
- 各 intent イベントは「そのスロットの actor を操作可能なユーザー」だけが実行できる。権限不足時は `battle_error: <event> permission denied` を返し、状態を変更しない。
- `GM` は全キャラクターのスロットを代理操作可能。
- `battle_resolve_confirm` と `battle_resolve_flow_advance_request` は `GM` 専用。

## 6. redirect（自動、init(A)>init(B)でB.target=A、競合は最大initiativeが最終勝者・後から再上書き、同速不可、マッチできなくなった側はone-sided）
- A が単体で B（相手スロット）を target にして commit したとき、`initiative(A) > initiative(B)` なら `B.target = A` に自動変更する。
- 同一 B への redirect 競合は、最大 initiative を持つスロットが最終勝者となる。
- 後から到着したより高 initiative の redirect は再上書き可能。
- 同速（`initiative(A) == initiative(B)`）では redirect 不可。
- redirect の結果、相互指定を失ってマッチできなくなった側は `one-sided` として実行する（対象が盤面に残る限り）。
- 例外: B が「広域スロット（`mass_individual` / `mass_summation`）」を単体 target 中なら、その target は redirect で横取りしない（広域対決の安定化）。
- 追加固定ルール（2026-02-27）: `target_scope=ally`（味方指定）スキルは redirect に参加しない（発生させない/受けない）。

## 7. no_redirect（引き寄せできない/されない、locked_targetでも解除して自由にtarget再選択、過去の引き寄せは無効化され得る）
- `no_redirect` スキルを選択したスロットは、redirect できず、redirect されない。
- `locked_target` 状態でもロックを解除し、自由に target を再選択できる。
- 過去に適用済みの redirect 結果は無効化され得る。
- その結果、相互指定が崩れた引き寄せ側は `one-sided` へ移行し得る。
- 追加固定ルール（2026-02-27）: `target_scope=ally`（味方指定）スキルは宣言時に `no_redirect` 相当として扱う。

## 8. Resolve（処理順：Mass最優先→Singleはtimeline、clashは相互指定のみ、one-sidedの対象は“選択時の対象スロットのactor”、1スロット複数絡みはclash1組のみ、コストは実行時、対象消失＝未配置なら不発）
処理順:
- Mass を最優先で解決する。
- Mass 同士は initiative 降順、同速は追加ロール順。
- Single は timeline 順に解決する。

マッチ生成:
- `clash` は相互指定のみ成立。
- それ以外は `one-sided`。
- `one-sided` の対象は「選択時に指定した対象スロットの actor」とする。
- 追加固定ルール（2026-02-27）: 同一陣営どうしの相互指定で、どちらかが `target_scope=ally`（味方指定）なら `clash` を作らず `one-sided` として扱う。
- 追加固定ルール（2026-02-27）: 同一陣営ペアには再回避差し込み（evade insert）を行わない。

複数絡み制約:
- 1スロットに複数の対戦候補がある場合、`clash` は1組のみ成立（優先者のみ）。
- それ以外の関連解決は `one-sided` とする。

実行時判定:
- コスト消費は「通常解決では実行時」が原則（`mass` は Resolve開始時に先払い）。
- 対象消失は「理由を問わず未配置（盤面から消失）」として扱う。
- 実行時に対象が未配置なら不発（`fizzle`）とする。

### 8.1 Resolve開始時の固定化（snapshot）
- Resolve 開始時に `resolve_snapshot_intents` を作成し、Resolve中はこの snapshot を参照する。
- 目的は、Selectフェーズの後続編集が進行中 Resolve に混入しないようにすること。
- `resolve_snapshot_intents` は `round_end` でクリアする。

### 8.2 進行カウンタ（step_total）の扱い
- `resolve.trace` 各要素は `step` に加えて `step_index` / `step_total` を持つ。
- `step_total` は「mass推定件数 + single推定件数」で初期化し、必要に応じて実件数で増補する。
- 新ラウンドで `trace` が空のとき、前ラウンドの `step_total` は持ち越さない。

### 8.3 非ダメージ・強硬追撃（実装追補）
- `deals_damage=false` のスキルは `one-sided` / `clash` とも HP減算を行わない。
- `tags` に `非ダメージ` / `no_damage` / `non_damage` がある場合も `deals_damage=false` 相当として扱う。
- 上記ケースでは `on_damage` 連鎖も発火しない。
- 強硬タグ側が通常スキルとの clash で敗北した場合、条件一致時に `hard_attack` を1回差し込む。
- 牽制タグ側が勝利した場合、相手の強硬追撃は差し込まない（抑止）。
- 回避タグ側が勝利した場合も、相手の強硬追撃は差し込まない（不発）。
- 牽制/回避により強硬追撃が不発になった場合は、チャットログに理由を出力する。

### 8.4 one-sided の PRE_MATCH 評価（実装追補）
- `one-sided` 解決では、攻撃側の `PRE_MATCH` のみを実行する。
- 防御側スキルは条件参照用データとしては渡すが、防御側自身の `PRE_MATCH` 効果は実行しない。
- 目的: 予約スキル/補助スキルの副作用が、非対決側で重複発火することを防ぐ。

### 8.5 clash の勝敗種別と FP 付与（実装追補）
- 攻撃スキル同士の clash で勝敗が付いた場合、勝者へ `FP+1` を付与する。
- 防御スキル同士の clash で勝敗が付いた場合も、勝者へ `FP+1` を付与する。
- 防御スキル vs 回避スキルの組み合わせはマッチ不成立として扱い、`outcome=no_effect` とする（FP増減なし）。

## 9. 再回避差し込み（再回避状態、回避スロット or 解決済みスロットを無料再利用、回避スロットがtargetしている相手スキルの解決時のみ差し込み、第三者介入なし、one-sided→clashに昇格）
- 再回避状態のキャラクターは、回避スロットまたは解決済みスロットを無料で再利用できる。
- 差し込み可能なのは、回避スロットが target している相手スキルの解決時のみ。
- 第三者介入は不可。
- 条件成立時、`one-sided` は `clash` へ昇格し得る。

## 9.1 解決タイミングフック（2026-02 追加）
Select/Resolve では、従来タイミング（`PRE_MATCH/HIT/WIN/LOSE/UNOPPOSED/END_MATCH/END_ROUND`）に加えて以下を扱う。

- `RESOLVE_START`: 解決フェーズ開始直後（ネタバレ防止制御の起点）
- `BEFORE_POWER_ROLL`: 威力レンジ表示後、実威力ロール直前
- `AFTER_DAMAGE_APPLY`: ダメージ反映直後
- `RESOLVE_STEP_END`: 1マッチ/1一方攻撃の表示完了時
- `RESOLVE_END`: 解決フェーズ全処理完了時（まとめログ出力、ラウンド終了遷移）

## 9.2 USE_SKILL_AGAIN（再使用チェーン）
- `effects[].type = USE_SKILL_AGAIN` は「同スキルを同対象スロットへ再実行」要求として解決層で扱う。
- 再使用は仮想スロット（`<origin_slot>__EX1`, `__EX2`, ...）を `single_queue` 直後へ差し込んで処理する。
- 既定では再使用時に通常コストを再消費しない（`apply_cost_on_execute = false`）。
- `consume_cost: true` を指定した場合のみ、再使用分も通常コストを消費する。
- `reuse_cost` を指定した場合、差し込み時点で支払い可能なときのみ再使用スロットを生成する。
- 連鎖上限は `max_reuses` と実装ハード上限（20）の小さい方。
- トレース表示ラベルは元ステップ基準で `n-EX`, `n-EX2` ... を使用する。

## 10. Mass（広域）
### 10.1 mass_individual：敵全員へ個別、対象側がSをtargetしているスロットがあればclash、複数ならinitiative最大1つ、無ければone-sided
- 攻撃側スロット S は敵全員に対して個別解決を行う。
- 各対象について、その対象側が S を target にしているスロットがあれば `clash`。
- 複数該当時は initiative 最大の1スロットのみ採用。
- 該当なしは `one-sided`。
- `mass` スロット自身の通常コストは Resolve 開始時に1回だけ先払いする（`cost_consumed_at_resolve_start=true` で二重消費防止）。

### 10.2 mass_summation：攻撃側威力A、参加は“Sをtargetしているスロットのみ”、1キャラ1スロット（initiative最大）、D=合計、A vs D
- 攻撃側スロット S の威力を A とする。
- 防御参加は「S を target にしているスロットのみ」。
- 防御側は1キャラ1スロットのみ参加可能（initiative 最大を採用）。
- 防御値 D は参加スロットの合計値（`D = sum`）。
- 解決は `A vs D`。
- ダメージは `delta = |A-D|`。`attacker_win` なら敵陣営全員へ `delta`、`defender_win` なら攻撃者へ `delta`、`draw` は0。

### 10.3 mass種別の推論（後方互換）
- `mass_type` 未指定でも、スキルの `tags` / `distance` / `距離` / `target_type` などから自動推論する。
- `広域-合算` / `summation` / `sum` を含む場合は `mass_summation`。
- `広域-個別` / `individual` を含む場合は `mass_individual`。
- `広域` のみ判定できる場合は `mass_individual` を既定とする。
- 自動推論された `mass` は target を `{"type":"mass_*","slot_id":null}` に正規化する。

## 11. データモデル（battle_stateに持つべき slots/intents/phase/redirects/resolve.trace の推奨JSON例）
`battle_state` の推奨最小構造例:

```json
{
  "room_id": "room_1",
  "battle_id": "battle_1",
  "round": 12,
  "phase": "select",
  "slots": {
    "slot_a": {
      "actor_id": "char_A",
      "initiative": 9,
      "index_in_actor": 0,
      "disabled": false,
      "locked_target": false
    },
    "slot_b": {
      "actor_id": "char_B",
      "initiative": 7,
      "index_in_actor": 0,
      "disabled": false,
      "locked_target": false
    }
  },
  "timeline": ["slot_a", "slot_b"],
  "intents": {
    "slot_a": {
      "slot_id": "slot_a",
      "actor_id": "char_A",
      "skill_id": "skill_attack_01",
      "target": { "type": "single_slot", "slot_id": "slot_b" },
      "committed": true,
      "committed_at": 1730000000123,
      "committed_by": "player_a",
      "intent_rev": 4,
      "tags": {
        "instant": false,
        "mass_type": null,
        "no_redirect": false
      }
    }
  },
  "redirects": [
    {
      "from_slot": "slot_a",
      "to_slot": "slot_b",
      "winner_slot": "slot_a",
      "applied": true
    }
  ],
  "resolve_snapshot_intents": {
    "slot_a": {
      "slot_id": "slot_a",
      "actor_id": "char_A",
      "skill_id": "skill_attack_01",
      "target": { "type": "single_slot", "slot_id": "slot_b" },
      "committed": true,
      "committed_at": 1730000000123,
      "committed_by": "player_a",
      "intent_rev": 4,
      "tags": { "instant": false, "mass_type": null, "no_redirect": false }
    }
  },
  "resolve_snapshot_at": 1730000000456,
  "resolve": {
    "mass_queue": [],
    "single_queue": [],
    "resolved_slots": [],
    "step_total": 3,
    "step_estimate": { "mass": 1, "single": 2, "total": 3 },
    "trace": [
      {
        "step": 1,
        "step_index": 0,
        "step_total": 3,
        "kind": "redirect",
        "attacker_slot": "slot_a",
        "defender_slot": "slot_b",
        "target_actor_id": "char_B",
        "attacker_actor_id": "char_A",
        "defender_actor_id": "char_B",
        "rolls": {},
        "outcome": "no_effect",
        "cost": { "mp": 0, "hp": 0, "fp": 0 },
        "display_label": "1",
        "notes": null
      }
    ]
  }
}
```

## 12. イベント（固定）
以下を固定イベントとして採用する。

Client→Server:
- battle_round_request_start
- battle_intent_preview
- battle_intent_commit
- battle_intent_uncommit
- battle_intent_change_skill
- battle_intent_change_target
- battle_resolve_confirm（GM専用）
- battle_resolve_start
- battle_resolve_flow_advance_request（GM専用）

Server→Client:
- battle_round_started
- battle_state_updated
- battle_resolve_ready
- battle_phase_changed
- battle_resolve_trace_appended
- battle_resolve_flow_advance
- battle_round_finished
- battle_error

payload例（このまま貼る）:

[Client→Server]
battle_round_request_start:
{"room_id":"string","battle_id":"string","round":12}

battle_intent_preview:
{"room_id":"string","battle_id":"string","slot_id":"string","skill_id":"string|null","target":{"type":"single_slot|mass_individual|mass_summation|none","slot_id":"string|null"}}

battle_intent_commit:
{"room_id":"string","battle_id":"string","slot_id":"string","skill_id":"string","target":{"type":"single_slot|mass_individual|mass_summation","slot_id":"string|null"},"client_ts":1730000000}

battle_intent_uncommit:
{"room_id":"string","battle_id":"string","slot_id":"string"}

battle_intent_change_skill:
{"room_id":"string","battle_id":"string","slot_id":"string","skill_id":"string"}

battle_intent_change_target:
{"room_id":"string","battle_id":"string","slot_id":"string","target":{"type":"single_slot|mass_individual|mass_summation|none","slot_id":"string|null"}}

battle_resolve_confirm:
{"room_id":"string","battle_id":"string"}

battle_resolve_start:
{"room_id":"string","battle_id":"string|null"}

battle_resolve_flow_advance_request:
{"room_id":"string","battle_id":"string","round":12,"expected_step_index":3}

[Server→Client]
battle_round_started (最小):
{"room_id":"string","battle_id":"string","round":12,"phase":"select","slots":{"slot_id":{"actor_id":"...","initiative":8,"index_in_actor":0,"disabled":false,"locked_target":false}},"timeline":["slot_a","slot_b"],"tiebreak":[{"initiative":7,"group":["slot_x","slot_y"],"rolls":{"slot_x":3,"slot_y":5}}]}

battle_state_updated (全量例):
{"room_id":"string","battle_id":"string","round":12,"phase":"select|resolve_mass|resolve_single","slots":{},"intents":{"slot_id":{"skill_id":"...","target":{"type":"...","slot_id":"..."},"committed":true,"tags":{"instant":false,"mass_type":null,"no_redirect":false}}},"redirects":[],"resolve_ready":false}

battle_resolve_ready:
{"room_id":"string","battle_id":"string","round":12,"phase":"select","ready":true,"required_count":4,"committed_count":4,"waiting_slots":[]}

battle_phase_changed:
{"room_id":"string","battle_id":"string","round":12,"from":"select","to":"resolve_mass"}

battle_resolve_trace_appended:
{"room_id":"string","battle_id":"string","round":12,"phase":"resolve_mass|resolve_single","trace":[{"step":1,"step_index":0,"step_total":9,"kind":"redirect|redirect_cancelled_by_no_redirect|mass_individual|mass_summation|clash|one_sided|fizzle|evade_insert|hard_attack","attacker_slot":"slot_a","defender_slot":"slot_b|null","target_actor_id":"char_X|null","display_label":"1|1-EX|1-EX2|null","rolls":{},"outcome":"attacker_win|defender_win|draw|no_effect","cost":{"mp":0,"hp":0,"fp":0},"notes":"string|null"}]}

battle_resolve_flow_advance:
{"room_id":"string","battle_id":"string","round":12,"expected_step_index":3,"requested_by":"gm"}

battle_round_finished:
{"room_id":"string","battle_id":"string","round":12}

battle_error:
{"message":"unknown slot_id|<event> permission denied|...","slot_id":"string|null","actor_id":"string|null"}

---

## 13. 参照リンク（タイミング実行時期）
- 効果タイミングの実行時期一覧は `manuals/03_Integrated_Data_Definitions.md` の
  「付録: 効果タイミング実行時期一覧（実装準拠 / 2026-02）」を参照。
- 解決フェーズ特有の運用（`RESOLVE_START` 以降）は本書の「9.1」「付録A」を参照。

---

## 付録A: 2026-02 実装反映（解決フェーズ演出・同期・ログ）

### A-1. 解決タイミングの運用確定
- `RESOLVE_START` は解決演出開始直後に実行し、事前ネタバレとなるダメージ/状態変化ログは出力しない。
- `BEFORE_POWER_ROLL` は威力レンジ表示（`min~max`）の後、実威力ロール前に実行する。
- `AFTER_DAMAGE_APPLY` はHP反映直後に実行する。
- `RESOLVE_STEP_END` は1処理（1マッチ/1一方攻撃/1広域解決）表示完了時に実行する。
- `RESOLVE_END` は全処理表示完了後に実行し、まとめログ送信と `round_end` 遷移を行う。

### A-2. 解決フェーズ演出仕様（GM同期）
- 解決開始時に「戦闘開始」を表示する。
- 1処理の標準表示時間は4秒。
- 1処理内の表示順は `名前 -> スキル -> 威力レンジ -> 実威力 -> 結果`。
- マッチ成立時のみ双方スキルを表示する。
- 一方攻撃時は防御側スキルを表示しない。
- 一方攻撃の結果文言は「Xの一方攻撃」とし、勝利表記は使わない。
- 解決表示の進行はGM操作に全参加者を厳密同期する。
- GMは手動進行ボタンで次処理へ進める。
- GMが自動進行チェックを有効化した場合、表示完了2秒後に次処理へ進める。

### A-3. 表示件数とトレース整合
- `resolve trace` は実処理単位（マッチ/一方攻撃/広域）で1件を原則とする。
- 攻撃側/防御側起点の重複記録で同一処理を二重カウントしない。
- 表示カウンタ `#n/N` は実処理件数と一致させる。

### A-4. ダメージ表示・ログ表示
- 解決表示の威力値はダイスロール由来を表示基準とする。
- ダメージ集計は `ダイス由来` と `効果由来` を分離表示する。
- 効果由来は効果名ごとの内訳を表示する（例: `亀裂`, `破裂爆発`）。
- 内訳表示は対象名の重複列挙を避け、受けた合計値と内訳を優先する。
- チャットログも同様に合計/内訳（ダイス・効果・効果名）を分離記録する。

### A-5. 広域-合算（mass_summation）表記・UI
- `mass_summation` の表示名は「広域-合算」とする。
- `participants` は「参加人数」、`delta` は「威力差」として扱う。
- `mass_summation_delta` は「合計ダメージ」として扱う。
- 広域-合算UIでは防御側カードの主情報を「防御威力合計」とする。
- 広域-合算の差分ダメージはダイス由来ダメージとして集計する。

### A-6. 再使用（USE_SKILL_AGAIN）運用確定
- 再使用は `one_sided` / `clash` の勝者起点で同対象へ差し込み解決する。
- 追加スロットIDは `origin_slot__EXn` 形式、表示ラベルは `origin_step-EXn` 形式を使用する。
- `reuse_cost` が不足する場合、その再使用差し込みはスキップする（元処理は有効）。
- 旧 `APPLY_SKILL_DAMAGE_AGAIN` は後方互換として「再使用1回要求」に読み替える。

### A-7. Resolve開始・同期運用
- Resolve開始時に `resolve_snapshot_intents` を固定化し、Resolve中は snapshot を参照する。
- `battle_resolve_ready` は「全 required slot が commit 済み」を通知するが、開始権限は GM のみ。
- `battle_error` は unknown slot / 権限不足 / phase不一致 などの拒否理由を返す。

### A-8. 強硬追撃と表示
- 強硬追撃の trace `kind` は `hard_attack` を使用し、UI表示名は常に「強硬攻撃」とする。
- 強硬追撃時の回避差し込みは「対象指定済み回避 > 未使用回避 > 再回避候補」の順で判定する。
- 牽制勝利または回避勝利で強硬追撃が抑止された場合、通常の clash 結果のみを採用する。
- 抑止時は `trace.notes` に抑止理由（`feint_blocked` / `hard_evaded`）を記録し、チャットログにも理由を表示する。

### A-9. 防御/回避のマッチ判定と FP
- `defense` vs `evade` は `clash` を実行しても結果は `no_effect` へ正規化する。
- `FP+1` の自動付与は、`attack vs attack` または `defense vs defense` の勝敗確定時だけ発生する。
- 上記FPは `source=match_win_fp` として記録し、スキル効果で増えたFPと区別する。
