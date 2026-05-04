# manuals フォルダ運用ガイド

最終更新: 2026-05-05

このディレクトリは以下の2系統で管理します。
- `implemented/`: 実装済み仕様の正本
- `planned/`: 未実装・検討中の計画

---

## 1. まず読む順番

### 1.1 JSON定義・スキル仕様
1. `implemented/20_JSON_Definition_Strict_v2_Manual.md`（現行正本）
2. `implemented/17_Phase3_Strict_Errata.md`（補遺）
3. `implemented/15_JSON_Definition_Master.md`（運用版要約）

### 1.2 デプロイ運用
1. `implemented/21_Render_Deploy_Operations_JSON_V2.md`

### 1.3 バトル全体仕様
1. `implemented/08_Skill_Logic_Reference.md`
2. `implemented/09_SelectResolve_Spec.md`
3. `implemented/11_Advanced_Skill_Extensions_Spec.md`

---

## 2. implemented の位置づけ
- `20`: JSON定義の正本（Phase3 strict v2）
- `21`: Render本番デプロイの運用記録・ロールバック要点
- `15`: 現場向けの短縮版マスター
- `17`: strict運用での差分補足

---

## 3. planned の位置づけ
- `planned/` は未実装・検討中のみを置く。
- 実装完了した計画書は削除し、必要事項を `implemented/` へ移管する。

---

## 4. 今回の整理（2026-05-02）
実装済みのため `planned` から削除:
- `20_Phase3_旧形式廃止_移行準備計画.md`
- `21_Phase3_完了判定チェックリスト.md`
- `23_自然言語JSON生成_3列入力運用仕様案.md`
- `24_Render_Deploy_Checklist_JSON_V2.md`

移管先:
- JSON定義・自然言語生成運用: `implemented/20`
- デプロイ運用: `implemented/21`

## 5. 今回の整理（2026-05-05）
実装済みのため `planned` から削除:
- `09_Status_Stack_Total_Effects_Plan.md`

移管先:
- JSON strict定義（状態異常スタック合計 / APPLY_BUFF_PER_N）: `implemented/20`
- 運用向けJSON要約: `implemented/15`
- 実行ロジック仕様: `implemented/08`
- 統合データ定義: `implemented/03`
