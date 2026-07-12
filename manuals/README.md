# manuals フォルダ運用ガイド

最終更新: 2026-06-28

このディレクトリは以下の系統で管理します。
- `implemented/`: 実装済み仕様の正本
- `planned/`: 未実装・検討中の計画
- `operations/`: 運用・デプロイ手順書（例: `account_system_deploy_runbook.md`）
- `typst/`: 上記MD文書のTypst（PDF）版。共有テーマ `typst/lib/theme.typ`。詳細は `typst/README.md`

---

## 1. ファイル体系（implemented/）

### 系統別ファイル一覧

| ファイル | 内容 |
|---|---|
| **A — ユーザーガイド** | |
| `A01_Player_Manual.md` | プレイヤー向け操作マニュアル |
| `A02_GM_Creator_Manual.md` | GM・管理者向け運用マニュアル |
| `A03_Character_Build_Guide.md` | キャラクタービルド作例集 |
| `A04_Glossary_Tutorial.md` | 用語図鑑機能チュートリアル |
| **B — 戦闘・スキル仕様** | |
| `B01_Skill_Logic_Core.md` | スキルロジック実装リファレンス Part1（effect処理・条件・亀裂） |
| `B02_Skill_Logic_Extensions.md` | スキルロジック実装リファレンス Part2（GRANT_SKILL/召喚/フォールバック/Variant） |
| `B03_SelectResolve_Spec.md` | Select/Resolve 確定仕様書 |
| **C — データ定義（JSON）** | |
| `C01_JSON_Definition_Master.md` | JSON定義マニュアル（正本・統合版） |
| **D — プレイモード仕様** | |
| `D01_Play_Mode_Specs.md` | PvEモード・戦闘専用モード・ステージ効果仕様書 |
| **E — UI / フロントエンド** | |
| `E01_Visual_Battle_Architecture.md` | ビジュアルバトル アーキテクチャ仕様書 |
| `E02_UI_Component_Specs.md` | UIコンポーネント仕様書（モーダル・プリセット・ステータス編集） |
| **F — 運用** | |
| `F01_Operations_Manual.md` | 運用マニュアル（GMバフ操作・マニュアル更新プロトコル・デプロイ手順・アカウント認証・ルーム権限システム仕様） |
| `F02_Battle_Balance_Designer_Skill_Manual.md` | バランス設計 Skill 運用・スキルバランス確定基準・スキル/遭遇設計ガイド（GM・作成者向け） |
| `F03_Battle_Balance_Simulator_CLI.md` | バランス検証シミュレータCLI・ヘッドレス検証ワークフロー |

---

## 2. まず読む順番

### JSON定義・スキル仕様
1. `C01_JSON_Definition_Master.md`（現行正本）
2. `B01_Skill_Logic_Core.md`（effect処理・条件判定の実装詳細）
3. `B02_Skill_Logic_Extensions.md`（拡張機能）

### 戦闘進行仕様
1. `B03_SelectResolve_Spec.md`
2. `D01_Play_Mode_Specs.md`（PvE/戦闘専用モード）

### デプロイ・運用
1. `F01_Operations_Manual.md`

### UI・フロントエンド
1. `E01_Visual_Battle_Architecture.md`
2. `E02_UI_Component_Specs.md`

---

## 3. ドキュメント更新ルール

**implemented/ は A〜F 系統ファイルで管理する。**

- 新しい実装済み仕様を追加するときは、内容に合った既存の系統ファイル（A01〜F01 等）の末尾に節を追加する。
- `implemented/` に番号付きファイル（例: `26_xxx.md`）を新規作成しない。
- `planned/` は未実装・検討中のみを置く。
- 実装完了した計画書は削除し、必要事項を既存の系統ファイルへ統合する。

どの系統に追加するか迷ったときの目安:

| 内容 | 追加先 |
|---|---|
| ユーザー・GM 向け操作手順 | A01 / A02 |
| キャラクタービルド・作例 | A03 |
| スキル・バフ・effect ロジック | B01 / B02 |
| JSON データ定義 | C01 |
| プレイモード・PvE 仕様 | D01 |
| UI コンポーネント・フロントアーキテクチャ | E01 / E02 |
| デプロイ・運用・権限・認証仕様 | F01 |

---

## 4. 今回の整理（2026-05-09）
旧 25 ファイル（数字番号体系）を 12 ファイル（アルファベット+連番体系）へ統合整理。

| 旧ファイル（削除済み） | 移管先 |
|---|---|
| 01_Integrated_Player_Manual | A01 |
| 02_Integrated_GM_Creator_Manual | A02 |
| 03_Integrated_Data_Definitions | C01 |
| 04_Character_Build_Guide | A03 |
| 05_PvE_Mode_Spec | D01 Part1 |
| 06_Visual_Battle_Architecture | E01 |
| 07_Visual_Battle_Code_Spec | E01 補足 |
| 08_Skill_Logic_Reference | B01 |
| 09_SelectResolve_Spec | B03 |
| 10_Glossary_User_Tutorial | A04 |
| 11_Advanced_Skill_Extensions_Spec | B02 |
| 12_Character_Modal_Spec | E02 Part1 |
| 13_Fissure_Round_Management_Spec | B01（亀裂統合） |
| 14_GM_Buff_Item_Operations_Spec | F01 Part1 |
| 15_JSON_Definition_Master | C01 |
| 16_Manual_Update_Protocol | F01 Part2 |
| 17_Battle_Only_Play_Mode_Spec | D01 Part2 |
| 17_Phase3_Strict_Errata | C01 |
| 18_Stage_Field_Effect_Spec | D01 Part3 |
| 19_Fallback_Struggle_Spec | B02 |
| 20_JSON_Definition_Strict_v2_Manual | C01（正本） |
| 21_Render_Deploy_Operations | F01 Part3 |
| 22_Special_Stack_Resource_Variants | B02 |
| 23_Preset_Stage_UI_Operation_Update | E02 Part2 |
| 24_Quick_Edit_and_UI_Consistency_Summary | E02 Part3 |

---

## 5. 計画策定プロセス

新機能・UI刷新など実装前に方針決定が必要な場面では、一問一答形式の議論で方針を固める方法を採用している。

詳細: [`planning_process.md`](planning_process.md)
