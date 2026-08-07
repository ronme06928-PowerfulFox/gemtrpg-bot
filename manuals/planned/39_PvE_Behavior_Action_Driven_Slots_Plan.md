# 39 PvE行動チャート駆動スロット生成計画

**作成日**: 2026-07-28  
**状態**: コード・UI・自動テスト実装済み、正式シナリオデータでの手動確認待ち
**ユースケース**: シナリオNo.2『瓦礫で鋳るは魔の鋼』のボススキル「鉄塊を捥ぎり喰う」  
**関連計画**: [38_Scenario_No2_Task_Hub.md](38_Scenario_No2_Task_Hub.md) / [40_Summon_Battle_Object_And_Scenario_Skill_Effects_Plan.md](40_Summon_Battle_Object_And_Scenario_Skill_Effects_Plan.md)

---

## 1. 目的

PvE敵のBehavior Profileで、そのラウンドのstepに設定したスキル行ごとに行動スロットを1個生成する。

これにより、キャラクターの`行動回数`とチャート上のスキル数を別々に合わせる必要をなくす。通常ラウンドにスキルを1件、特殊ラウンドに通常技と特殊技を2件設定すれば、それぞれ1スロット、2スロットが生成される。

## 2. 現状と問題

- RoundStartはキャラクターの`行動回数`ぶんだけスロットを先に生成する。
- PvE intent生成は、生成済みのスロット数にBehavior Profileの`actions`を合わせる。
- `actions`がスロットより多い場合は、設定行からスロット数ぶんをランダム抽出する。
- `actions`がスロットより少ない場合は、余ったスロットを行動なしにする。

このため、GMはチャートのスキル数だけでなく、敵キャラクター側の`行動回数`も同期して管理する必要がある。ラウンドごとに行動数を変えることもできない。

## 3. 決定仕様

Behavior Profileへ`slot_generation_mode`を追加する。

- `step_actions`: 有効stepの各`actions`要素が1スロットを生成する。チャート駆動の新方式。
- `character_action_count`: キャラクターの`行動回数`でスロットを作り、`actions`を割り当てる従来方式。
- フィールド欠損時は`character_action_count`として扱い、既存保存データの挙動を変えない。
- 新規Behavior ProfileをUIから作成するときは、`slot_generation_mode: step_actions`を明示的に保存する。
- バックエンドは新旧データをフィールド欠損だけで判別せず、欠損時は常に`character_action_count`へ正規化する。

`step_actions`では、有効stepの正規化済み`actions`件数がそのラウンドのスロット数になる。キャラクターの`行動回数`は参照しない。

`slot_generation_mode`は各stepではなくBehavior Profile全体へ設定する。同じBehavior Profileの中で、stepごとに生成方式を混在させない。

## 4. データ例

```json
{
  "enabled": true,
  "slot_generation_mode": "step_actions",
  "initial_loop_id": "main",
  "loops": {
    "main": {
      "repeat": true,
      "steps": [
        {
          "actions": ["BOSS_NORMAL"],
          "targets": ["target_enemy_random"],
          "on_no_target": ["cancel"]
        },
        {
          "actions": ["BOSS_NORMAL"],
          "targets": ["target_enemy_random"],
          "on_no_target": ["cancel"]
        },
        {
          "actions": ["BOSS_NORMAL", "BOSS_ABSORB_RUBBLE"],
          "targets": [
            "target_enemy_random",
            [
              {
                "team": "same_team",
                "required_tag_ids": ["瓦礫"],
                "selection": "random"
              }
            ]
          ],
          "on_no_target": ["cancel", "cancel"]
        }
      ],
      "transitions": []
    }
  }
}
```

- `actions[i]`、`targets[i]`、`on_no_target[i]`は同じスロットへ対応する。
- `targets[i]`欠損時は既存の対象方針既定値を使う。
- `on_no_target[i]`の初期正式値は`cancel`とする。
- 空文字の`actions`要素はスロット数へ含めない。
- 未知または使用不能なスキルIDは、該当スロットをキャンセルして警告ログを残す。別スキルへ暗黙フォールバックしない。
- `actions: []`のstepは、その敵が意図的に行動しないラウンドとして0スロットを生成する。

## 5. RoundStartとintent生成

`step_actions`の敵では、次の順序で処理する。

1. RoundStart中にBehavior Runtimeと遷移条件を評価し、そのラウンドのstepを一度だけ決定する。
2. 正規化した行動計画を`battle_state`へラウンドスナップショットとして保存する。
3. 行動計画1件につき、通常のスロット生成処理を使って1スロットを生成する。
4. 各スロットへ同じ添字のスキルと対象候補を1対1で割り当てる。ランダム抽出、切り捨て、穴埋めを行わない。
5. 対象候補が空で`on_no_target=cancel`の場合は、そのスロットだけをキャンセル済みとして確定する。コスト、使用回数、スキル効果、死亡時連動は発生させない。
6. Behavior Runtimeのstep進行は、生成スロット数にかかわらず1ラウンドに1回だけ行う。

RoundStart、PvE intent再生成、再接続が同じラウンドに繰り返されても、保存したスナップショットを再利用し、スロットとstepを重複生成・重複進行させない。

### 5.1 動的に出現する対象の選択

Behavior Profileには対象キャラクターIDを固定保存せず、`team`、`required_tag_ids`、`selection`からなる対象候補条件を保存する。

対象候補はRoundStartで、その時点の`state.characters`と生成済みスロットを使って評価する。生存中かつ戦場に配置され、スキルの`target_scope`と候補条件を満たすキャラクターだけを対象候補とする。

`action_slot_mode: none`のキャラクターは行動スロットを生成しないが、対象可能であれば既存の`target_only`スロットを生成し、対象候補へ含める。これにより、行動しない瓦礫や装置も行動チャートから対象にできる。

遅延召喚は次の順序で処理する。

1. RoundStartの遅延効果を実行し、対象キャラクターを戦場へ追加する。
2. 通常スロットと`target_only`スロットを生成する。
3. Behavior Profileの対象候補条件を評価し、対象を確定する。

したがって、前ラウンドのスキルによって「次ラウンド開始時」に召喚されるキャラクターは、そのラウンドの対象候補へ含まれる。同じラウンドのSelect完了後またはResolve途中に出現したキャラクターは、生成済みの行動計画へ遡って追加せず、原則として次ラウンドから対象候補へ含める。

対象確定後、解決前に対象が死亡、撤退、消滅、対象外状態になった場合は、別の候補へ自動的に再選択しない。宣言時に表示された対象と割り込み・マッチ関係を維持し、そのスロットを対象不在として不発にする。

`on_no_target`は、チャート作成時に対象IDが登録されていないことではなく、RoundStartの候補評価結果が0件だった場合の処理を表す。

### 5.2 ラウンド行動計画と対象不在キャンセルの状態契約

確定したラウンド行動計画は、`battle_state.behavior_round_plan`へ次の形式で保存する。

```json
{
  "round": 3,
  "actors": {
    "enemy_iron_root": {
      "slot_generation_mode": "step_actions",
      "loop_id": "main",
      "step_index": 2,
      "plans": [
        {
          "skill_id": "BOSS_NORMAL",
          "target_candidates": [],
          "on_no_target": "cancel"
        },
        {
          "skill_id": "BOSS_ABSORB_RUBBLE",
          "target_candidates": [
            {
              "team": "same_team",
              "required_tag_ids": ["瓦礫"],
              "selection": "random"
            }
          ],
          "on_no_target": "cancel"
        }
      ]
    }
  }
}
```

- `round`が現在ラウンドと一致する間は同じスナップショットを再利用する。
- 同じRoundStartの再実行、再接続、PvE intent再生成では、stepを再評価・再進行しない。
- 次ラウンド開始時に新しいスナップショットへ置き換える。
- `plans`は空文字のスキルを除去した後の順序を保持し、生成スロットと1対1で対応する。
- `character_action_count`では従来処理を維持し、このスナップショットをスロット数の決定には使わない。

対象候補が0件で`on_no_target: cancel`となった行動は、監査・画面表示用のintentを次の状態で残す。

- `skill_id`は予定していたスキルIDを保持する。
- `target.slot_id`は`null`とする。
- `committed: true`としてSelectの完了を妨げない。
- `cancelled: true`、`cancel_reason: "no_target"`を設定する。
- 対応スロットは`disabled: true`、`status: "cancelled"`、`cancelled_without_use: true`とする。
- ラウンド開始時の`resolve.cancelled_slots`を空に初期化してから、対象不在スロットを登録する。
- 対象不在をラウンド開始ログと行動予告へ表示し、Resolveでは実行キューへ入れない。

この状態ではコスト、使用回数、`RESOLVE_START`、使用時、`PRE_MATCH`、`HIT`、`RESOLVE_END`、死亡時連動を一切発生させない。

## 6. 適用範囲と互換性

- `step_actions`を使うのは、Behavior Profileが有効で、有効loopとstepを解決できたPvE敵だけとする。
- プレイヤー、PvP、Behavior Profile無効の敵、チャートが破損して解決不能な敵は、従来どおり`行動回数`からスロットを生成する。
- 既存Behavior Profileはフィールド欠損により従来方式を維持する。
- UIで既存チャートを開いただけでは方式を変更しない。
- 既存チャートは、GMが明示的に新方式へ切り替えた場合だけ`slot_generation_mode: step_actions`を保存する。
- Behavior Profile自体が存在しない、または空オブジェクトだけの状態からUIで新規作成したチャートは、保存時に`slot_generation_mode: step_actions`を明示する。
- 方式は敵キャラクターごとのBehavior Profile単位で選択し、同じ戦闘内で従来方式の敵と新方式の敵を併用できる。
- 新方式では行動数が遭遇難度へ直結するため、各stepに表示する「このラウンドの行動数」を`actions`件数から明示する。

## 7. 行動チャート編集画面のUI仕様

### 7.1 Profile全体設定

行動チャート編集画面の上部で、既存の「有効化」「初期ループ」と同じProfile全体設定として「スロット生成方式」を表示する。

選択欄は、違いを読んでから選べるよう、説明付きラジオボタンとする。

- **チャートのスキル数から生成（推奨）**
  - 保存値は`step_actions`。
  - 「各ラウンドに設定したスキル1件につき1スロット生成し、キャラクターの『行動回数』は使用しない」と表示する。
- **キャラクターの行動回数から生成（互換）**
  - 保存値は`character_action_count`。
  - 「行動回数ぶんスロットを生成し、チャートのスキルを割り当てる従来方式」と表示する。

Behavior Profileが存在しない、または空オブジェクトだけの場合は新規チャートと判定し、`step_actions`を初期選択する。既存Profileに`slot_generation_mode`がない場合は`character_action_count`を選択表示し、画面を開いただけではdirty状態にしない。

方式変更はラジオボタンを選んだ時点では保存せず、画面下部の「保存」で確定する。戦闘中に変更した場合は、現在ラウンドのスナップショットを変更せず、次のRoundStartから反映する旨を設定欄へ表示する。

狭い画面では、2つの選択肢を上下に並べる。ラベル全体をクリック可能にし、キーボード操作と選択状態の読み上げに対応する。

### 7.2 stepごとの行動数表示

`step_actions`選択中は、各「ラウンド設定」の見出しへ`行動数: N`を表示する。`N`は空文字・未指定を除く`actions`件数から常時計算し、スキル行の追加・削除・変更と同時に更新する。

- スキル1件は1スロットとして数える。
- 空のスキル行は行動数へ含めない。
- 行動数0は有効な設定とし、「このラウンドは行動しません」と注意表示する。保存エラーにはしない。
- フローチャート表示の各ノードにも、各stepの行動数を表示する。

`character_action_count`選択中は、`行動数`と誤認させず、`登録スキル: N件`と表示する。あわせて「実際の行動数はキャラクターの『行動回数』で決まる」と表示する。

### 7.3 対象不在時の表示

初期実装で正式対応する`on_no_target`は`cancel`だけとする。選択肢が1つしかないためプルダウンは追加せず、各スキル行へ「対象不在時: この行動をキャンセル」と固定表示する。

保存時は、空のスキルを除去した後の`actions`と同じ件数・順序になるよう、`on_no_target: ["cancel", ...]`を自動生成する。既存の`targets`も同じ添字関係を維持する。

仕様ガイドへ次を追記する。

- 対象はキャラクターIDの固定指定ではなく、RoundStart時点の戦場から陣営・必須タグ・選択方法で検索される。
- 次ラウンド開始時の遅延召喚は、そのラウンドの候補へ含まれる。
- 対象確定後に対象が消滅しても、別対象へ自動変更しない。
- 対象候補がなければ、そのスキル行だけがキャンセルされる。

現行ガイドの「スロット数より多い場合はランダム抽選、少ない場合は最後のスキルを繰り返す」は従来方式だけの説明とし、選択中の方式に応じて説明を切り替える。

### 7.4 共通エディターと各導線

通常モードと戦闘専用モードは、`static/js/modals/behavior_flow_editor_modal.js`の共通エディターへ同じUIを実装する。

次の新規Profile生成・保存導線でも、`slot_generation_mode`と`on_no_target`を欠落させない。

- 通常キャラクターの行動チャート編集
- 戦闘専用モードの敵カタログ
- 敵編成
- 戦闘準備画面
- プリセットの保存・読込・搬出入

JSONテキストエリアから既存チャートを直接入力した場合も、サーバー側正規化と同じ欠損時互換規則を適用する。

## 8. シナリオNo.2への適用

- 鉄交じりの瓦礫を非行動かつ対象可能なキャラクターとして扱う基盤と、瓦礫を生成・破壊するスキル効果は計画40で実装する。
- 1R・2R相当のstepは通常技1件を設定し、1スロットを生成する。
- 3R相当のstepは通常技と「鉄塊を捥ぎり喰う」の2件を設定し、2スロットを生成する。
- 3stepのループにより、3R・6R・9R……だけ吸収スロットが通常行動へ追加される。
- 有効な瓦礫がなければ吸収スロットだけをキャンセルし、同じstepの通常技は予定どおり使用する。
- PCは吸収スロットへ通常どおり割り込み、マッチできる。

## 9. 実装候補

- `manager/battle/enemy_behavior.py`: モード正規化、ラウンド行動計画の確定
- `manager/battle/select_resolve_state.py`: step行動数によるRoundStartスロット生成
- `manager/battle/pve_intent_planner.py`: スナップショット済み行動計画の1対1割り当て、対象不在キャンセル
- `events/battle/pve_intents.py`: commit待ち判定とSocket通知
- `static/js/modals/behavior_flow_editor_modal.js`: §7のProfile全体設定、step行動数、対象不在表示、方式別ガイドを共通エディターへ追加する
- `static/js/modals/battle_only_catalog_modal.js`、`battle_only_enemy_formation_modal.js`、`battle_only_draft_modal.js`: 新規Profile初期値とJSON入出力を共通契約へ合わせる
- `static/js/battle/components/DeclarePanel.js`、`ResolveFlowPanel.js`: キャンセル表示
- `manuals/implemented/D01_Play_Mode_Specs.md`、`E02_UI_Component_Specs.md`: 実装完了後の正本

通常方式とチャート駆動方式でスロットの必須フィールド、initiative計算、同速処理が分岐しないよう、既存スロット生成を共通ヘルパー化する。

### 9.1 実装順序

1. `requirements-dev.txt`を導入したテスト可能なPython環境を用意し、既存のBehavior Profile、非行動対象、遅延召喚テストを基準として実行する。
2. `enemy_behavior.py`へ`slot_generation_mode`、`on_no_target`、ラウンド行動計画の正規化を追加し、欠損時互換テストを先に作る。
3. RoundStartで遅延効果実行後にBehavior Profileを1回だけ評価し、`behavior_round_plan`を保存する。
4. 共通スロット生成ヘルパーを作り、`step_actions`と従来方式の双方から利用する。0スロット、複数スロット、同速処理を検証する。
5. 保存済み行動計画からintentと対象を1対1で確定し、対象不在キャンセル、未知スキル、使用不能スキルを処理する。
6. Select完了判定、Resolveキュー、再接続、ラウンド再実行でスナップショットとキャンセル状態が重複しないことを検証する。
7. 共通行動チャートエディターと戦闘専用モード各導線へ§7のUIを実装する。
8. Timeline、Declare、Resolve表示、ログ、方式別ガイドを整合させ、実際の画面で確認する。
9. 関連テスト、全体テスト、`npm run build`、文字コード検査を通し、実装済み仕様を既存正本へ統合する。

## 10. テスト

- [x] `slot_generation_mode`欠損の既存Behavior Profileが従来どおり`行動回数`を使う。
- [ ] Profileが存在しない、または空オブジェクトだけの新規チャートは、UI保存時に`step_actions`を明示する。
- [x] `step_actions`では`actions`1件から1スロット、2件から2スロットを生成する。
- [x] `actions`数がキャラクターの`行動回数`より多くても切り捨てやランダム抽出をしない。
- [x] `actions`数がキャラクターの`行動回数`より少なくても余分なスロットを生成しない。
- [x] `actions: []`のstepで0スロットとなり、Select完了判定が停止しない。
- [x] 未知・使用不能スキルのスロットはキャンセルされ、別スキルへ置換されない。
- [x] 対象候補が空なら該当スロットだけがキャンセルされ、同じ敵の他スロットは維持される。
- [ ] RoundStartの遅延効果で召喚された、条件に一致する`target_only`キャラクターを同ラウンドの対象に選べる。
- [ ] Select完了後またはResolve途中に召喚されたキャラクターを、そのラウンドの生成済みintentへ遡って追加しない。
- [ ] 対象確定後に対象が死亡または消滅しても別の対象へ自動再選択せず、該当スロットだけが不発になる。
- [ ] PCが有効な敵スロットへ通常どおり割り込み・マッチできる。
- [x] RoundStart再実行、intent再生成、再接続でもスロットとstepが重複しない。
- [x] Behavior Runtimeのstepが生成スロット数に関係なく1ラウンドに1回だけ進む。
- [ ] プリセットJSONの搬出入と保存・復元で`slot_generation_mode`と`on_no_target`が維持される。
- [ ] 既存チャートを開いただけではdirty状態にならず、欠損モードは互換方式として表示される。
- [ ] UIで現在のスロット生成方式を確認・変更でき、保存後のJSONへ反映される。
- [ ] `step_actions`では空のスキルを除いた行動数が各stepとフローチャートへ表示され、0件では非行動の注意が出る。
- [ ] `character_action_count`では登録スキル件数と、実際の行動数がキャラクター依存である旨が表示される。
- [ ] 各スキル行に対象不在キャンセルが固定表示され、保存時に`actions`と同じ順序・件数の`on_no_target`が生成される。
- [ ] 通常モード、敵カタログ、敵編成、戦闘準備、プリセット搬出入の各導線で新フィールドが維持される。

## 11. 受け入れ条件

- 新方式の敵は、チャートの当該stepへ設定したスキル数と同数のスロットを生成する。
- GMはキャラクターの`行動回数`とチャートのスキル数を同期管理する必要がない。
- 行動チャート編集画面で、Profile全体のスロット生成方式を確認・変更できる。
- 新方式では各stepとフローチャートに表示された行動数が、実際に生成されるスロット数と一致する。
- 対象不在時の処理が各スキル行に表示され、キャンセル済み行動がSelect進行、コスト、使用回数、スキル効果へ影響しない。
- シナリオNo.2では3R・6R・9Rに通常技と吸収技の2スロット、それ以外は通常技の1スロットを生成する。
- 瓦礫がなければPCへフォールバックせず、吸収スロットだけをキャンセルする。
- 次ラウンド開始時に召喚された瓦礫は対象候補となり、対象確定後に破壊された瓦礫は別の瓦礫へ自動変更されない。
- 既存チャート、非チャート敵、プレイヤー、PvPの行動数は変更されない。
- 実装後、汎用仕様とUI仕様を`manuals/implemented/`の既存正本へ統合し、本書を削除する。

## 12. 実装・自動確認記録（2026-07-31）

- バックエンドのProfile正規化、ラウンドスナップショット、step数によるスロット生成、対象不在・使用不能キャンセルを実装した。
- 共通行動チャートエディターへ方式選択、step行動数、0行動注意、対象不在時表示を追加し、戦闘専用モードの新規Profile初期値も更新した。
- キャンセル済みスロットをタイムラインへ表示し、Resolveキューから除外される既存契約を確認した。
- `tests/test_enemy_behavior_profile.py`と`tests/test_pve_auto_intents.py`の42件は全件成功した。
- 全体テストは799件成功・2件スキップ。`tests/test_summon_loader.py`の既存ログ捕捉1件だけが、一時テスト環境のロガー出力先差異により失敗した（警告本文と安全値へのフォールバック自体は確認済み）。
- `npm run build`、Python/JavaScript構文検査、文字コード検査は実施済み。残る未チェック項目は実画面・実戦闘での手動確認を中心とする。

## 13. 残作業

新しい基盤実装は残っていない。計画38で正式キャラクターと行動チャートを作成した後、次を実機確認する。

1. 通常ラウンドは1スロット、吸収ラウンドは通常技と`E-32`の2スロットになる。
2. 瓦礫不在時は`E-32`のスロットだけがキャンセルされ、通常スロットは維持される。
3. PCが追加スロットへ割り込み・マッチできる。
4. 対象確定後に瓦礫が破壊された場合、別の瓦礫へ自動再選択しない。
5. 保存・搬出入・再読込後も`slot_generation_mode`と`on_no_target`が維持される。
6. 実機確認完了後、実装済み仕様との重複を整理して本計画を削除する。
