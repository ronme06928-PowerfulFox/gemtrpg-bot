# 40 召喚戦闘オブジェクト・シナリオスキル効果基盤計画

**作成日**: 2026-07-30
**状態**: コード基盤実装済み・スプレッドシートJSON反映待ち
**ユースケース**: シナリオNo.2『瓦礫で鋳るは魔の鋼』の「鉄交じりの瓦礫」「鉄根刺突」「暴れ回る」「瓦礫を狙う」
**関連計画**: [38_Scenario_No2_Task_Hub.md](38_Scenario_No2_Task_Hub.md) / [39_PvE_Behavior_Action_Driven_Slots_Plan.md](39_PvE_Behavior_Action_Driven_Slots_Plan.md)

---

## 1. 目的

召喚テンプレートの`特記JSON`から、キャラクタータグ、パッシブID、インライン常時効果を安全に定義できるようにする。

あわせて、次の性質を持つ「戦闘オブジェクト」をSelect/Resolve戦闘で扱える汎用基盤を作る。

- フィールド上にキャラクターとして存在する。
- HPを持ち、スキルの対象になり、ダメージと死亡処理を受ける。
- 自身は行動せず、通常の行動スロットを生成しない。
- 死亡原因となったキャラクターとスキルに応じて死亡時効果を分岐できる。

さらに、シナリオNo.2で作成済みの`E-33`〜`E-35`を実行可能にするため、既存の汎用effectを組み合わせ、不足するフィールド集計と遅延召喚を追加する。シナリオ固有の名称やIDをコードへハードコードしない。

## 2. 現状

### 2.1 召喚テンプレート

`manager/summons/loader.py::_build_row_template`は、`特記JSON`を辞書として読み込み、`template = dict(extra)`で任意キーをいったん保持する。

このため、次の記述は現在でもキャッシュへ残せる。

```json
{
  "tag_ids": ["瓦礫"]
}
```

一方、`SPassive`はその後に「パッシブスキル」列の値で無条件に上書きされる。列が空の場合も空配列で上書きされるため、次の`SPassive`は現在の実装では失われる。

```json
{
  "SPassive": ["Pa-XX"]
}
```

`special_buffs`は上書き対象ではなく、召喚処理もテンプレートから引き継ぐ。したがって、`special_buffs[].data.on_death`を使ったインライン死亡時効果は既存構造で表現できるが、正式な入力契約、検証、マニュアル、専用テストがない。

### 2.2 パッシブ

`SPassive`の既存契約はパッシブIDの配列である。各パッシブの効果本体はパッシブマスターのJSON定義に置き、キャラクター投入時に`special_buffs`へ展開する。

既存の死亡処理は次に対応している。

- HPが正数から0以下へ遷移した場合だけ死亡時処理を行う。
- 死亡原因となったキャラクターと使用スキルを`death_context`へ保持する。
- パッシブ由来またはインラインの`on_death`を`IMMEDIATE`で実行する。
- `APPLY_STATE`、`APPLY_BUFF`、`CUSTOM_DAMAGE`、`SUMMON_CHARACTER`、`GRANT_SKILL`を死亡時に反映する。

したがって、瓦礫の死亡時パッシブは新しい死亡イベント基盤ではなく、既存の`on_death`と`death_context`を利用する。

### 2.3 非行動キャラクター

現在のラウンド開始処理は、`行動回数`が0以下でも最低1スロットへ補正する。戦闘スキルを1つも持たない召喚体も、永続的な非行動キャラクターにはならない。

また、単体スキルの対象はキャラクターIDではなくスロットIDで指定する。単純にスロット生成を止めるだけでは、瓦礫を攻撃対象として選べなくなる。

### 2.4 作成済みスキル

| ID | 名称 | 現在の状態 |
|---|---|---|
| `E-32` | 鉄塊を捥ぎり喰う | `DEAL_TARGET_MAX_HP_DAMAGE`と瓦礫タグ条件のJSON作成済み |
| `E-33` | 鉄根刺突 | 表示文作成済み。`特記処理`は空 |
| `E-34` | 暴れ回る | 表示文作成済み。`特記処理`は空 |
| `E-35` | 瓦礫を狙う | 表示文作成済み。`特記処理`は空 |

## 3. 決定するデータ契約

### 3.1 召喚テンプレートの`特記JSON`

`特記JSON`で次のキーを正式に受け付ける。

```json
{
  "tag_ids": ["瓦礫"],
  "disabled_tag_ids": [],
  "SPassive": ["Pa-XX"],
  "special_buffs": [],
  "flags": {}
}
```

- `tag_ids` / `disabled_tag_ids`は文字列配列として正規化する。
- `SPassive`はパッシブIDの文字列配列とする。
- 「パッシブスキル」列と`特記JSON.SPassive`の両方に値がある場合は、両方を順序どおり結合し、完全一致の重複を除く。
- 列が空であっても`特記JSON.SPassive`を空配列で上書きしない。
- `special_buffs`は既存どおり辞書配列を許可する。
- 不正な型は黙って別の型へ変換せず、テンプレートIDとキー名を含む警告を残して安全な空値へ正規化する。
- 既存の専用列、既存キャッシュ、`特記JSON`を持たないテンプレートの挙動は変えない。

### 3.2 `SPassive`と効果本体

`SPassive`へ効果オブジェクトを直接入れる方式は採用しない。`SPassive`はパッシブID参照のまま維持する。

再利用可能で名称を持つパッシブは、パッシブマスターへ次のように効果本体を定義する。

```json
{
  "on_death": []
}
```

召喚テンプレートだけで完結する匿名効果が必要な場合は、`SPassive`ではなく次の既存形式を利用する。

```json
{
  "special_buffs": [
    {
      "name": "任意の常時効果名",
      "lasting": -1,
      "delay": 0,
      "data": {
        "on_death": []
      }
    }
  ]
}
```

シナリオNo.2の「魔力の籠った鉄塊」は、戦闘中に名称と効果を確認できる正式パッシブ`Pa-07`として登録済みである。`U-02`の`SPassive`から`Pa-07`を参照する。

表示文では「行動せず、スロットを持たない」という内部仕様をそのまま書かず、次の一文へ置き換える。

> 根から捥ぎ取られた鉄塊は意志を持たず、戦場に沈黙したまま横たわる。

非行動であることの厳密な保証は、表示文ではなく`Pa-07.effect.action_slot_mode="none"`で行う。フレーバーテキスト欄を別に使う場合は、次を候補とする。

> 根から捥ぎ取られた鉄塊は、意志もなく戦場に横たわる。だが、内に籠もる魔力は、それを砕いた者の力へと形を変える。

### 3.3 キャラクタータグ

シナリオNo.2では、既存の`E-32`と行動チャートの条件に合わせ、瓦礫タグを完全一致の`"瓦礫"`へ統一する。

```json
{
  "tag_ids": ["瓦礫"]
}
```

`"瓦礫"`と`"種別:瓦礫"`を同義語として暗黙変換しない。タグ条件は既存仕様どおり完全一致とする。

## 4. 非行動・対象可能な戦闘オブジェクト

### 4.1 パッシブ効果

パッシブ効果へ、通常の行動スロットを生成しないことを示す汎用設定を追加する。

```json
{
  "action_slot_mode": "none"
}
```

- 欠損時は従来どおり`normal`として扱う。
- `none`のキャラクターはラウンド開始時に通常行動スロットを生成しない。
- 行動回数、加速・減速、自動スキル選択、Behavior Profileより`action_slot_mode:none`を優先する。
- 死亡、未配置、離脱済みのキャラクターは従来どおり対象候補から除外する。

### 4.2 対象専用アンカー

Select/Resolveの単体対象がスロットIDを必要とするため、`action_slot_mode:none`の配置済み生存キャラクターには内部的な対象専用アンカーを生成する。

- アンカーは`battle_state.slots`に存在し、`target_only:true`を持つ。
- 攻撃側の`target.slot_id`から参照できる。
- 自身のintentを持たず、宣言待ち、Resolve待ち、コスト消費、行動順、マッチ相手にはならない。
- 相手から攻撃された場合は、防御スキルを持たない対象への一方攻撃として処理する。
- PvE対象候補、PCの対象選択、redirect、広域対象収集で通常キャラクターと同じ生存・配置判定を受ける。
- 通常の行動スロットとしてタイムラインや行動予告へ表示しない。
- 死亡、未配置化、戦闘離脱時に対象専用アンカーを無効化する。
- Resolve準備判定ではアンカーにコミットを要求しない。

この内部アンカーは実装都合の参照点であり、ルール上は「スロットを持たず、行動しない」と表現する。

## 5. 瓦礫死亡時パッシブ

### 5.1 必要データ

瓦礫破壊時の強化は専用の効果オブジェクトをその場で生成せず、バフ図鑑に登録した次の状態を`APPLY_BUFF`で付与する。

| ID | 名称 | 効果 | 付与先 |
|---|---|---|---|
| `Bu-51` | 鉄の恩恵 | 全スキル最終威力+2、2ラウンド継続 | 破壊者が味方陣営の場合、味方陣営全員 |
| `Bu-52` | 鉄の剛力 | 全スキル最終威力+1、3ラウンド継続 | 破壊者が敵陣営の場合、破壊者 |

`Bu-51`と`Bu-52`のバフ図鑑「JSON定義」には、説明文だけでなく次の効果本体を登録する。

```json
{
  "power_bonus": [
    {
      "operation": "FIXED",
      "value": 2,
      "apply_to": "final"
    }
  ]
}
```

`Bu-52`は`value`を`1`にする。それ以外の構造は`Bu-51`と共通とする。

- バフ図鑑の「持続ラウンド」は、`Bu-51=2`、`Bu-52=3`とする。
- 瓦礫死亡時の付与では従来の決定を維持し、`delay=1`として次のラウンドから有効化する。
- 瓦礫パッシブの`APPLY_BUFF`に`lasting`を明示し、`Bu-51=2`、`Bu-52=3`を指定する。今回の効果ではバフ図鑑の`default_duration`へ依存しない。
- 現行の`APPLY_BUFF`は`lasting`と`delay`を受け付けるため、この部分に新しい持続時間基盤は追加しない。
- `{"type":"stat_mod","stat":"最終威力","value":2}`というバフJSONは採用しない。現行の最終威力計算は`stat_mods["最終威力"]`を参照しないため、上記の`power_bonus`形式へ統一する。
- 2026-07-30の確認時点ではローカルの`buff_catalog_cache.json`は`Bu-50`までである。スプレッドシートのJSON定義確定後、`--update`で`Bu-51`と`Bu-52`をキャッシュへ反映する。

- 瓦礫パッシブ: 死亡原因となったキャラクターと瓦礫の陣営関係に応じて上記を振り分ける
- 非行動パッシブ: `action_slot_mode:none`

瓦礫パッシブと非行動設定は`Pa-07`へまとめる。`U-02`側のインライン`special_buffs`へ同じ効果を重ねて登録しない。

### 5.2 分岐

- 死亡原因のキャラクターが味方陣営なら、味方陣営の配置済み・生存中キャラクター全員へ`Bu-51`を付与する。
- 死亡原因のキャラクターが敵陣営なら、死亡原因のキャラクターへ`Bu-52`を付与する。
- 死亡原因が存在しない、スキルによるHP0化ではない、または条件を判定できない場合は、どちらのバフも付与しない。
- HP0の瓦礫への追加ダメージでは再発しない。
- 蘇生後に再び正数から0へ遷移した場合は、既存死亡仕様どおり再発を許可する。

この分岐をパッシブJSONだけで記述できるよう、死亡時効果に次の汎用参照を追加する。

- 条件参照`death_context.killer_team`: 死亡原因となったキャラクターの陣営を`ally`または`enemy`で返す。
- 対象`KILLER`: 死亡原因となったキャラクター。
- 対象`KILLER_TEAM`: 死亡原因となったキャラクターと同陣営の配置済み・生存中キャラクター全員。

瓦礫パッシブの効果本体は、概ね次の形とする。正式なキー名は実装時に既存のcondition命名規則へ合わせる。

```json
{
  "on_death": [
    {
      "timing": "IMMEDIATE",
      "type": "APPLY_BUFF",
      "target": "KILLER_TEAM",
      "buff_id": "Bu-51",
      "lasting": 2,
      "delay": 1,
      "condition": {
        "source": "death_context",
        "param": "killer_team",
        "operator": "EQUALS",
        "value": "ally"
      }
    },
    {
      "timing": "IMMEDIATE",
      "type": "APPLY_BUFF",
      "target": "KILLER",
      "buff_id": "Bu-52",
      "lasting": 3,
      "delay": 1,
      "condition": {
        "source": "death_context",
        "param": "killer_team",
        "operator": "EQUALS",
        "value": "enemy"
      }
    }
  ]
}
```

### 5.3 累積と再付与

- `Bu-51`と`Bu-52`は同名状態を1件だけ保持し、効果は累積しない。
- 効果中に再付与された場合、効果値は増やさず、`delay`と`lasting`を新しい付与内容へ更新する。
- 複数の瓦礫が同じスキルで同時に破壊された場合も、同一バフは1件だけ保持する。

## 6. シナリオスキルの実行基盤

### 6.1 `E-35 瓦礫を狙う`

新しいeffect typeは追加しない。既存の条件付き`DAMAGE_BONUS`を使う。

```json
{
  "schema": "skill_json_rule_v2",
  "id": "SKILL_E35",
  "target_scope": "any",
  "power_bonus": [],
  "cost": [],
  "effects": [
    {
      "timing": "HIT",
      "type": "DAMAGE_BONUS",
      "target": "target",
      "value": 20,
      "condition": {
        "source": "target",
        "param": "tag_ids",
        "operator": "CONTAINS",
        "value": "瓦礫"
      }
    }
  ]
}
```

対象を同陣営の瓦礫だけに限定する処理はBehavior Profileの順序付き対象候補で行う。スキルJSONの条件は、誤った対象へ20ダメージが加算されることを防ぐ二重防御とする。

### 6.2 `E-34 暴れ回る`

ランダムな相手陣営キャラクターの選択はBehavior Profileの対象方針で行う。

スキル効果は、使用を確定した次のラウンド開始時に`U-02`を2体召喚する。正確な発動時期を保つため、ラウンド開始時実行の予約基盤を追加する。

予約データは少なくとも次を保持する。

- 発生元キャラクターID
- 発生元スキルID
- 実行予定ラウンド
- 実行するeffect
- `repeat_count`
- 同一スロットからの二重予約を防ぐ一意キー

RoundStartの再実行、再接続、保存復元で二重召喚しない。発生元が死亡していても予約済みの召喚を実行するかは、スキル文どおり「使用時に予約が成立する」ものとして実行する。

### 6.3 `E-33 鉄根刺突`

的中時の《破裂》10と3ラウンドの《亀裂》3は既存effectで処理する。

`RESOLVE_START`では、効果適用前のフィールド状態を基準として、次を一度だけ行う。

1. 使用者と同陣営、配置済み、生存中、有効な`"瓦礫"`タグを持つキャラクターを抽出する。
2. 抽出数を確定する。
3. 抽出対象すべてへ`DEAL_TARGET_MAX_HP_DAMAGE`を適用する。
4. 抽出数が1以上なら、使用者へ「抽出数×1」の全スキル最終威力補正を、このラウンド中だけ付与する。

フィールド上の一致キャラクター数をバフ値へ変換する汎用effectを追加する。仮のデータ形は次とし、実装時に`skill_json_rule_v2`の命名規則へ合わせて正式化する。

```json
{
  "timing": "RESOLVE_START",
  "type": "APPLY_BUFF_FROM_CHARACTER_COUNT",
  "target": "self",
  "buff_id": "Bu-TBD",
  "lasting": 1,
  "delay": 0,
  "value_per_character": 1,
  "character_filter": {
    "team": "same_team",
    "required_tag_ids": ["瓦礫"],
    "alive": true,
    "placed": true
  }
}
```

- 一致数は瓦礫をHP0にする前のスナップショットで数える。
- `RESOLVE_START`はコミット済みスロットごとに一度だけ処理する。
- 同じスロットの再処理や再接続で重複発火しない。
- 瓦礫へのHP0化には使用者と`E-33`を死亡原因として渡し、通常の瓦礫死亡時パッシブを発火させる。
- 瓦礫が0体の場合、破壊処理と追加強化はどちらも発生しないが、PC全員への広域攻撃自体は通常どおり解決する。

## 7. 自然言語JSONビルダー

実行基盤と正式JSONの形を確定した後に対応する。ビルダーを先に拡張して、実行不能なJSONを生成しない。

### 7.1 追加文型

- `対象の特徴に「瓦礫」があるなら、20ダメージを与える。`
  - タグ条件付き`DAMAGE_BONUS`
- `次のラウンド開始時、「鉄交じりの瓦礫」2体を召喚する。`
  - 召喚テンプレート名からIDを解決し、2体分を予約
- `フィールドに存在する全ての「鉄交じりの瓦礫」のHPを0にする。`
  - 同陣営・タグ条件付きの全対象最大HPダメージ
- `存在していた「鉄交じりの瓦礫」が1体につき1、このラウンドで自身が使うスキルの最終威力をアップする。`
  - フィールド一致数を参照するバフ付与

### 7.2 召喚名の解決

- 「召喚する」を一律`U-00`へ変換する既存処理を廃止する。
- 召喚テンプレートキャッシュのIDまたは表示名と完全一致する場合だけ変換する。
- 一致なし、複数一致、個数欠損は変換失敗として理由を表示する。
- 自動推測で別の召喚テンプレートへフォールバックしない。

## 8. 実装順序

### Phase 1: 召喚テンプレートJSON契約

1. `tag_ids` / `disabled_tag_ids` / `SPassive` / `special_buffs`の正規化を追加する。
2. `特記JSON.SPassive`と「パッシブスキル」列を結合し、空列による上書きをなくす。
3. ローダー、召喚サービス、キャッシュ復元のテストを追加する。
4. `C01_JSON_Definition_Master.md`へ実装済み仕様を統合する。

### Phase 2: 非行動・対象可能オブジェクト

1. パッシブの`action_slot_mode:none`を読み取る共通ヘルパーを追加する。
2. 通常行動スロットの生成を抑止する。
3. 対象専用アンカーを生成し、対象選択と一方攻撃で利用可能にする。
4. 宣言待ち、Resolve待ち、タイムライン表示、PvE intentから対象専用アンカーの行動を除外する。
5. 死亡、未配置、離脱、ラウンド再生成時の掃除を実装する。

### Phase 3: 瓦礫死亡時パッシブ

1. `Bu-51`と`Bu-52`へ全スキル最終威力補正のJSON定義を登録する。
2. `death_context.killer_team`、`KILLER`、`KILLER_TEAM`を追加する。
3. `Pa-07`へ`action_slot_mode:none`と、死亡原因の陣営によって`Bu-51`と`Bu-52`を付け分ける`on_death`を登録する。`lasting`と`delay`もパッシブJSONで指定する。
4. 非累積、再付与時更新、同時複数破壊を検証する。
5. `U-02`へ`tag_ids:["瓦礫"]`と`SPassive:["Pa-07"]`を設定する。
6. `--update`を実行し、`Bu-51`、`Bu-52`、瓦礫パッシブ、`U-02`を各キャッシュへ反映する。

### Phase 4: 既存effectで完成できるスキル

1. `E-35`へ条件付き`DAMAGE_BONUS`と`target_scope:any`を設定する。
2. `E-32`と`E-35`が同じ瓦礫タグへ一致することを確認する。
3. PC、別の敵、無効化された瓦礫タグへの誤適用がないことを検証する。

### Phase 5: 遅延召喚

1. 次ラウンド開始時のeffect予約データを追加する。
2. RoundStartで冪等に予約を実行し、実行済み予約を除去する。
3. `E-34`から`U-02`を2体召喚するJSONを作成する。
4. 保存復元、再接続、RoundStart再実行、召喚元死亡を検証する。

### Phase 6: フィールド集計effect

1. タグ・陣営・生存・配置条件によるフィールドキャラクター集計を追加する。
2. 集計値をバフの`data.value`へ渡すeffectを追加する。
3. `E-33`の瓦礫一括破壊、死亡原因、当該ラウンド強化を実装する。
4. 0体、1体、2体、同時死亡、同一Resolve再実行を検証する。

### Phase 7: 自然言語JSONビルダー

1. 3技能の追加文型を実装する。
2. 召喚テンプレート名解決を追加する。
3. 変換成功、曖昧、未登録名、不正文型のテストを追加する。
4. フロントエンドをビルドし、生成物を更新する。

### Phase 8: 計画39とシナリオデータ

1. 計画39の行動チャート駆動スロット生成を実装する。
2. 小型、中型、ボス、瓦礫の正式キャラクターデータを作成する。
3. `E-33`〜`E-35`の正式JSONをスプレッドシートへ登録し、`--update`でキャッシュを更新する。
4. 通常戦闘2、ボス戦、瓦礫不在、複数瓦礫、HP低下後の行動チャートを実機確認する。

## 9. 主な変更候補

- `manager/summons/loader.py`
- `manager/summons/service.py`
- `manager/utils.py`またはパッシブ効果参照用の分割モジュール
- `manager/battle/select_resolve_state.py`
- `manager/battle/pve_intent_planner.py`
- `manager/battle/resolve_queue_helpers.py`
- `manager/battle/resolve_effect_runtime.py`
- `manager/battle/effect_handlers/`
- `manager/json_rule_v2.py`
- `CharaCreator/json_definition_builder.html`
- `static/js/battle/components/DeclarePanel.js`
- `static/js/battle/components/ResolveFlowPanel.js`
- `tests/test_summon_loader.py`
- `tests/test_summon_system.py`
- `tests/test_passive_effect_buffs.py`
- `tests/test_death_context.py`
- `tests/test_select_resolve_smoke.py`
- `tests/test_pve_auto_intents.py`
- JSONビルダーと新effectの専用テスト

## 10. テスト要件

- [ ] `特記JSON.tag_ids`が召喚キャラクターまで保持される。
- [ ] `特記JSON.SPassive`が空の専用列で消えない。
- [ ] JSONと専用列のパッシブIDが順序を保って結合され、重複しない。
- [ ] `special_buffs[].data.on_death`を使う既存インライン形式も壊れない。
- [ ] `action_slot_mode:none`のキャラクターが行動スロットを生成しない。
- [ ] 非行動キャラクターをPCと敵の双方が単体攻撃の対象にできる。
- [ ] 対象専用アンカーが宣言待ち、行動順、Resolve待ちへ入らない。
- [ ] 味方が瓦礫を破壊すると、味方陣営の配置済み・生存中キャラクター全員へ`Bu-51`が付与される。
- [ ] 敵が瓦礫を破壊すると、破壊者へ`Bu-52`が付与される。
- [ ] `Bu-51`は全スキル最終威力+2を2ラウンド、`Bu-52`は全スキル最終威力+1を3ラウンド反映する。
- [ ] 瓦礫死亡時に付与された`Bu-51`と`Bu-52`は、付与の次のラウンドから有効になる。
- [ ] 瓦礫パッシブの`APPLY_BUFF`が`Bu-51`へ`lasting=2`、`Bu-52`へ`lasting=3`を明示して付与する。
- [ ] 各バフは累積せず、再付与時に持続時間を更新する。
- [ ] HP0への追加ダメージで死亡時効果が再発しない。
- [ ] `E-35`は瓦礫にだけ追加20ダメージを与える。
- [ ] `E-34`は次ラウンド開始時に`U-02`をちょうど2体召喚する。
- [ ] RoundStart再実行で`E-34`の召喚数が増えない。
- [ ] `E-33`はResolve開始時の瓦礫数を基準に一括破壊と当該ラウンド強化を行う。
- [ ] `E-33`による破壊でも通常の瓦礫死亡時パッシブが発火する。
- [ ] 既存召喚、通常キャラクター、通常スロット、既存パッシブの挙動が変わらない。

## 11. 受け入れ条件

- `U-02`の`特記JSON`だけで瓦礫タグとパッシブIDを保持できる。
- `SPassive`はID参照、効果本体はパッシブマスターJSONという既存契約が維持される。
- 必要な場合は`special_buffs[].data`でインライン常時効果も記述できる。
- 鉄交じりの瓦礫は行動せず、通常スロットを表示せず、PCと敵の攻撃対象にはなる。
- 瓦礫の破壊者に応じて`Bu-51`または`Bu-52`が、正しい対象、開始ラウンド、持続ラウンドで付与される。
- `E-33`〜`E-35`が文章表示だけでなく、Select/Resolve上で自動処理される。
- 自然言語JSONビルダーが3技能の正式JSONを生成できる。
- 計画39の実装後、行動チャートだけで通常行動、瓦礫攻撃、追加スロット、大技周期を管理できる。
- 実装完了後、本計画を削除し、汎用仕様を`B01` / `B02` / `B03` / `C01` / `D01` / `E02`へ統合する。

## 12. スプレッドシートで先に準備するデータ

### 12.1 現時点で完成できるもの

| シート | ID | 作業 |
|---|---|---|
| バフ図鑑 | `Bu-51` | 名称を「鉄の恩恵」、持続を2、JSON定義を全スキル最終威力+2の`power_bonus`形式にする |
| バフ図鑑 | `Bu-52` | 名称を「鉄の剛力」、持続を3、JSON定義を全スキル最終威力+1の`power_bonus`形式にする |
| 特殊パッシブ | `Pa-07` | 名称を「魔力の籠った鉄塊」とし、効果文の非行動部分を§3.2のフレーバー表現へ置き換える |
| 召喚テンプレート | `U-02` | HP30、永続、重複可、戦闘スキルなし、パッシブスキル列へ`Pa-07`、特記JSONへ`{"tag_ids":["瓦礫"]}`を設定する |
| 敵スキル | `E-35` | 既存の条件付き`DAMAGE_BONUS`で、瓦礫タグへの追加20ダメージをJSON化する |
| 敵スキル | `E-33` | 的中時の《破裂》10と3ラウンドの《亀裂》3だけを、既存effectで先にJSON化できる |

`U-02`の`SPassive`は、現行ローダーの上書き問題を避けるため、計画40 Phase 1完了までは`特記JSON`ではなく既存の「パッシブスキル」列へ`Pa-07`を記入する。`tag_ids`は現状でも`特記JSON`から保持される。

### 12.2 行だけ確保してもよいもの

`E-33`が瓦礫数に応じて得る可変値の全スキル最終威力バフは、専用のバフIDを1件使用する予定である。次の空きIDを確保してよいが、JSONの値参照契約はPhase 6で確定するため、現時点では名称、説明、JSONを確定しない。

### 12.3 基盤実装後にJSONを完成させるもの

- `Pa-07`の`action_slot_mode:none`と陣営分岐付き`on_death`
- `E-34`の次ラウンド開始時の`U-02`二体召喚
- `E-33`の瓦礫一括破壊、破壊前の体数集計、可変値バフ
- 計画39を使う敵キャラクターのBehavior Profileと行動チャート

これらは未実装キーの仮名をスプレッドシートへ先行登録せず、実装時に確定したJSONを記入する。

## 13. 2026-07-31 実装結果と残作業

Phase 1〜7のコード基盤を実装した。汎用仕様は`C01`、`B02`、`B03`へ統合済み。本計画は、次のスプレッドシート反映と実機確認が残るため維持する。

自動検証は2026-07-31時点で全件成功している（`792 passed, 2 skipped`）。フロントエンド成果物も`npm run build`相当で再生成済み。

### 13.1 `Pa-07` JSON効果

```json
{"action_slot_mode":"none","on_death":[{"timing":"IMMEDIATE","type":"APPLY_BUFF","target":"KILLER_TEAM","buff_id":"Bu-51","lasting":2,"delay":1,"condition":{"source":"death_context","param":"killer_team","operator":"EQUALS","value":"ally"}},{"timing":"IMMEDIATE","type":"APPLY_BUFF","target":"KILLER","buff_id":"Bu-52","lasting":3,"delay":1,"condition":{"source":"death_context","param":"killer_team","operator":"EQUALS","value":"enemy"}}]}
```

### 13.2 `E-34` 特記処理

```json
{"schema":"skill_json_rule_v2","id":"SKILL_E34","target_scope":"opposing_team","power_bonus":[],"cost":[],"effects":[{"timing":"RESOLVE_START","type":"SCHEDULE_EFFECT","target":"self","round_offset":1,"repeat_count":2,"effect":{"type":"SUMMON_CHARACTER","summon_template_id":"U-02"}}]}
```

### 13.3 `E-33` 特記処理

```json
{"schema":"skill_json_rule_v2","id":"SKILL_E33","target_scope":"opposing_team","power_bonus":[],"cost":[],"effects":[{"timing":"RESOLVE_START","type":"APPLY_BUFF_FROM_CHARACTER_COUNT","target":"self","buff_name":"瓦礫吸収","lasting":1,"delay":0,"value_per_character":1,"apply_to":"final","character_filter":{"team":"same_team","required_tag_ids":["瓦礫"],"alive":true,"placed":true}},{"timing":"RESOLVE_START","type":"CUSTOM_EFFECT","target":"FILTERED_CHARACTERS","value":"DEAL_TARGET_MAX_HP_DAMAGE","character_filter":{"team":"same_team","required_tag_ids":["瓦礫"],"alive":true,"placed":true}},{"timing":"HIT","type":"APPLY_STATE","target":"target","state_name":"破裂","value":10},{"timing":"HIT","type":"APPLY_STATE","target":"target","state_name":"亀裂","value":3,"rounds":3}]}
```

### 13.4 `E-35` 特記処理

```json
{"schema":"skill_json_rule_v2","id":"SKILL_E35","target_scope":"any","power_bonus":[],"cost":[],"effects":[{"timing":"HIT","type":"DAMAGE_BONUS","target":"target","value":20,"condition":{"source":"target","param":"tag_ids","operator":"CONTAINS","value":"瓦礫"}}]}
```

### 13.5 残作業

1. 上記JSONをスプレッドシートへ登録し、`--update`でキャッシュを更新する。
2. `Pa-07`の表示文から内部仕様文を外し、§3.2のフレーバーへ置き換える。
3. 計画39の行動チャート駆動スロット生成を実装する。
4. 通常戦闘2とボス戦を実機確認し、予約召喚、対象専用アンカー、瓦礫死亡時バフ、鉄根刺突の一括破壊を検証する。
