<!-- 旧: 09_SelectResolve_Spec.md を B 系列へ移管 (2026-05-09) -->
# 09 Select/Resolve 確定仕様書 v1.2

**最終更新日**: 2026-10-20
**文書バージョン**: v1.7
**対象実装**: `events/battle/common_routes.py` / `manager/battle/common_manager.py` / `manager/battle/core.py`
**版注記**: 本更新で v1.6 相当の仕様差分（`same_team/opposing_team` 記法と同陣営指定タグの固定ルール）を反映

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

PR4の記録追加仕様（2026-10-29）：

- `applied.fired_effects`: 発動順の `{term_id, name, actor_id, target_id, results: [{name, delta}]}`。名称は用語図鑑の `display_name`。HPはresultsへ入れない。対応表にない効果・名称欠損・不発は省略する。
- `applied.statuses`: MPも他の状態と同じ `{target_id, name, before, after, delta}` で記録する。
- `applied.damage` / 広域の `damage_events`: 各行へ `hp_after`（その行の適用後HP）を追加する。`hp_after === 0 && hp_after + hp > 0` が戦闘不能への移行。
- `self_destructed`: この段の記録送信直後に既存の自滅処理を実行するキャラIDの一覧。判定条件を既存処理と共有し、実際の自滅の順序は変えない。
- 広域合算の `fired_effects` は既存の `statuses` / `damage_events` と同じ階層にも置き、フロントエンドで共通形式に正規化する。
- 一方攻撃・マッチ（duel委任含む）・強硬・広域個別・合算の解決段で収録する。`RESOLVE_STEP_END` は送信後、`RESOLVE_START` と宣言時は段外のため表示用一覧へ含めない。旧広域モーダルは任意の収集リストを受け取るが、解決trace自体がない。

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
6. `加速(Bu-11)` / `減速(Bu-12)` は initiative 計算に反映する。付与後1ラウンド待機し、1ラウンド有効。ロール後には解除せず終了時に減衰する（D24）。
7. legacy互換として `state.timeline` も同スロットIDで再構築し、`hasActed=false` を初期化する。

## 5. Select（行動可能者のみ、全スロット選択→commitでのみ進行、instantはcommit時発動でスロット消費なし、全公開矢印）
- 選択可能なのは行動可能キャラクターのみ（混乱・行動不能は除外）。
- 対象キャラクターの全スロットに対し `skill_id` と `target` を選択する。
- Resolve への進行は全対象スロットの `commit` 完了時のみ。
- `instant` タグのスキルは `commit` 時に即時発動し、スロットを消費しない（Resolve 対象外）。基本は1キャラクターにつき1ラウンドに1回（2026-10-20ユーザー裁定、計画46 D20）。同ラウンドの再確定はサーバーで拒否し、コスト・効果を処理しない。次ラウンドの開始成功時に `flags.immediate_action_used` を解除し、状態を配信する。
- `宝石の加護スキル` タグを持つスキルは、即時発動かどうかに関係なく、1回の戦闘（戦闘突入から戦闘終結まで）で1キャラクター1回まで（2026-10-20ユーザー裁定、計画46 D20追補。2026-10-22に即時発動以外へ拡張）。即時発動の宝石の加護スキルには1ラウンド1回の制限もかかり、両方を満たす必要がある。
  - 印 `used_gem_protect_this_battle` は実際に使ったとき、つまりコストを処理するときに立てる。即時発動は確定時、通常の宣言は Resolve で実行してコストを処理するとき（`free_cost` でコスト0でも立てる）。宣言しても実行されなかった（不発・取消）場合は立てず、その戦闘中に再び使える（2026-10-22ユーザー決定）。戦闘突入とリセットで解除する。
  - 印が立っていれば、即時発動の確定はサーバーで拒否し、コスト・効果を処理しない。⚡の一覧からも外す。
  - 通常の宣言では `evaluate_skill_access` が使用不可とする（commit・スキル変更の拒否、宣言パネルの `usable_skill_ids`）。同じキャラクターの別スロットが同じラウンドに宝石の加護スキルを確定済みのときも使用不可とし、1ラウンドで2回実行されないようにする。
- 目標指定は全公開矢印として可視化する。
- `required slots` は「行動可能かつ未消費」のスロットのみ。行動不能者や `committed+instant` は Resolve 必須条件から除外する。

### 5.0 通常ルームの戦闘セッション境界（2026-09-08）

- 通常ルームは `combat_phase` を用い、`ready`（戦闘準備中）と `active`（戦闘中）を区別する。探索表示を切り替える既存の `mode` とは別の状態である。
- `ready` 中は、RoundStart、ラウンド終了、宣言、Resolve、通常・広域マッチの進行要求をサーバー側で拒否する。`battle_only` は従来どおりこの制限の対象外である。
- 新規作成した通常ルームは `ready` で始まる。GMの戦闘突入で `active` となり、`combat_session` を新規作成して戦闘内一時状態を初期化する。召喚体は残し、荊棘重絡0化・バフの初期状態への復元は行う（2026-10-21 D25、C1）。既存保存データにこの状態がなければ、互換性のため `active` として扱う。
- GMの戦闘終結で、結果を`VICTORY`、`DEFEAT`、`RETREAT`、`INTERRUPTED`から必須選択して `ready` に戻す。通常キャラクターのHP、MP、FP、配置は保持し、召喚体を除去し、荊棘重絡を0にする（D25）。timeline、slots、intents、resolve queue、active match、ラウンド制状態、伝授スキル、戦闘内使用フラグを消去する。
- 行動可能者と行動対象は、HPが正で逃走しておらず、`x` と `y` の両方が0以上の盤面配置済みキャラクターに限る。片方だけ盤外または座標欠損のキャラクターは、timeline、Select/Resolve slot、PvE自動行動、AI対象選択、ラウンド終了時の未行動判定に含めない。

### 5.1 Select UI補正（対象先行）
- 対象選択後、対象条件に合致するスキルのみ候補表示する（逆方向フィルタ）。
- 既に選択済みスキルが新しい対象と非整合になった場合、そのスキル選択は自動で解除する。
- 目的は「宣言可能でない組み合わせ」の commit 前検出。

### 5.2 Select時の権限・入力バリデーション（実装準拠）
- `battle_intent_preview` / `battle_intent_commit` / `battle_intent_uncommit` は、対象 `slot_id` が存在しない場合 `battle_error: unknown slot_id` を返し、状態を変更しない。
- 各 intent イベントは「そのスロットの actor を操作可能なユーザー」だけが実行できる。権限不足時は `battle_error: <event> permission denied` を返し、状態を変更しない。
- `GM` は全キャラクターのスロットを代理操作可能。
- `battle_resolve_confirm` は `GM` 専用。通常ルームの `battle_resolve_start` も `GM` 専用。
- `battle_resolve_flow_advance_request` は、後述する共有 Resolve presentation の進行役だけが実行できる。

## 6. redirect（自動、init(A)>init(B)でB.target=A、競合は条件を満たす最後の宣言が最終勝者、同速不可、マッチできなくなった側はone-sided）
- 宣言の確定・取り消しごとに全体の redirect を再計算する。A が単体で B（相手スロット）を target にする宣言によって、`initiative(A) > initiative(B)` 等の条件を満たせば `B.target = A` に自動変更する。
- 同一 B への redirect 競合は、各候補が `init(A)>init(B)` 等の引き寄せ条件を満たす場合、最後に宣言したスキルがマッチを取る。候補同士の最大 initiative では決めない（2026-10-20ユーザー裁定、計画46 D16）。
- 後の宣言がBへの引き寄せ条件を満たせば再上書き可能。先の候補Aより速い必要はない。
- 同速（`initiative(A) == initiative(B)`）では redirect 不可。
- redirect の結果、相互指定を失ってマッチできなくなった側は `one-sided` として実行する（対象が盤面に残る限り）。
- 例外: B が「広域スロット（`mass_individual` / `mass_summation`）」を単体 target 中なら、その target は redirect で横取りしない（広域対決の安定化）。
- 追加固定ルール（2026-03-28）: `target_scope=same_team`（互換: `ally`、同陣営指定/味方指定）スキルは redirect に参加しない（発生させない/受けない）。

## 7. no_redirect（引き寄せできない/されない、locked_targetでも解除して自由にtarget再選択、過去の引き寄せは無効化され得る）
- `no_redirect` スキルを選択したスロットは、redirect できず、redirect されない。
- `locked_target` 状態でもロックを解除し、自由に target を再選択できる。
- 過去に適用済みの redirect 結果は無効化され得る。
- その結果、相互指定が崩れた引き寄せ側は `one-sided` へ移行し得る。
- 追加固定ルール（2026-03-28）: `target_scope=same_team`（互換: `ally`、同陣営指定/味方指定）スキルは宣言時に `no_redirect` 相当として扱う。

## 8. Resolve（処理順：Mass最優先→Singleはtimeline、clashは相互指定のみ、one-sidedの対象は"選択時の対象スロットのactor"、1スロット複数絡みはclash1組のみ、コストは実行時、対象消失＝未配置なら不発）
処理順:
- Mass を最優先で解決する。
- Mass 同士は initiative 降順、同速は追加ロール順。
- Single は timeline 順に解決する。

マッチ生成:
- `clash` は相互指定のみ成立。
- それ以外は `one-sided`。
- `one-sided` の対象は「選択時に指定した対象スロットの actor」とする。
- 追加固定ルール（2026-03-28）: 同一陣営どうしの相互指定で、どちらかが `target_scope=same_team`（互換: `ally`）なら `clash` を作らず `one-sided` として扱う。
- 追加固定ルール（2026-02-27）: 同一陣営ペアには再回避差し込み（evade insert）を行わない。
- Select/Resolve では `同時攻撃` / `相互命中` を独立 outcome としては扱わない。相互指定は `clash` として解決し、結果は `attacker_win` / `defender_win` / `draw` のいずれかに正規化する。両者にダメージを発生させたいスキルは、勝敗 outcome ではなく `HIT` / `AFTER_DAMAGE_APPLY` / `CUSTOM_DAMAGE` などの効果で表現する。

複数絡み制約:
- 1スロットに複数の対戦候補がある場合、`clash` は1組のみ成立（優先者のみ）。
- それ以外の関連解決は `one-sided` とする。

実行時判定:
- コスト消費は「通常解決では実行時」が原則（`mass` は Resolve開始時に先払い）。コストを支払ってから使用時の効果を処理する（2026-10-20ユーザー裁定、計画46 D18）。
- 通常単体は対象・組合せによる不発判定を通過してから支払い、`PRE_MATCH`（使用時）→`BEFORE_POWER_ROLL`→威力ロールへ進む。マッチは両者の使用コストを使用時効果より前に支払う。結果反映時やマッチ委譲先で再控除しない。広域の解決開始時先払いと即時発動の確定時支払いは維持する。広域は先払い後に不発になっても、支払ったコストを返さない（2026-10-22ユーザー裁定、D06）。
- 広域の先払いも通常のステータス更新で行い、`[スキル名]: キャラ名: FP (5) -> (2)` のチャット行を残す。HPコストで0になった場合は通常どおり戦闘不能へ移行する。
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

### 8.3 非ダメージ・強硬攻撃（実装追補）
- `deals_damage=false` のスキルは `one-sided` / `clash` とも HP減算を行わない。
- `tags` に `非ダメージ` / `no_damage` / `non_damage` がある場合も `deals_damage=false` 相当として扱う。
- 上記ケースでは `on_damage` 連鎖も発火しない。
- 強硬スキルを使ってclashで敗北した場合、勝者が強硬スキルでも `hard_attack`（強硬攻撃）を1回差し込む。引き分けでは発動しない（2026-10-22ユーザー裁定D39）。
- 牽制タグ側が勝利した場合、相手の強硬攻撃は差し込まない（抑止）。
- 回避タグ側が勝利した場合も、相手の強硬攻撃は差し込まない（不発）。
- 牽制/回避により強硬攻撃が不発になった場合は、チャットログに理由を出力する。

### 8.4 one-sided の PRE_MATCH 評価（実装追補）
- `one-sided` 解決では、攻撃側の `PRE_MATCH` のみを実行する。
- 防御側スキルは条件参照用データとしては渡すが、防御側自身の `PRE_MATCH` 効果は実行しない。
- 目的: 予約スキル/補助スキルの副作用が、非対決側で重複発火することを防ぐ。

### 8.5 clash の勝敗種別と FP 付与（実装追補）
- 攻撃と防御・回避の威力が同じなら、防御・回避側の勝利。attacker / defender の処理位置によらず同じ勝敗・勝利FP・勝敗効果を適用する。回避成功は再回避状態になり、ギァン・バルフの反撃は威力差0のため発生しない。攻撃同士・防御同士の同値は引き分け（勝敗効果・勝利FPなし）を維持する（2026-10-22ユーザー裁定）。
- 攻撃スキル同士の clash で勝敗が付いた場合、勝者へ `FP+1` を付与する。
- 防御スキル同士の clash で勝敗が付いた場合も、勝者へ `FP+1` を付与する。
- 攻撃スキル vs 防御スキルでは、防御スキル側が勝利した場合に限り、勝者へ `FP+1` を付与する。
- 攻撃スキル vs 回避スキルでは、回避スキル側が勝利した場合に限り、勝者へ `FP+1` を付与する。
- 防御スキル vs 回避スキルの組み合わせは、マッチ自体を作らず `fizzle`（不発）として扱う。
- 回避スキル vs 回避スキルの組み合わせも、マッチ自体を作らず `fizzle`（不発）として扱う。
- 上記の不発では、そのスキルは「未使用」扱いとなる。コストは消費せず、`RESOLVE_START` / 使用時 / `PRE_MATCH` / `RESOLVE_END` を含むスキル効果は発動しない。
- ただし行動回数だけは消費されるため、そのスロットは解決済みになる。
- 例外として、`RESOLVE_START` の後に対象消失などで後発的に不発になった場合は、`RESOLVE_START` だけは既に発動済みとして残る。

## 9. 再回避差し込み（再回避状態、回避スロット or 解決済みスロットを無料再利用、使用者を対象とする後続攻撃へ差し込み、同陣営を除く、one-sided→clashに昇格）
- 再回避状態のキャラクターは、回避スロットまたは解決済みスロットを無料で再利用できる。
- 差し込み対象は、回避スロットの使用者を対象とする後続の攻撃（同陣営を除く）。元の回避スロットが指定した相手以外からの攻撃にも使い直せる（2026-10-22ユーザー裁定、D17）。
- 不発で未使用になった回避スロットは再利用しない。
- 条件成立時、`one-sided` は `clash` へ昇格し得る。

## 9.1 解決タイミングフック（2026-02 追加）
Select/Resolve では、従来タイミング（`PRE_MATCH/HIT/WIN/LOSE/UNOPPOSED/END_MATCH/END_ROUND`）に加えて以下を扱う。`END_MATCH` は名称を維持し、マッチ結果確定直後、`WIN` / `LOSE` とスキルダメージ判定の前に実行する共通タイミングとして扱う。

この結果タイミング標準順は `one_sided` / `clash` / `mass_individual` に適用する。`mass_summation` は複数防御側の合算結果を1つの差分ダメージとして扱うが、攻撃側スキルは1回、参加防御側スキルは参加者ごとに1回として `END_MATCH` / `WIN` / `LOSE` を評価する。

- `RESOLVE_START`: 戦闘開始時（解決フェーズ開始直後、ネタバレ防止制御の起点）
- `BEFORE_POWER_ROLL`: 威力レンジ表示後、実威力ロール直前
- `AFTER_DAMAGE_APPLY`: ダメージ反映直後。`base_damage` には実際にHPへ反映したダメージ量を渡す。
- `RESOLVE_STEP_END`: 1マッチ/1一方攻撃の表示完了時
- `RESOLVE_END`: 解決フェーズ終了時（解決フェーズ全処理完了時。まとめログ出力、ラウンド終了遷移）

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
- 複数該当時は initiative が高い順、同じならスロット番号が小さい方（slot_id 昇順）の1スロットのみ採用（2026-10-22ユーザー裁定）。
- 該当なしは `one-sided`。
- `mass` スロット自身の通常コストは Resolve 開始時に1回だけ先払いする（`cost_consumed_at_resolve_start=true` で二重消費防止）。`clash` でも二度目の支払いはしない（2026-10-20ユーザー裁定、計画46 D19）。先払い後に不発になっても返還しない（2026-10-22ユーザー裁定、D06）。

### 10.2 mass_summation：攻撃側威力A、参加は"Sをtargetしているスロットのみ"、1キャラ1スロット（initiative最大）、D=合計、A vs D
- 攻撃側スロット S の威力を A とする。
- 防御参加は「S を target にしているスロットのみ」。
- 防御側は1キャラ1スロットのみ参加可能（initiative 最大を採用）。
- 防御値 D は参加スロットの合計値（`D = sum`）。
- 解決は `A vs D`。
- 参加側も各スロットのスキル使用コストを、合算を解決するときに単体マッチと同じ支払い処理で1回払う。広域側のResolve開始時先払いは再控除しない。
- 勝利FPは、広域側勝利なら使用者にFP1、参加側勝利なら加わった全員にそれぞれFP1、引き分けなら双方0。合算はこの集団の勝敗に従い、単体マッチの防御・回避の組合せによるFP制限は適用しない（2026-10-22ユーザー裁定）。
- ダメージは `delta = |A-D|`。`attacker_win` なら攻撃側から見た相手陣営全員へ `delta`、`defender_win` なら攻撃者へ `delta`、`draw` は0。
- 結果タイミングは `END_MATCH` → `WIN` → `LOSE` → 荊棘処理 → 亀裂参照 → HP反映 → `AFTER_DAMAGE_APPLY` の順で扱う。
- `attacker_win` では攻撃側スキルの `WIN` を1回、参加防御側スキルの `LOSE` を参加者ごとに実行する。
- `defender_win` では参加防御側スキルの `WIN` を参加者ごとに、攻撃側スキルの `LOSE` を1回実行する。
- `draw` では攻撃側と参加防御側の `END_MATCH` のみを実行し、`WIN` / `LOSE` は実行しない。
- `attacker_win` 時の攻撃側 `END_MATCH` / `WIN` / `AFTER_DAMAGE_APPLY` は代表対象（実ダメージ対象の先頭）に対して実行する。参加防御側の効果は攻撃者を対象に実行する。
- 亀裂は `delta` に加算する。`END_MATCH` / `WIN` / `LOSE` で代表対象または攻撃者へ付与された亀裂は、同じ `mass_summation` の差分ダメージに反映される。

### 10.3 mass種別の推論（後方互換）
- `mass_type` 未指定でも、スキルの `tags` / `distance` / `距離` / `target_type` などから自動推論する。
- `広域-合算` / `summation` / `sum` を含む場合は `mass_summation`。
- `広域-個別` / `individual` を含む場合は `mass_individual`。
- `広域` のみ判定できる場合は `mass_individual` を既定とする。
- 自動推論された `mass` は target を `{"type":"mass_*","slot_id":null}` に正規化する。

D06の返還案（出典・不足台帳§11）は2026-10-22ユーザー裁定により不採用。先払い後に不発でも返さない。

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
- 効果タイミングの実行時期一覧は `manuals/implemented/C01_JSON_Definition_Master.md` の
  「付録: 効果タイミング実行時期一覧（実装準拠 / 2026-02）」を参照。
- 解決フェーズ特有の運用（`RESOLVE_START` 以降）は本書の「9.1」「付録A」を参照。

---

## 付録A: 2026-02 実装反映（解決フェーズ演出・同期・ログ）

### A-1. 解決タイミングの運用確定
- `RESOLVE_START` は解決演出開始直後に実行し、事前ネタバレとなるダメージ/状態変化ログは出力しない。
- `BEFORE_POWER_ROLL` は威力レンジ表示（`min~max`）の後、実威力ロール前に実行する。
- `END_MATCH` はマッチ結果確定直後に攻防双方へ実行し、その後に勝者側 `WIN`、敗者側 `LOSE` を実行する。
- 引き分けでは攻防双方の `END_MATCH` のみを実行し、`WIN` / `LOSE` は実行しない。
- `END_MATCH` / `WIN` / `LOSE` は荊棘処理およびスキルダメージ判定より前に実行する。
- `AFTER_DAMAGE_APPLY` はHP反映直後に実行し、`base_damage` には実際に反映したダメージ量を渡す。
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

### A-8. 強硬攻撃と表示
- D39（2026-10-22裁定）：マッチで敗北した強硬スキルの基礎威力を勝者へのダメージとして与える。勝者が強硬スキルでも発動し、引き分けでは発動しない。勝者は使える回避で防げる。
- 強硬攻撃の trace `kind` は `hard_attack` を使用し、UI表示名は常に「強硬攻撃」とする。
- 強硬攻撃時の回避差し込みは「対象指定済み回避 > 未使用回避 > 再回避候補」の順で判定する。
- 牽制勝利または回避勝利で強硬攻撃が抑止された場合、通常の clash 結果のみを採用する。
- 抑止時は `trace.notes` に抑止理由（`feint_blocked` / `hard_evaded`）を記録し、チャットログにも理由を表示する。

### A-9. 防御/回避のマッチ判定と FP
- `defense` vs `evade` は `clash` を実行せず、`fizzle`（不発）として処理する。
- `evade` vs `evade` も `clash` を実行せず、`fizzle`（不発）として処理する。
- 上記不発のスロットは `cancelled_without_use` 扱いになり、後続の再回避差し込み候補にもならない。
- `FP+1` の自動付与は、`attack vs attack` / `defense vs defense` の勝敗確定時に発生する。
- `attack vs defense` では `defense` 側が勝利した場合に限り、`FP+1` を付与する。
- `attack vs evade` では `evade` 側が勝利した場合に限り、`FP+1` を付与する。
- 上記FPは `source=match_win_fp` として記録し、スキル効果で増えたFPと区別する。

## 付録B: 2026-03 UI表示仕様追補

本追補は、Manual14 の UI 改善実装を Select/Resolve の恒常仕様として固定するためのものである。

### B.1 スロット表示

- Select/Resolve 中のスロット番号バッジは、トークン本体の上側に退避表示する。
- スロット番号は状態異常アイコン帯と重ならない位置を優先し、トークン右上アイコンより上に置く。
- スロット番号は矢印の始点・終点に隠れてはならない。

### B.2 矢印表示

- Select 中の矢印は「宣言先の可視化」が目的であり、数字の可読性を阻害しないことを優先する。
- 矢印のアンカーはスロット数字の中心ではなく、数字を避けた近傍位置へ置く。
- 矢印はスロットから不自然に離れすぎない範囲で、数字と重ならない位置に調整する。

### B.3 タイムラインUI

- Visual Battle 画面では `timeline` の画面表示を必須としない。
- 内部の `timeline` データは RoundStart の整列・Resolve 順序決定に継続利用する。
- したがって、UI 上でタイムラインを非表示にしても、進行ロジックは変更しない。

### B.4 Resolve 表示

- Resolve 画面は、スクロール前提になりすぎないよう情報を圧縮して表示する。
- 勝敗、総ダメージ、内訳は下部サマリとしてまとめて表示する。
- attacker / defender の立ち絵表示を許可し、`mass_summation` では参加者の簡易表示を行ってよい。
- `tiebreak` 情報は常時一覧ではなく、現在表示中の Resolve 対象に限って補助表示する。

### B.5 フローティングテキスト

- `select / resolve_mass / resolve_single / round_end` 中は、フローティングテキストを必須表示としない。
- 戦闘開始時に一斉表示されて読解を阻害する場合は、戦闘フェーズ中のみ抑止してよい。
- 代わりに ResolvePanel とログで結果が追えることを優先する。
- 本実装では、戦闘フェーズ中のマップ上フローティングテキストは抑止を標準とする。
- 戦闘中の追加演出が必要な場合は、ResolvePanel 内で段階同期して表示する。

### B.6 宣言パネルの右列オーバーレイ固定

- Select のスキル選択パネル（`#select-resolve-declare-panel`）は、右列サイドバー上へのオーバーレイ表示を標準とする。
- 描画先は `#declare-panel-sidebar-host` を優先し、欠落時のみ `#visual-chat-area -> #map-viewport -> #visual-battle-container` へフォールバックする。
- 右列表示時は `.declare-panel--sidebar` を適用し、表示高さは右列上端（R開始/R終了ボタン帯）から下端までを使用する。
- 表示幅は従来より拡張し、実装上の目安は `clamp(520px, calc(100% * 1.5), 760px)` とする。
- 本追補は表示領域のUX改善であり、`battle_intent_preview` / `battle_intent_commit` を含む Select/Resolve のイベント仕様には変更を加えない。

---

## 2026-07 追補: redirect（§6・§7）の実装構成（events/battle/redirect_flow.py 分割）

計画書34（2026-07-08 実装完了・削除済み）により、`events/battle/common_routes.py` にあった
redirect（§6）・no_redirect（§7）の実体ロジックを `events/battle/redirect_flow.py` へ分割した。
**ルール・挙動・resolve trace のログ形式は分割前と同一**（全既存テスト無修正で通過）。

### 構成

- `events/battle/redirect_flow.py`: `clear_redirect_state` / `append_redirect_record` /
  `cancel_redirect_by_no_redirect` / `try_apply_redirect` / `recalculate_redirect_state` の実体。
  `events/battle/phase_flow.py` 等と同じ「サブモジュールは common_routes を import しない・
  依存は関数注入で受け取る」方針を踏襲する。
- `common_routes.py` 側は `_cancel_redirect_by_no_redirect` / `_try_apply_redirect` /
  `_recalculate_redirect_state` の3関数を**シグネチャそのまま**の薄いラッパーとして残す
  （`ensure_intent_for_slot_fn` / `infer_target_scope_fn` / `server_ts_fn` を注入して
  `redirect_flow` へ委譲するだけ）。`clear_redirect_state` / `append_redirect_record` は
  redirect_flow.py 内でのみ使う内部関数のため、common_routes.py 側のラッパーは置かない。

### ラッパーを残した理由（テスト契約）

- `tests/test_select_resolve_smoke.py` が `common_routes._try_apply_redirect(...)` /
  `_recalculate_redirect_state(...)` / `_cancel_redirect_by_no_redirect(...)` を
  **直接呼び出す**ため、3関数は common_routes 側に元のシグネチャのまま存在する必要がある。
- `tests/test_intent_authorization_routes.py`（importlib 隔離ロード）が
  `_recalculate_redirect_state` を monkeypatch するため、当該名は common_routes の
  モジュール属性として残す必要がある（ラッパー自体を丸ごと差し替えられれば足りるため、
  ラッパーの中身が redirect_flow への委譲であることは monkeypatch と無矛盾）。

---

## 2026-07 追補: 非行動・対象可能な戦闘オブジェクト

特殊パッシブ等から`action_slot_mode:none`が有効になった配置済み・生存中キャラクターは、通常行動スロットを生成しない。代わりに`battle_state.slots`へ`target_only:true`の対象専用アンカーを1件生成する。

- 対象専用アンカーは単体スキルの`target.slot_id`として選択できる。
- `timeline`、宣言待ち、Resolveキュー、コスト消費、PvE行動元、redirect行動元へは含めない。
- 対象専用アンカーへの攻撃は、防御intentを持たない一方攻撃として解決する。
- 死亡、未配置、離脱後は次回のスロット再構築で除去する。
- 召喚ラウンドの行動ロック中でも、非行動オブジェクトの対象専用アンカーは生成する。

内部的には対象参照用スロットを持つが、ルール表示上は「行動せず、スロットを持たない」と扱う。

実装: `manager/battle/action_slot_mode.py`、`manager/battle/select_resolve_state.py`。

### 非行動アンカーの共通表現（2026-08-16追補）

恒久非行動オブジェクトと行動チャート上の待機は、`target_only:true`、`source_disabled:true`、`status:inactive`、`initiative:null`を持つ非行動アンカーで表す。`inactive_reason`は`non_action_object`または`behavior_no_action`とする。宣言元、宣言待ち、Resolveキュー、タイムラインには含めず、攻撃対象には指定できる。

混乱・行動不能は通常スロット自体を消さず、配信ペイロード上で`source_disabled:true`と理由を付与する。Select中は該当スロットの既存intentを解除し、preview/commitをサーバーでも拒否する。Resolve中に混乱した場合は、すでに解決済みの行動へ遡及せず、未解決スロットだけを`attacker_confusion`としてスキップする。通常キャラクターが本当に使用可能スキルを持たない場合の`SYS-STRUGGLE`は従来どおり維持する。

実装: `events/battle/pve_intents.py`、`events/battle/common_routes.py`、`manager/battle/resolve_auto_mass_phase.py`、`manager/battle/resolve_auto_single_phase.py`。

## 2026-08 追補: Resolve履歴snapshotと共有presentation

Resolveの計算結果と演出位置は分離して管理する。計算結果の正本は`battle_state.resolve.trace`、卓全体の現在表示位置の正本は`battle_state.resolve.presentation`である。再入室・再読込は保存済み結果を復元するだけで、戦闘計算を再実行しない。

`battle_state_updated`は`trace_is_snapshot:true`と当該ラウンドの全`trace`を返す。クライアントは`step_index`で重複排除し、`presentation.current_step_index`より前の演出を自動再生せず現在位置へ合流する。完了ラウンドのtraceは次ラウンド開始まで保持し、過去結果は戦闘ログからも確認できる。

Select中の引き寄せ履歴は`battle_state.redirects`にのみ記録し、Resolve結果の`trace`へ混入させない。presentationの`step_total`とカーソルは、`redirect`、`redirect_cancelled_by_no_redirect`、`evade_insert`、スキルを持たない`no_intent`不発などの内部行を除く表示対象traceだけを数える。`current_step_index`は配列位置ではなく表示対象traceのraw `step_index`であり、内部行を挟む場合は次の表示対象indexへ進む。

`presentation`は次を保持する。

- `round`、`status`（`idle|playing|completed`）
- `current_step_index`、`step_total`、単調増加する`revision`
- `controller_user_id`、`controller_username`、`controller_present`
- 現在ステップのサーバー時刻`step_started_at`

`battle_resolve_flow_advance_request`は`room_id`、`battle_id`、`round`、`expected_step_index`、`expected_revision`を必要とする。在室中の進行役から届き、すべてが現在値と一致した要求だけを一度受理する。遅延・重複・非進行役の要求は状態を変更せず、要求元へ最新presentationを返す。受理時はroom全体へpresentationと`battle_resolve_flow_advance`を配信するため、通常ルームを含め全員の表示位置は同じになる。

宣言操作権と演出進行権は別権限である。通常ルームはResolveを開始したGM、戦闘専用ルームは原則として戦闘開始者が進行役となる。通常ルームの別GMは`battle_resolve_flow_claim_request`で明示的に引き継げる。一般参加者による引継ぎは、戦闘専用ルームで現在の進行役がSocket在室していない場合だけ許可する。

最後のステップを進めるとサーバーが`completed`を確定し、ラウンド終了処理を一度だけ実行する。クライアントのローカル再生完了をラウンド終了の根拠にしない。traceが0件の場合はResolve計算直後に同じ完了処理へ進む。

実装: `manager/battle/resolve_presentation.py`、`events/battle/resolve_presentation_routes.py`、`events/battle/phase_flow.py`、`static/js/battle/components/ResolveFlowPanel.js`。
