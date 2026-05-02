# manuals フォルダ運用ガイド

**最終更新日**: 2026-03-30  
**方針**: 実装済み仕様は `implemented/`、未着手または検討中は `planned/` に分離する。

## 1. まず読む順番（推奨）

### 1.1 プレイヤー向け
1. `implemented/01_Integrated_Player_Manual.md`
2. `implemented/10_Glossary_User_Tutorial.md`
3. 必要に応じて `implemented/04_Character_Build_Guide.md`

### 1.2 GM運用向け
1. `implemented/02_Integrated_GM_Creator_Manual.md`
2. `implemented/14_GM_Buff_Item_Operations_Spec.md`
3. `implemented/09_SelectResolve_Spec.md`
4. PvE運用時のみ `implemented/05_PvE_Mode_Spec.md`

### 1.3 データ定義・拡張実装向け
1. `implemented/20_JSON_Definition_Strict_v2_Manual.md`（現行正本）
2. `implemented/17_Phase3_Strict_Errata.md`（旧資料の読み替え）
3. `implemented/08_Skill_Logic_Reference.md`
4. `implemented/11_Advanced_Skill_Extensions_Spec.md`

## 2. implemented の役割整理

- `01`〜`02`: 利用者向けの統合手順（PL/GM）
- `20`: JSON定義の現行正本仕様（Phase3 strict）
- `04`〜`05`: 運用ガイド（ビルド・PvE）
- `06`〜`09`: 戦闘表示/フロー仕様
- `10`: 用語・データ入力チュートリアル
- `11`〜`13`: 拡張仕様（上級）
- `14`: GMバフ/アイテム運用の実装済み確定仕様
- `17`: 戦闘専用プレイモード（battle_only）の実装済み運用仕様

## 3. planned の読み方

- `planned/` は「未実装タスクのみ」を置く。
- 実装完了した計画は詳細を `implemented/` へ移設し、`planned/` 側には残課題または移設先リンクのみを残す。
- 仕様調査の起点は `planned/06_Integrated_Implementation_Roadmap.md` を先頭にする。

## 4. 今回の再編方針（2026-03-30）

- GMバフ/デバフ付与・解除、アイテム付与/没収、認可強化（Phase A/B/C）の確定内容を `implemented/14_GM_Buff_Item_Operations_Spec.md` へ集約。
- `planned/07_GM_Buff_Item_Operation_Implementation_Plan.md` は実装済み確認後に削除した。
- `planned/04_TRPG_Session_Improvement_Feasibility_Plan.md` は未完了の追跡事項のみ保持する。

## 5. Planned 追記（2026-05-02）
- `planned/23_自然言語JSON生成_3列入力運用仕様案.md`
  - スプレッドシート3列（使用時効果 / 発動時効果 / 特記）から `skill_json_rule_v2` JSONを生成する運用案。
  - timing辞書、文分割ルール、曖昧時エラー停止、strict出力方針を定義。
