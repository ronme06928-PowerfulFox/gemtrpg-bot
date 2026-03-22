# manuals フォルダ運用ルール

`manuals` 配下は、文書の役割ごとに次の 2 系統で管理します。

- `implemented/`: 現在の実装・運用に対して参照するマニュアル群
- `planned/`: これから実装する内容や改善案、実装手順、ロードマップをまとめる計画書群

番号は各フォルダ内で独立して採番します。新規文書を追加する場合も、`implemented` と `planned` をまたいで通し番号にはしません。

## implemented

1. `01_Integrated_Player_Manual.md`
2. `02_Integrated_GM_Creator_Manual.md`
3. `03_Integrated_Data_Definitions.md`
4. `04_Character_Build_Guide.md`
5. `05_PvE_Mode_Spec.md`
6. `06_Visual_Battle_Architecture.md`
7. `07_Visual_Battle_Code_Spec.md`
8. `08_Skill_Logic_Reference.md`
9. `09_SelectResolve_Spec.md`
10. `10_Glossary_User_Tutorial.md`
11. `11_Advanced_Skill_Extensions_Spec.md`
12. `12_Character_Modal_Spec.md`

## planned

1. `03_New_Skill_Ideas_Feasibility_Plan.md`
2. `04_TRPG_Session_Improvement_Feasibility_Plan.md`
3. `05_Shindou_Skill_Implementation_and_Documentation_Protocol.md`
4. `06_Integrated_Implementation_Roadmap.md`
5. `09_Status_Stack_Total_Effects_Plan.md`
6. `10_Faction_Terminology_Alignment_Plan.md`

`typst/` は文書出力用の共通アセットとしてそのまま `manuals` 直下に置きます。
