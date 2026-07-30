# 39 PvE行動チャート駆動スロット生成計画

**作成日**: 2026-07-28  
**状態**: 未実装  
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
          "targets": ["target_enemy_random"]
        },
        {
          "actions": ["BOSS_NORMAL"],
          "targets": ["target_enemy_random"]
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

## 6. 適用範囲と互換性

- `step_actions`を使うのは、Behavior Profileが有効で、有効loopとstepを解決できたPvE敵だけとする。
- プレイヤー、PvP、Behavior Profile無効の敵、チャートが破損して解決不能な敵は、従来どおり`行動回数`からスロットを生成する。
- 既存Behavior Profileはフィールド欠損により従来方式を維持する。
- UIで既存チャートを開いただけでは方式を変更しない。
- GMが明示的に新方式へ切り替えた場合だけ`slot_generation_mode: step_actions`を保存する。
- 方式は敵キャラクターごとのBehavior Profile単位で選択し、同じ戦闘内で従来方式の敵と新方式の敵を併用できる。
- 新方式では行動数が遭遇難度へ直結するため、各stepに表示する「このラウンドの行動数」を`actions`件数から明示する。

## 7. シナリオNo.2への適用

- 鉄交じりの瓦礫を非行動かつ対象可能なキャラクターとして扱う基盤と、瓦礫を生成・破壊するスキル効果は計画40で実装する。
- 1R・2R相当のstepは通常技1件を設定し、1スロットを生成する。
- 3R相当のstepは通常技と「鉄塊を捥ぎり喰う」の2件を設定し、2スロットを生成する。
- 3stepのループにより、3R・6R・9R……だけ吸収スロットが通常行動へ追加される。
- 有効な瓦礫がなければ吸収スロットだけをキャンセルし、同じstepの通常技は予定どおり使用する。
- PCは吸収スロットへ通常どおり割り込み、マッチできる。

## 8. 実装候補

- `manager/battle/enemy_behavior.py`: モード正規化、ラウンド行動計画の確定
- `manager/battle/select_resolve_state.py`: step行動数によるRoundStartスロット生成
- `manager/battle/pve_intent_planner.py`: スナップショット済み行動計画の1対1割り当て、対象不在キャンセル
- `events/battle/pve_intents.py`: commit待ち判定とSocket通知
- `static/js/modals/behavior_flow_editor_modal.js`: エディター上部にProfile全体のスロット生成方式を選ぶ欄を追加し、各stepの行動数表示と対象不在設定も追加する
- `static/js/battle/components/DeclarePanel.js`、`ResolveFlowPanel.js`: キャンセル表示
- `manuals/implemented/D01_Play_Mode_Specs.md`、`E02_UI_Component_Specs.md`: 実装完了後の正本

通常方式とチャート駆動方式でスロットの必須フィールド、initiative計算、同速処理が分岐しないよう、既存スロット生成を共通ヘルパー化する。

## 9. テスト

- [ ] `slot_generation_mode`欠損の既存Behavior Profileが従来どおり`行動回数`を使う。
- [ ] `step_actions`では`actions`1件から1スロット、2件から2スロットを生成する。
- [ ] `actions`数がキャラクターの`行動回数`より多くても切り捨てやランダム抽出をしない。
- [ ] `actions`数がキャラクターの`行動回数`より少なくても余分なスロットを生成しない。
- [ ] `actions: []`のstepで0スロットとなり、Select完了判定が停止しない。
- [ ] 未知・使用不能スキルのスロットはキャンセルされ、別スキルへ置換されない。
- [ ] 対象候補が空なら該当スロットだけがキャンセルされ、同じ敵の他スロットは維持される。
- [ ] RoundStartの遅延効果で召喚された、条件に一致する`target_only`キャラクターを同ラウンドの対象に選べる。
- [ ] Select完了後またはResolve途中に召喚されたキャラクターを、そのラウンドの生成済みintentへ遡って追加しない。
- [ ] 対象確定後に対象が死亡または消滅しても別の対象へ自動再選択せず、該当スロットだけが不発になる。
- [ ] PCが有効な敵スロットへ通常どおり割り込み・マッチできる。
- [ ] RoundStart再実行、intent再生成、再接続でもスロットとstepが重複しない。
- [ ] Behavior Runtimeのstepが生成スロット数に関係なく1ラウンドに1回だけ進む。
- [ ] プリセットJSONの搬出入と保存・復元で`slot_generation_mode`と`on_no_target`が維持される。
- [ ] UIに各stepの行動数と現在のスロット生成方式が表示される。

## 10. 受け入れ条件

- 新方式の敵は、チャートの当該stepへ設定したスキル数と同数のスロットを生成する。
- GMはキャラクターの`行動回数`とチャートのスキル数を同期管理する必要がない。
- 行動チャート編集画面で、Profile全体のスロット生成方式を確認・変更できる。
- シナリオNo.2では3R・6R・9Rに通常技と吸収技の2スロット、それ以外は通常技の1スロットを生成する。
- 瓦礫がなければPCへフォールバックせず、吸収スロットだけをキャンセルする。
- 次ラウンド開始時に召喚された瓦礫は対象候補となり、対象確定後に破壊された瓦礫は別の瓦礫へ自動変更されない。
- 既存チャート、非チャート敵、プレイヤー、PvPの行動数は変更されない。
- 実装後、汎用仕様とUI仕様を`manuals/implemented/`の既存正本へ統合し、本書を削除する。
