# 15. Random Target Skill Plan

**最終更新日**: 2026-04-19  
**対象バージョン**: Current  
**対象機能**: ランダムターゲット技（敵味方含む）

---

## 1. 目的
- Select/Resolve の宣言から「対象未確定のランダム単体技」を安全に扱う。

---

## 2. 現状
### 2.1 実装済み
- 効果解決レイヤ (`process_skill_effects`) に `target_select=RANDOM` がある
- `target_filter` により ENEMY/ALLY/ALL の抽選は可能

### 2.2 未実装
- Select/Resolve の target.type として `random_single` が未対応
- 宣言時未確定 -> 実行直前確定の導線がない

---

## 3. 実装方針
### 3.1 宣言形式
- intent で `target.type = "random_single"` を許可
- スキル定義で `random_target_scope`（`enemy`/`ally`/`any`）を参照

### 3.2 確定タイミング
- resolve直前に候補（生存・配置済み・scope一致）から抽選
- 抽選後、intent を `single_slot` に確定して既存処理に流す

### 3.3 初期制約
- 初回は `no_redirect=true` を推奨（redirect衝突回避）

---

## 4. 実装タスク
1. target normalizer に `random_single` 追加
2. resolve前抽選処理追加
3. ログとトレースに「抽選結果」を表示

---

## 5. テスト観点
- scope=`any` で敵味方から抽選される
- 対象不在時の失敗メッセージが明確
- redirect 系との衝突が起きない

