# AI Prompt Pack: JSON定義マニュアル（Typst化用）

以下を他AIチャットへそのまま貼り付けて使える。

---

あなたはTypstドキュメント作成者です。  
`manuals/implemented/15_JSON_Definition_Master.md` を唯一の仕様ソースとして、  
「スキル定義・バフ定義JSONの統合マニュアル」を **Typst 1ファイル** で生成してください。

## 出力要件

1. 出力は `typ` コードのみ（説明文なし）
2. 章立ては次を含む:
   - 目的
   - Source of Truth
   - Skill本体スキーマ
   - rule_dataトップレベル
   - effects共通仕様
   - condition仕様
   - Effect Type別仕様
   - tags/target_scope
   - cost/power_bonus
   - Buff定義
   - 動的バフ命名規則
   - 参照整合ルール
   - CUSTOM_EFFECT一覧
   - バフプラグインID対応
   - CSV列名マップ
   - 実運用チェック
3. `effect.type`, `timing`, `target` は `15_JSON_Definition_Master.md` にある値以外を追加しない
4. 表形式を多用し、最低でも以下の表を作る:
   - Effect Typeと必須キー
   - timing一覧
   - target一覧
   - CSV列名マップ
5. JSON例を3つ以上載せる:
   - 最小rule_data
   - APPLY_STATE例
   - APPLY_BUFF + buff_id例
6. 末尾にチェックリストを入れる:
   - 参照整合チェック
   - pytestコマンド
7. 日本語で記述する

## 禁止

- 仕様にないeffect typeの創作
- 仕様にないtiming/targetの創作
- 「推測」「たぶん」など曖昧記述

---

補助入力として必要なら次も参照可:

- `manuals/implemented/16_Manual_Update_Protocol_and_Feature_Roadmap.md`

