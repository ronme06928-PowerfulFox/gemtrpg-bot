# 16_Hard_Feint_Skill_Tag_Feasibility.md

更新日: 2026-02-25  
対象: Select/Resolve 戦闘処理（`manager/battle/core.py` / `manager/battle/common_manager.py` / `static/js/battle/components/ResolveFlowPanel.js`）

## 1. 結論

- `強硬スキル` は **実装可能（中）**。  
  既存の `one_sided` 解決・`evade_insert`・`-EX` 表示の土台を流用できるが、  
  「敗北後に専用追撃」「最終威力=基礎威力固定」「発火タイミング制御（LOSE/HITのみ）」の追加実装が必要。
- `牽制スキル` は **実装可能（中〜高）**。  
  「強硬攻撃の不発化」は実装しやすい。  
  一方で「通常スキル勝利時ダメージ半減」は、現行が duel delegate 内で確定ダメージまで処理するため、`duel_solver.py` 側の分岐追加が必要。

---

## 2. 現状実装で流用できる要素

### 2.1 一方攻撃（one-sided）基盤

- `run_select_resolve_auto` の single 解決で `one_sided` 分岐が存在し、`_resolve_one_sided_by_existing_logic(...)` に委譲される。
- 同関数内で `PRE_MATCH -> BEFORE_POWER_ROLL -> UNOPPOSED -> HIT -> AFTER_DAMAGE_APPLY` を実行。
- 既存仕様上、one-sided は「一方攻撃時効果（UNOPPOSED）」を自動発火する。

参照:
- `manager/battle/core.py`  
  - `run_select_resolve_auto` の `resolve_single` 分岐  
  - `_resolve_one_sided_by_existing_logic`

### 2.2 回避差し込み（再回避）基盤

- `select_evade_insert_slot(...)` が存在し、条件成立時に one-sided を clash へ昇格できる。
- 現在の主条件は `is_dodge_lock_active(...)`（再回避ロック状態）で、`evade_insert` trace を積んでから clash 実行する。

参照:
- `manager/battle/common_manager.py`  
  - `select_evade_insert_slot`  
  - `is_dodge_lock_active` / `_is_evade_skill`
- `manager/battle/core.py`  
  - `resolve_single` 内の `evade_insert` 処理

### 2.3 `#n-EX` 表示基盤

- 仮想再使用スロットは `__EX1`, `__EX2` で作成され、表示ラベルは `n-EX`, `n-EX2` を自動生成。
- UI側も `slotId.includes('__EX')` と `-EX` ラベルを再使用ステップとして認識済み。

参照:
- `manager/battle/core.py`  
  - `_schedule_single_reuse_slot`  
  - `_resolve_reuse_display_label`
- `static/js/battle/components/ResolveFlowPanel.js`  
  - `_isReuseStep`

---

## 3. 要件別の実装可否と不足点

### 3.1 強硬スキル: 「通常スキルとのマッチ敗北時に強硬攻撃へ移行」

可否: **可能**

不足点:
- clash 後に「敗者のタグ判定 -> 追撃予約」を行う処理は未実装。
- 現在の再使用は `USE_SKILL_AGAIN` 起点で勝者側からしか積まない設計。

実装案（最小）:
- `resolve_single` の clash 解決直後で、
  - 敗者スキルが `強硬スキル` タグ
  - 勝者スキルが `通常スキル`（= 強硬でない）
  を満たす場合、敗者スロット起点の「強硬追撃用 仮想スロット」を1回だけ差し込む。

### 3.2 強硬スキル: 「最終威力は基礎威力と同じ」

可否: **可能**

不足点:
- 既存 one-sided は `roll_dice(final_command)` の結果を最終威力として使うため、そのままでは要件不一致。

実装案:
- 強硬追撃専用ヘルパー（例: `_resolve_hard_attack_followup(...)`）を追加し、  
  `calculate_skill_preview(...).power_breakdown.final_base_power` を基準ダメージとして採用。
- ここで `UNOPPOSED` は実行しない（後述 3.3）。

### 3.3 強硬スキル: 「敗北時効果と的中時効果は発動、勝利時/一方攻撃時は発動しない」

可否: **可能**

不足点:
- 既存 one-sided は `UNOPPOSED + HIT` を発火するため、要件とズレる。

実装案:
- 強硬追撃専用ヘルパーで `process_skill_effects` を
  - `LOSE`
  - `HIT`
  のみ実行し、`WIN` と `UNOPPOSED` は呼ばない。
- 仕様上の名称として「強硬攻撃時」を導入する場合、  
  将来拡張として `timing: HARD_ATTACK` を追加してもよい（この場合は lint 更新が必要）。

### 3.4 強硬スキル: 「相手に未使用回避スキル/再回避状態があれば回避マッチ」

可否: **可能（中）**

不足点:
- 現行の `select_evade_insert_slot` は再回避ロック（`Bu-05` 系）前提で、  
  「未使用の回避スロットがあるだけ」のケースを標準で拾わない。

実装案:
- 強硬追撃専用の差し込み判定を追加し、以下の優先順で防御スロットを選ぶ。  
  1. 強硬追撃対象を明示 target している回避スロット  
  2. 未解決の回避スロット（同キャラ内で initiative 最大）  
  3. 再回避状態なら解決済みスロット再利用

### 3.5 強硬スキル: 「UI表示は強硬攻撃（回避マッチ時も）」

可否: **可能**

不足点:
- 現在の UI 種別は `clash` / `one_sided` など固定マップ。

実装案:
- trace に `kind='hard_attack'`（または `is_hard_attack=true`）を追加。
- `ResolveFlowPanel._kindLabel` に `hard_attack: 強硬攻撃` を追加。
- 回避マッチになった場合も trace kind を `hard_attack` で統一する。

### 3.6 牽制スキル: 「強硬スキル相手に勝利時、強硬攻撃を不発」

可否: **可能（高）**

実装案:
- clash 解決直後、勝者スキルに `牽制スキル` タグがある場合は `hard_followup` の差し込みを抑止。
- 仕様用語「牽制成功時」は、内部的には「clash勝利 + 相手が強硬 + 自分が牽制」で判定可能。

### 3.7 牽制スキル: 「通常スキル相手に勝利時、与ダメージ半減」

可否: **可能（中）**

不足点:
- clash ダメージは `duel_solver.execute_duel_match(...)` 委譲中に確定するため、  
  `core.py` 側で事後半減すると副作用（追加効果・ログ）不整合が出やすい。

実装案:
- `manager/battle/duel_solver.py` の勝敗分岐（攻撃側勝利/防御側勝利）内に、  
  `winner has 牽制` かつ `loser is 通常` の条件で `final_damage = floor(final_damage / 2)` を追加。
- 併せてログ文言に「牽制半減」を追記。

---

## 4. 影響ファイル（見込み）

- `manager/battle/core.py`
  - clash 後の強硬追撃予約
  - 強硬追撃専用解決ヘルパー
  - trace への `hard_attack` 表示情報追加
- `manager/battle/common_manager.py`
  - 強硬追撃向け回避差し込み選定（既存関数拡張または新関数）
- `manager/battle/duel_solver.py`
  - 牽制勝利時の通常相手ダメージ半減
- `events/battle/common_routes.py` / `manager/battle/common_manager.py`
  - （任意）intent tags へ `hard_skill` / `feint_skill` を追加
- `static/js/battle/components/ResolveFlowPanel.js`
  - `hard_attack` の表示ラベル・見出し調整
- `tests/test_select_resolve_smoke.py`
  - 強硬追撃発生、回避差し込み、`-EX` 表示、牽制による不発
- `tests/test_match_integraton.py` ほか
  - 牽制ダメージ半減の clash 回帰

---

## 5. 実装順（推奨）

1. 強硬追撃の最小版（敗北後1回差し込み、LOSE/HITのみ、基礎威力固定）
2. 強硬追撃の回避差し込み（未使用回避 + 再回避）
3. UI表示を `強硬攻撃` に統一
4. 牽制の強硬不発化
5. 牽制ダメージ半減（duel_solver）
6. 仕様確定後に `manuals/03_Integrated_Data_Definitions.md` と `manuals/07_Skill_Logic_Reference.md` へ統合

---

## 6. 補足（設計上の注意）

- 既存の `USE_SKILL_AGAIN` と強硬追撃は概念が近いが、  
  発火条件・威力式・タイミングが異なるため、内部フラグを分ける方が安全。
- 新しい effect timing 名（例: `HARD_ATTACK`, `FEINT_SUCCESS`）をデータに追加する場合、  
  `tests/test_skill_catalog_smoke.py` の `SUPPORTED_EFFECT_TIMINGS` 更新が必要。
- 「通常スキル」の厳密定義（強硬/牽制/広域/守備を含むか）は先に固定した方が、  
  分岐の曖昧さとテストコストを下げられる。
