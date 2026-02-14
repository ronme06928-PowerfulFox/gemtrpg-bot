# 08 Select/Resolve 確定仕様書 v1.2

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

## 5. Select（行動可能者のみ、全スロット選択→commitでのみ進行、instantはcommit時発動でスロット消費なし、全公開矢印）
- 選択可能なのは行動可能キャラクターのみ（混乱・行動不能は除外）。
- 対象キャラクターの全スロットに対し `skill_id` と `target` を選択する。
- Resolve への進行は全対象スロットの `commit` 完了時のみ。
- `instant` タグのスキルは `commit` 時に即時発動し、スロットを消費しない（Resolve 対象外）。
- 目標指定は全公開矢印として可視化する。

## 6. redirect（自動、init(A)>init(B)でB.target=A、競合は最大initiativeが最終勝者・後から再上書き、同速不可、マッチできなくなった側はone-sided）
- A が単体で B（相手スロット）を target にして commit したとき、`initiative(A) > initiative(B)` なら `B.target = A` に自動変更する。
- 同一 B への redirect 競合は、最大 initiative を持つスロットが最終勝者となる。
- 後から到着したより高 initiative の redirect は再上書き可能。
- 同速（`initiative(A) == initiative(B)`）では redirect 不可。
- redirect の結果、相互指定を失ってマッチできなくなった側は `one-sided` として実行する（対象が盤面に残る限り）。

## 7. no_redirect（引き寄せできない/されない、locked_targetでも解除して自由にtarget再選択、過去の引き寄せは無効化され得る）
- `no_redirect` スキルを選択したスロットは、redirect できず、redirect されない。
- `locked_target` 状態でもロックを解除し、自由に target を再選択できる。
- 過去に適用済みの redirect 結果は無効化され得る。
- その結果、相互指定が崩れた引き寄せ側は `one-sided` へ移行し得る。

## 8. Resolve（処理順：Mass最優先→Singleはtimeline、clashは相互指定のみ、one-sidedの対象は“選択時の対象スロットのactor”、1スロット複数絡みはclash1組のみ、コストは実行時、対象消失＝未配置なら不発）
処理順:
- Mass を最優先で解決する。
- Mass 同士は initiative 降順、同速は追加ロール順。
- Single は timeline 順に解決する。

マッチ生成:
- `clash` は相互指定のみ成立。
- それ以外は `one-sided`。
- `one-sided` の対象は「選択時に指定した対象スロットの actor」とする。

複数絡み制約:
- 1スロットに複数の対戦候補がある場合、`clash` は1組のみ成立（優先者のみ）。
- それ以外の関連解決は `one-sided` とする。

実行時判定:
- コスト消費は実行時に行う。
- 対象消失は「理由を問わず未配置（盤面から消失）」として扱う。
- 実行時に対象が未配置なら不発（`fizzle`）とする。

## 9. 再回避差し込み（再回避状態、回避スロット or 解決済みスロットを無料再利用、回避スロットがtargetしている相手スキルの解決時のみ差し込み、第三者介入なし、one-sided→clashに昇格）
- 再回避状態のキャラクターは、回避スロットまたは解決済みスロットを無料で再利用できる。
- 差し込み可能なのは、回避スロットが target している相手スキルの解決時のみ。
- 第三者介入は不可。
- 条件成立時、`one-sided` は `clash` へ昇格し得る。

## 10. Mass（広域）
### 10.1 mass_individual：敵全員へ個別、対象側がSをtargetしているスロットがあればclash、複数ならinitiative最大1つ、無ければone-sided
- 攻撃側スロット S は敵全員に対して個別解決を行う。
- 各対象について、その対象側が S を target にしているスロットがあれば `clash`。
- 複数該当時は initiative 最大の1スロットのみ採用。
- 該当なしは `one-sided`。

### 10.2 mass_summation：攻撃側威力A、参加は“Sをtargetしているスロットのみ”、1キャラ1スロット（initiative最大）、D=合計、A vs D
- 攻撃側スロット S の威力を A とする。
- 防御参加は「S を target にしているスロットのみ」。
- 防御側は1キャラ1スロットのみ参加可能（initiative 最大を採用）。
- 防御値 D は参加スロットの合計値（`D = sum`）。
- 解決は `A vs D`。

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
      "skill_id": "skill_attack_01",
      "target": { "type": "single_slot", "slot_id": "slot_b" },
      "committed": true,
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
  "resolve": {
    "trace": [
      {
        "step": 1,
        "kind": "redirect",
        "attacker_slot": "slot_a",
        "defender_slot": "slot_b",
        "target_actor_id": "char_B",
        "rolls": {},
        "outcome": "no_effect",
        "cost": { "mp": 0, "hp": 0 },
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

Server→Client:
- battle_round_started
- battle_state_updated
- battle_phase_changed
- battle_resolve_trace_appended
- battle_round_finished

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

[Server→Client]
battle_round_started (最小):
{"room_id":"string","battle_id":"string","round":12,"phase":"select","slots":{"slot_id":{"actor_id":"...","initiative":8,"index_in_actor":0,"disabled":false,"locked_target":false}},"timeline":["slot_a","slot_b"],"tiebreak":[{"initiative":7,"group":["slot_x","slot_y"],"rolls":{"slot_x":3,"slot_y":5}}]}

battle_state_updated (全量例):
{"room_id":"string","battle_id":"string","round":12,"phase":"select|resolve_mass|resolve_single","slots":{},"intents":{"slot_id":{"skill_id":"...","target":{"type":"...","slot_id":"..."},"committed":true,"tags":{"instant":false,"mass_type":null,"no_redirect":false}}},"redirects":[]}

battle_phase_changed:
{"room_id":"string","battle_id":"string","round":12,"from":"select","to":"resolve_mass"}

battle_resolve_trace_appended:
{"room_id":"string","battle_id":"string","round":12,"phase":"resolve_mass|resolve_single","trace":[{"step":1,"kind":"redirect|redirect_cancelled_by_no_redirect|mass_individual|mass_summation|clash|one_sided|fizzle|evade_insert","attacker_slot":"slot_a","defender_slot":"slot_b|null","target_actor_id":"char_X|null","rolls":{},"outcome":"attacker_win|defender_win|draw|no_effect","cost":{"mp":0,"hp":0},"notes":"string|null"}]}

battle_round_finished:
{"room_id":"string","battle_id":"string","round":12}
