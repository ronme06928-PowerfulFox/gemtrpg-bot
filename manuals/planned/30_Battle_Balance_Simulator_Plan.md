# 30 バランス検証シミュレータ計画

**作成日**: 2026-07-08
**位置づけ**: F02 遭遇設計ガイドの「低/中/高ロールで撃破ターンを概算する」を、実戦闘エンジンを使った pytest ハーネス／CLIで自動化する計画。敵編成を入力に、撃破ターン・詰み（膠着）・全滅有無を機械的に報告する。議論前のたたき台（§7 を一問一答で確定してから実装）。

**2026-07-11 確認**: 既存の `tests/test_select_resolve_smoke.py` と `tests/test_pve_auto_intents.py` のヘッドレス実行経路を再確認し、Phase 1 実装に進める状態と判断。未決定事項は §8 の方針で固定してよい。

---

## 1. 目的

- 新スキル・新遭遇のバランス検証を手作業の概算から解放する。
- F02 の逆算手順（想定ラウンド数・敵HP・敵火力）を、**実エンジンの挙動**（マッチ相殺・状態異常・バフ・AI行動込み）で検証できるようにする。
- 出力: 低/中/高ロール別の決着ラウンド・勝敗・残HP、膠着検出、（将来）スキル使用統計。

## 2. 現状分析（2026-07-08 調査）

### 2.1 ヘッドレス駆動は既存テストが実証済み

現行の本流は Select/Resolve（vNext, slotベース）。`tests/test_select_resolve_smoke.py` と `tests/test_pve_auto_intents.py` が Flask/socket なしで1ラウンドを回す方法を実証している。

**1ラウンドの最小シーケンス**:
1. `extensions.all_skill_data` へキャッシュ実データを投入（`scripts/verify_skill_constraints.py:30-34` の方式が最軽量）
2. `manager/battle/select_resolve_state.py:255 process_select_resolve_round_start` — スロット生成・イニシアチブ（`roll_dice("1d6")`）・**敵intentの自動コミット**（`_apply_pve_auto_enemy_intents`）
3. 味方 intent を `battle_state['intents'][slot_id]` へ直接セット（`test_select_resolve_smoke.py:78-102`）
4. `phase='resolve_mass'` を直接セット → `manager/battle/core.py:643 run_select_resolve_auto`（mass→single フェーズで実ダメージ適用、末尾で `phase='round_end'`）
5. `manager/battle/common_manager.py:315 process_full_round_end`（出血ティック・バフ減衰・END_ROUND）
6. 勝敗は `manager/battle/resolve_auto_runtime.py:37 _bo_estimate_battle_result(state)`（ally全滅/enemy全滅/draw/in_progress）

**Flask app_context は不要**。差し替えが必要なのは `get_room_state` / `save_specific_room_state`(no-op) / `broadcast_log`(no-op) / `_update_char_stat` / `socketio`(emit no-op) / `flask_socketio.emit`(no-op)。各モジュール冒頭に差し替え口があり、core と common_manager を押さえれば `_sync_from_core` で resolve 系へ伝播する。

### 2.2 AI宣言

- **敵側は完全自動化済み**（`pve_intent_planner.py:390`。`flags.auto_skill_select` / `behavior_profile` / ターゲットポリシー対応）。
- **味方側の自動宣言は存在しない**（planner は team=='enemy' のみ）。シミュレータ側で `battle_ai.ai_suggest_skill(char)` ＋ターゲット選択の薄いラッパを書いて intent を組み立てる必要がある。

### 2.3 乱数は2系統（seed一括では不十分）

| 系統 | 箇所 | 注入法 |
|---|---|---|
| `roll_dice`（威力・防御・速度1d6・tiebreak） | `manager/dice_roller.py:57`、`resolve_match_runtime.py:34` ほかモジュール変数として束縛 | モジュール変数の差し替え（`test_pve_auto_intents.py:71` が実例）。**低/中/高は roll_dice を「各ダイス最小/期待値/最大を返す」実装に差し替え**（`total`/`breakdown` の整合必須） |
| `random` 直呼び（AIのスキル/対象選択） | `battle_ai.py:33,61`、`pve_intent_planner.py:314,512...`、`enemy_behavior.py:447` | `random.seed(固定)` または `behavior_profile` で決定論化 |

注意: legacy の `common_manager.process_round_start` は `random.randint(1,6)` 直呼び（:1047）のため使わず、**select_resolve_state 側の round_start に一本化**する。

### 2.4 入力データ

- キャラ辞書の必須: `id` / `type`('ally'|'enemy') / `hp`/`maxHp`/`mp`/`maxMp` / `x`,`y`（**x>=0 必須**、未配置は timeline 除外） / `params`（**速度・行動回数**、物理/魔法補正） / `states` / `flags` / `commands`（チャットパレット文字列。使用可能スキルはここから解析）
- 編成プリセット: `data/cache/battle_only_presets_cache.json` の `character_presets`（`character_json.data` に status[]/params[]/commands）。ランタイムキャラへの変換は既存のプリセット適用実装（`test_room_preset_apply.py` 系）を参照・再利用する。

### 2.5 難所

1. `_update_char_stat` がダメージ適用の唯一の口。HP反映スタブで足りるか、実 `room_manager._update_char_stat` を broadcast 無害化して流用するか（§7）
2. clash は `resolve_match_runtime.py:383` 経由で `duel_solver.execute_duel_match` へ委譲され内部で broadcast/roll_dice を一時差し替えている（最密結合。roll_dice 本体差し替えで波及することは確認済み）
3. エンジンに「膠着」概念がない → シミュレータ側で「上限Nラウンド or HP合計の減少が閾値未満」で打ち切り判定を定義する

## 3. 対象範囲

### 触るもの
- 新規: シミュレータ本体（配置は §7。候補: `scripts/simulate_battle.py` ＋ `tests/sim/` の pytest ラッパ）
- 新規: 味方AI宣言の薄いラッパ、低/中/高 `roll_dice` 差し替え実装、プリセット→キャラ辞書変換

### 触らないもの（禁止事項）
- 戦闘エンジン本体（`manager/battle/*`）のロジック変更。差し替えはすべてシミュレータ側の monkeypatch/注入で行う
- 本番の乱数挙動・Socket イベント

## 4. 設計方針

- **ハーネスの土台**: `test_select_resolve_smoke.py` の monkeypatch セットを fixture 化（`sim_room()` fixture: room_state・スタブ束・skill_data 投入）。
- **1戦闘関数**: `run_battle(room_state, roll_mode, max_rounds) -> BattleReport`
  - ループ: round_start → 味方intent充填（AIラッパ）→ resolve → round_end → `_bo_estimate_battle_result` 判定
  - `BattleReport`: 決着ラウンド / 勝敗 / 各キャラ残HP / ラウンド別与ダメ集計 / 膠着フラグ
- **3シナリオ実行**: `roll_mode ∈ {low, median, high}` を同一編成に適用し、F02 チェックリスト（「低ロールで詰みがないか」「高ロールで想定の半分以下で終わらないか」）を assert 可能にする。
- **入口2つ**:
  - pytest: 代表編成のバランス回帰テスト（想定ラウンド帯を assert）
  - CLI: 任意のプリセットID/JSONを渡してレポート出力（GMの遭遇設計時に使う）
- 決定論性: AI選択は `random.seed(シナリオ固定値)`。behavior_profile 持ちの敵はそのまま決定論に近い挙動になる。

## 5. 実装段階

| Phase | 内容 | 完了条件 |
|---|---|---|
| 1 | ハーネス基盤: fixture（スタブ束＋skill_data投入）＋固定intentで1戦闘完走 | 2vs2 の手書きキャラで決着までループが回り、勝敗が返る |
| 2 | 味方AIラッパ＋低/中/高 roll_dice 差し替え | 同一編成で3シナリオの決着ラウンドが単調（high≦median≦low とは限らないが再現可能）に出力される |
| 3 | プリセット変換: `battle_only_presets_cache.json` → キャラ辞書 | 実プリセットIDを指定して戦闘が回る |
| 4 | レポート整形＋膠着検出＋CLI化 | Markdown/JSON レポート出力。膠着編成のサンプルで打ち切りが働く |
| 5 | 代表編成の回帰テスト整備（雑魚4R帯/中堅8R帯の想定 assert） | CI で回せる実行時間に収まる |

## 6. 推奨PR分割

1. Phase 1（fixture＋固定intent完走）
2. Phase 2（AIラッパ＋rollモード）
3. Phase 3（プリセット変換）
4. Phase 4（レポート＋CLI）
5. Phase 5（回帰テスト＋必要ならCI組込）

## 7. 未決定事項

| 論点 | 選択肢 | 備考 |
|---|---|---|
| 配置 | (1) `scripts/`＋`tests/`併設 / (2) `manager/sim/` として製品コード化 | (2)はGM向けUI提供（将来）に繋がるが重い。まず(1)推奨 |
| `_update_char_stat` | (1) HP/状態反映の忠実スタブ / (2) 実実装を broadcast 無害化して流用 | (2)のほうが死亡連鎖等の忠実度が高い。DB非依存かの検証が先 |
| 味方AIの方式 | (1) ai_suggest_skill＋ターゲットポリシーの薄いラッパ / (2) 味方にも behavior_profile を書かせる | (1)が最小。(2)はビルド別の行動を固定検証できる |
| 中央値ロールの定義 | 期待値の切り捨て / 四捨五入 / 上下2本（floor/ceil）併走 | ダイス期待値が .5 のときの扱い |
| 膠着判定 | 上限ラウンド数（例: 想定+8R）/ HP減少率閾値 / 両方 | F02の「10R以上はボスのみ」を基準にできる |
| 出力形式 | コンソール表 / Markdown / JSON | CLI用途とpytest用途で分ける手もある |
| CI組込 | 回帰テストとして常時実行 / 手動のみ | 実行時間と乱数由来の不安定性次第 |

## 8. 決定事項ログ

| 日付 | 論点 | 決定 | 根拠 |
|---|---|---|---|
| 2026-07-11 | 配置 | まず `scripts/simulate_battle.py` と `tests/sim/` 併設で実装する | GM向けUI化は将来拡張。現時点では手動CLIとpytestハーネスを優先し、戦闘エンジン本体へ製品コードを混ぜない |
| 2026-07-11 | `_update_char_stat` | 実 `manager.room_manager._update_char_stat` を、保存・Socket・ログ送信を無害化して流用する | HPクランプ、死亡時の未配置化、死亡時効果、状態/params更新の忠実度がスタブより高い。DB保存は `save_specific_room_state` 差し替えで止める |
| 2026-07-11 | 味方AIの方式 | `battle_ai.ai_suggest_skill(char)` と最小ターゲットポリシーの薄いラッパをシミュレータ側に実装する | 既存plannerは敵専用。Phase 1-2ではビルド別 behavior_profile までは不要 |
| 2026-07-11 | 中央値ロール | 期待値の四捨五入（`.5` は切り上げ）を `median` とする | 低/中/高を1本ずつ出す用途では読みやすさを優先。floor/ceil併走は必要になった時点で拡張する |
| 2026-07-11 | 膠着判定 | `max_rounds` 到達を基本とし、将来 `stall_window` とHP減少閾値を追加できる形にする | Phase 1-2では決着ループの安全停止が最重要。HP減少率はレポート整形時に追加する |
| 2026-07-11 | 出力形式 | CLIはコンソール表を既定、`--json` で機械可読出力を追加する | GMの手元確認とpytest利用の両方を満たす。MarkdownはPhase 4以降の任意拡張 |
| 2026-07-11 | CI組込 | Phase 1-4は個別テストのみ、Phase 5で軽量代表ケースだけ通常 `pytest -q` に含める | 実行時間と決定論性を確認してから常時実行にする |

## 9. 実装準備メモ（2026-07-11）

Phase 1 の最小実装は、次の順で進める。

1. `scripts/simulate_battle.py` に `BattleReport` と `run_battle(state, *, roll_mode="median", max_rounds=10)` を置く。
2. `get_room_state` / `save_specific_room_state` / `socketio.emit` / `broadcast_log` を、`manager.battle.core` と `manager.battle.common_manager` の両方で差し替える。
3. `_update_char_stat` は実実装を呼ぶ。ただし保存・emit・ログ送信は no-op に差し替え、DB/Socket へ出さない。
4. 1ラウンドは `process_select_resolve_round_start` → 味方intent注入 → `phase="resolve_mass"` → `run_select_resolve_auto` → 全員 `hasActed=True` 補正 → `process_full_round_end` → `_bo_estimate_battle_result` の順に回す。
5. Phase 1 テストは手書き 1vs1 または 2vs2 の固定intentで、決着・上限打ち切り・既存エンジン本体未変更を確認する。

注意点:

- `process_full_round_end` は未行動キャラがいると止まるため、シミュレータでは resolve 後に生存・行動可能キャラの `hasActed` を補正する。
- `roll_dice` 差し替えは Phase 2 で追加する。Phase 1 は既存乱数または固定スキル威力スタブで完走確認に絞る。
- `extensions.all_skill_data` には実キャッシュを投入する。テストでは必要最小のスキルだけを `all_skill_data` に差し込む。

## 10. 受け入れ条件

- 実プリセット（または手書き編成JSON）を入力に、低/中/高ロールの3シナリオで決着ラウンド・勝敗・残HPが再現可能に出力される。
- 膠着編成が上限で打ち切られ「詰み」として報告される。
- 戦闘エンジン本体のコードに変更がない（monkeypatch/注入のみ）。
- 既存テスト全通過。シミュレータ自体のテストが `pytest -q` に含まれても所要時間が許容範囲（目安: 追加30秒以内）。
- F02 の遭遇チェックリストのうち「低/中/高ロールの撃破ターン」「詰みの有無」が本ツールで機械検証できる旨を F02 に追記。
