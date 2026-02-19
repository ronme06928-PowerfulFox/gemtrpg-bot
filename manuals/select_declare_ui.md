# Select/Declare UI 改善計画（現実装照合版）

最終更新: 2026-02-19
対象: Select フェーズの宣言 UI（slot クリック導線、DeclarePanel、ホバー情報、再宣言制御）

---

## 0. この版で書き換えた必要箇所

- 既存実装済みの項目と未実装項目を分離し、実作業対象を明確化。
- 「サーバで権限担保済み」という前提を削除し、別チケット化を明記。
- 実装順を P0/P1/P2 に整理し、先に着手すべき項目を固定。

---

## 1. 現状実装確認サマリ（2026-02-19）

### 1.1 既に実装済み
- slot クリックで `source -> target` の状態遷移そのものは実装済み（`mode: idle/choose_target/ready`）。
- committed slot クリック時の再編集モード遷移は実装済み。
- close で draft を破棄（`resetDeclare`）する挙動は実装済み。
- timeline は折りたたみ機構自体は実装済み（ヘッダクリック + `localStorage`）。

### 1.2 部分実装（改善が必要）
- 2クリック導線: 状態遷移はあるが、DeclarePanel は source 選択時点で表示されるため「圧迫軽減」の要件を満たしていない。
- 再宣言ボタン: skill/target の入力可否で有効化されており、`committed vs draft` 差分では制御していない。

### 1.3 未実装
- 差分1行表示（`skill: A -> B` / `target: X -> Y`）。
- slot ダブルクリックで DeclarePanel を直開きする導線。
- committed intent を元にした最小ホバーサマリ（現状は draft 側の選択スキルに寄る）。

### 1.4 サーバ権限前提の補正
- `battle_intent_preview/commit/uncommit` は現状、slot 所有者/GM の厳密検証が未実装。
- したがって UI 側の disabled は UX 上の制御であり、セキュリティ担保は別タスクでサーバ追加が必要。
- 本計画では UI 改修を先行し、サーバ権限強化は別 PR として扱う。

---

## 2. 目的

- 宣言フェーズの視認性を改善し、操作を段階化する。
- 「変更したつもり」「確定したつもり」のズレを、差分表示とボタン制御で減らす。
- 既存の `BattleStore.declare` / `state.intents` / socket イベントを活かし、最小差分で実装する。

---

## 3. 非目的（今回やらない）

- 戦闘ルール本体（ダメージ式、効果、ターゲット制約）の変更。
- Resolve フェーズ UI の再設計。
- 権限モデルの全面刷新（別タスクで段階実施）。

---

## 4. 実装方針（合理化）

- 既存ロジックを壊さず、表示条件と比較ロジックを先に整える。
- まず P0（差分判定 + 再宣言制御 + 表示条件）を完了させる。
- dblclick/hover/timeline は P1/P2 として分離し、回帰を局所化する。

---

## 5. 優先度付きタスク

### P0（必須）
1. `committed intent` と `draft declare` の差分比較関数を追加。
2. DeclarePanel に差分1行を追加（差分がある時のみ表示）。
3. 再宣言ボタンを「差分あり」の時だけ有効化。
4. DeclarePanel 表示条件を調整。
- single: `source + target` が揃うまで出さない。
- mass: source のみで表示可。

### P1（推奨）
1. slot ダブルクリックで DeclarePanel を直開き（source セット）。
2. committed slot hover で `skill_id / skill名 / 対象` の最小サマリ表示。

### P2（任意）
1. timeline を Select 開始時に既定で折りたたむかを調整。
- 既存トグル実装は維持。デフォルト方針のみ決める。

### 別チケット（サーバ）
1. `battle_intent_preview/commit/uncommit` に所有者/GM 権限チェックを追加。
2. 権限拒否時のエラーコードと UI 復帰仕様を固定。

---

## 6. 受け入れ条件（Acceptance Criteria）

### AC-1 表示圧迫改善
- single 対象スキルでは source 1回目クリックだけでパネルが出ない。

### AC-2 差分表示
- `committed == draft` のとき差分行は非表示。
- `skill` または `target` が変わると 1行差分を表示。

### AC-3 再宣言ボタン
- 差分なし: disabled。
- 差分ありかつ必須入力充足: enabled。

### AC-4 破棄挙動
- 閉じるで draft 破棄。再オープン時は committed 基準で表示。

### AC-5 ダブルクリック（P1）
- slot を dblclick で source セット + パネル表示（single で target 未選択時は誘導文のみ）。

### AC-6 ホバー（P1）
- committed slot hover で `skill_id / skill名 / 対象` を表示。
- 欠損データでも UI が壊れない。

### AC-7 権限（現段階）
- UI 上で権限なし操作は抑止する。
- ただし最終担保は別チケットのサーバ実装に委譲。

---

## 7. 実装手順（最小差分順）

### Step 1: 差分比較ユーティリティ
- `hasDiff` と `diffSummary` を返す関数を追加。
- 比較対象は `skill_id`, `target(type+slot_id)`, 必要なら `mode`。

### Step 2: DeclarePanel の再宣言制御
- Step 1 の結果を使って差分1行表示。
- commit ボタン活性条件に `hasDiff` を追加。

### Step 3: DeclarePanel 表示条件の調整
- single: target 未選択時は非表示または最小誘導のみ。
- mass: source のみで表示可能。

### Step 4: dblclick 導線追加（P1）
- slot-badge の dblclick で source をセット。
- 既存の token dblclick（詳細表示）との競合を避ける。

### Step 5: hover サマリ追加（P1）
- title 生成を `declare.skillId` 依存から `intents[slotId]` 依存へ変更。

### Step 6: timeline 既定表示調整（P2任意）
- 必要なら Select 開始時に collapsed を既定化。

### Step 7: サーバ権限強化（別PR）
- ここでは TODO として明記し、UI 改修とは分離。

---

## 8. 主変更候補ファイル

- `static/js/battle/components/DeclarePanel.js`
- `static/js/visual/visual_map.js`
- `static/js/battle/core/BattleStore.js`（比較関数を置く場合）
- `static/js/visual/visual_ui.js`（timeline 既定値を触る場合）
- `events/battle/common_routes.py`（別チケット: 権限検証）

---

## 9. 手動テスト観点

- single skill: source クリックのみではパネル非表示、target クリック後に表示。
- committed の skill/target 変更で差分1行が出る。
- 差分なしで再宣言ボタンが押せない。
- 差分ありで再宣言ボタンが押せる。
- close 後に再オープンすると未確定変更が残らない。
- dblclick でパネルを開いても click 導線が破綻しない。
- hover サマリが欠損データで落ちない。

---

## 10. 作業可能性の結論

- 現在の実装基盤で、この計画は実施可能。
- ただし「サーバ側が権限を担保済み」という前提は現状不正確なため、本書の通り別チケット化して進める。
- 以降の実装は本書の P0 から開始する。
