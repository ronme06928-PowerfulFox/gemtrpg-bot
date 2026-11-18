# バランス検証シミュレータ CLI

最終更新: 2026-11-14（ユニット資源からの構築）

バランス検証シミュレータは、実際の Select/Resolve 戦闘エンジンをヘッドレスで動かし、遭遇・敵編成・スキル調整の妥当性を確認するための検証ツールです。本番の戦闘エンジン本体は変更せず、シミュレータ側で room_state、乱数、Socket、保存処理を差し替えて実行します。

## ファイル構成

- `scripts/simulate_battle.py`: CLI 入口。引数解析、入力読み込み、出力整形を担当。
- `manager/sim/battle_runner.py`: ヘッドレス戦闘実行、決定論ダイス、実行時パッチ、味方 intent 自動投入を担当。
- `manager/sim/preset_loader.py`: ユニット管理の資源、味方/敵編成、ステージから一時 room_state を生成。
- `manager/sim/positions.py`: 味方・敵を自動配置する。実行時キャラクターは `manager/units/characters.py` で組み立てる。
- `manager/battle/battle_result.py`: 全滅に基づく勝敗を判定する。
- `manager/sim/reporting.py`: レポート dataclass、HP 集計、膠着理由判定、複数試行集計、コンソール整形を担当。
- `tests/sim/test_simulate_battle.py`: シミュレータの回帰テスト。

## 基本の起動方法

ステージ ID から検証する例:

```bash
python scripts/simulate_battle.py --stage-id ST-001 --roll-mode all --max-rounds 10 --auto-ally-intents
```

JSON で結果を取得する例:

```bash
python scripts/simulate_battle.py --stage-id ST-001 --roll-mode median --max-rounds 10 --json
```

保存済み room_state JSON を直接使う例:

```bash
python scripts/simulate_battle.py --input encounter_room_state.json --roll-mode all --max-rounds 10
```

## 入力方法

入力は大きく 2 系統です。

1. `--input` で room_state JSON を渡す。
2. `--stage-id`、`--ally-formation-id`、`--enemy-formation-id`、`--ally-preset-id`、`--enemy-preset-id` でユニット管理の資源から一時 room_state を組み立てる。

`--input` とプリセット系オプションは同時に指定しません。保存済み状態の検証と、プリセットからの検証用シナリオ生成を明確に分けるためです。

プリセット指定の例:

```bash
python scripts/simulate_battle.py --stage-id ST-001 --roll-mode median
python scripts/simulate_battle.py --ally-formation-id ALLY_1 --enemy-formation-id ENEMY_1 --roll-mode median
python scripts/simulate_battle.py --ally-preset-id U-004 --enemy-preset-id U-002 --roll-mode median
```

オプションを省略した場合はローカルアプリDBを読みます。任意の明示Export JSONを使う場合:

```bash
python scripts/simulate_battle.py --preset-store units.json --list-stages
```

## ID 一覧の確認

ID を探すための一覧表示オプションがあります。これらは戦闘入力なしで実行できます。

```bash
python scripts/simulate_battle.py --list-stages
python scripts/simulate_battle.py --list-presets
python scripts/simulate_battle.py --list-ally-formations
python scripts/simulate_battle.py --list-enemy-formations
```

機械可読で取得する場合:

```bash
python scripts/simulate_battle.py --list-presets --json
```

## ダイスモード

`--roll-mode` でダイスの振り方を指定します。

- `low`: すべてのダイスを最小値で扱う。
- `median`: すべてのダイスを中央値、端数は切り上げで扱う。
- `high`: すべてのダイスを最大値で扱う。
- `random`: 通常の乱数で振る。
- `all`: `low`、`median`、`high` を順に実行する。

低/中/高の 3 条件を見ることで、「低ロールで詰まるか」「中央値で想定ラウンドに収まるか」「高ロールでも破綻しないか」を確認できます。

## レポート項目

各実行結果は `BattleReport` として出力されます。

- `result`: `ally_win`、`enemy_win`、`draw`、`in_progress`、`invalid_state` のいずれか。
- `rounds`: 実行されたラウンド数。
- `stalled`: `in_progress` のまま終了した場合は true。
- `summary`: 味方/敵それぞれの生存数、総数、残HP、最大HP、残HP率。
- `stall_reason`: 膠着または異常終了の理由。
- `rounds_detail`: ラウンドごとの result、確定 intent 数、味方HP、敵HP、HP変化量。

`stall_reason` は次の値を取ります。

- `invalid_battle_state`: round_start などで戦闘状態を作れなかった。
- `no_committed_intents`: 確定 intent がなく、行動が成立していない。
- `no_damage_progress`: intent はあるが HP が変化していない。
- `max_rounds_reached`: HP 変化はあるが最大ラウンドに到達した。
- `unknown`: 上記以外の未分類。

## 複数試行と集計

`--runs` で同じ条件を複数回実行できます。特に `--roll-mode random` と組み合わせると、実戦に近い勝率や平均ラウンドを確認できます。

```bash
python scripts/simulate_battle.py --stage-id ST-001 --roll-mode random --runs 30 --seed 100 --json
```

`--seed` を指定すると、乱数試行を再現しやすくなります。各 run では、基準 seed に roll mode と run index のオフセットを加えます。

複数試行の集計には次が含まれます。

- 結果別件数
- 膠着理由別件数
- 味方勝率
- 敵勝率
- 引き分け率
- stall 率
- 平均決着ラウンド
- 味方平均残HP率
- 敵平均残HP率

## 実運用での使いどころ

最も重要なのは、調整前に一度ベースラインを取ることです。変更後だけ実行しても、強くなったのか弱くなったのか判断しにくくなります。

推奨タイミング:

1. スキル、敵HP、敵火力、行動回数、編成を変更する前。
2. 実装直後のスモーク確認。
3. 数値を小刻みに調整している途中。
4. GM 向け公開や本番投入の前。

比較時は、同じ `stage-id`、同じ `roll-mode`、同じ `max-rounds`、必要なら同じ `seed` を使います。見るべき項目は、勝敗だけではなく、平均ラウンド、残HP率、膠着理由、確定 intent 数です。

## 注意点

- 本ツールは実戦闘エンジンを利用しますが、Socket 送信や保存処理はシミュレータ側で無害化します。
- 味方自動 intent は簡易実装です。回復、支援、範囲、ビルド別 behavior まで完全に最適化するものではありません。
- ユニットのチャットパレットは現在のマスターデータから生成する。
- `--runs 1` の JSON は単一レポート形式、`--runs 2` 以上の JSON は aggregate と runs を持つ集計形式になります。


## 演習場の確率との照合（計画63 PR63-1）

`python scripts/check_drill_match.py --runs 5000` で、キャッシュから演習場の正確な分布を計算し、同じ組をこのCLIのrandomモードで照合する。DBを読まず、確認用の一時入力JSONは自動で削除する。比較はE-00同士（補正6対4）で、両者HP1・行動回数1、PvEで敵の自動スキル選択を有効にする。スキル・バフ・出身の発動がないので、1ラウンドの生存結果が最初のマッチの勝敗に一致する。一般の長期戦の勝率を、最初のマッチだけの確率と同じものとして比較しない。

同スクリプトは、キャッシュのダイスが多い組と16d16同士の計算時間も表示する。シミュレータのパッチを本番APIの中で使わず、CLIを別プロセスで動かす。
