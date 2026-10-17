# はじめに読むマニュアル

最終更新: 2026-09-16

このページはローカルの仕様・操作資料を読むための内部案内です。外部向けには基本ルールブックと操作ガイドをPDFで構成します。[出版構成案（計画46 §13）](planned/46_Manual_Restructuring_Plan.md#13-出版構成案2026-09-15)を参照してください。

今やりたいことに合わせて、以下の順に読んでください。ゲームのルールと世界観は[卓上ルール本](../typst_manual/全体マニュアル/README.md)、アプリの操作は各操作マニュアルで確認できます。

## プレイヤー：参加して遊ぶ

1. [A01 プレイヤー編](implemented/A01_Player_Manual.md)：始める前に（ログイン・入室）、キャラクターを用意する、画面を読む、戦闘・探索を操作する、セッションの後、の順に並んでいます。
2. 持ちキャラの作成・保存・ルームへの追加は、同書の[2. キャラクターを用意する](implemented/A01_Player_Manual.md#2-キャラクターを用意する)を確認してください。
3. ルールを知りたい場合は、[卓上ルール本](../typst_manual/全体マニュアル/README.md)の第一章「ゲームシステム」へ。世界観は第二章です。

必要になったら：[A03 キャラクタービルド作例](implemented/A03_Character_Build_Guide.md)、[A04 用語図鑑の使い方](implemented/A04_Glossary_Tutorial.md)。

A01は2026-10-17に章立てを再編し、日付付きの追補を本文へ統合しました。ルールの説明は卓上ルール本を正とし、A01には操作と画面の見え方を載せています。

## GM：卓を準備・進行する

1. [A02 GM編](implemented/A02_GM_Creator_Manual.md)の「GM権限とルーム管理」で参加コード、GM PIN、配置を確認します。
2. 通常ルームでは、同書の[戦闘突入・戦闘終結](implemented/A02_GM_Creator_Manual.md#追補2026-09-08-通常ルームの戦闘突入戦闘終結)を先に読みます。戦闘専用モードとは開始手順が異なります。
3. 同書の「GM向け解決フェーズ運用」で解決表示の進行、「プレイヤーの持ちキャラへの成果反映」で終了後の操作を確認します。

裁定は[卓上ルール本](../typst_manual/全体マニュアル/README.md)の第一章、バフ・アイテム介入や画像操作は[F01](implemented/F01_Operations_Manual.md)のPart 1・Part 1-Cを参照してください。F01後半のサーバー運用手順を通読する必要はありません。

## 制作者：敵・編成・シナリオを作る

1. [A02](implemented/A02_GM_Creator_Manual.md)の「敵行動チャート」「戦闘専用プリセット管理」「シナリオ用プリセットを別環境へ移す」を読みます。
2. 詳しい挙動は[D01 プレイモード仕様](implemented/D01_Play_Mode_Specs.md)、編集画面は[E02 UI仕様](implemented/E02_UI_Component_Specs.md)で確認します。
3. 設計・検証が必要なら[F02 バランス設計](implemented/F02_Battle_Balance_Designer_Skill_Manual.md)、[F03 シミュレータCLI](implemented/F03_Battle_Balance_Simulator_CLI.md)へ進みます。F02のSkill利用部分とF03は開発環境を使う人向けです。

JSON・シート定義を扱う場合のみ、[C01 JSON定義](implemented/C01_JSON_Definition_Master.md)と[C02 被弾反応パッシブ仕様・記入例](implemented/C02_Retaliation_Passive_Sheet_Examples.md)を参照してください。

外部協力者向けの専用制作ガイドは未整備です。[計画45](planned/45_External_Contribution_Program_Plan.md)は今後の文書・運用案であり、受付開始の案内ではありません。

## 開発者・AI：実装を調べる

1. [AGENTS.md](../AGENTS.md)と[CONTRIBUTING.md](../CONTRIBUTING.md)で開発規約を確認します。
2. [文書一覧](README.md)から対象仕様へ進みます。戦闘進行は[B03](implemented/B03_SelectResolve_Spec.md)、効果処理は[B01](implemented/B01_Skill_Logic_Core.md)・[B02](implemented/B02_Skill_Logic_Extensions.md)、画面構成は[E01](implemented/E01_Visual_Battle_Architecture.md)です。
3. [テスト案内](test_manuals/README.md)で関連する確認項目を選びます。新しい計画の整理は[計画策定プロセス](planning_process.md)を参照してください。

## アプリ管理者：管理・運用する

アカウント・権限・保存・デプロイは[F01 運用マニュアル](implemented/F01_Operations_Manual.md)、認証機能の導入確認は[デプロイ手順書](operations/account_system_deploy_runbook.md)へ進んでください。ルームのGMとアプリ管理者は異なる権限です。

## 文書の版と再編状況

- 卓上ルール本の編集元・PDFの区別は[ルール本の案内](../typst_manual/全体マニュアル/README.md)に記載しています。
- 操作・実装仕様はMarkdown、`manuals/typst/`はその整形版です。個別スキル等の数値はルール本の案内にあるマスターデータの扱いも確認してください。
- A01・A02の本文訂正と追補統合、読者向け変更履歴は今後の作業です。[計画46](planned/46_Manual_Restructuring_Plan.md)で進捗を管理しています。
