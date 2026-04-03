# 11 スキルID埋め込みリンク実装マニュアル

**作成日**: 2026-03-31
**対象**: スキル効果説明・バフ説明などのテキスト内にスキルIDリンクを埋め込み、クリックで「キャラクター詳細と同等のスキル説明モーダル」を表示する機能
**位置づけ**: 実装前の仕様合意用（planned）

---

## 1. 目的

説明文（例: スキルのコスト/効果/特記、バフ説明）にスキル参照リンクを埋め込み、閲覧者がリンクをクリックすると、キャラクター詳細のスキル一覧から開くものと同じ詳細モーダルを表示できるようにする。

---

## 2. 背景と現状

1. 用語図鑑リンクは `[[用語ID|表示名]]` 記法で実装済み。
2. 既存パーサは `static/js/common/glossary_ui.js` の `parseMarkupToHTML(...)`。
3. スキル詳細モーダルは `static/js/modals.js` の `openSkillDetailModal(...)`。
4. スキル効果系は `formatSkillDetailHTML(...)`（`static/js/legacy_globals.js`）経由で用語記法が有効。
5. 一部のバフ説明（キャラクター詳細内）は現在プレーン文字列埋め込みで、記法HTML化が未適用。

---

## 3. 確定仕様

## 3.1 記法

スキル参照は名前空間付きで表現する。

- 推奨記法: `[[SKILL:スキルID]]`
- 表示名指定: `[[SKILL:スキルID|任意表示名]]`

例:

- `[[SKILL:B-01]]`
- `[[SKILL:Mp-06|恐れはしない]]`

補足:

- 既存の用語記法 `[[W-19|使用時]]` とは競合しない。
- 大文字小文字は無視して解釈可能（`skill:` / `SKILL:`）。
- `SKILL:` なし（例: `[[B-01]]`）をスキルとして自動判定しない。

## 3.2 クリック時挙動

1. `SKILL:` リンクをクリック。
2. `allSkillData[skillId]` から名称を解決（なければID表示）。
3. `openSkillDetailModal(skillId, skillName)` を呼び出す。
4. 表示されるモーダルはキャラクター詳細から開いたものと同一UI/同一データ構造。

## 3.3 不正ID・未ロード時

- スキルIDが存在しない場合:
  - クリック不可にはせず、モーダルを開いて「データなし（ID表示）」の既存フォールバック表示を使う。
- `allSkillData` 未ロード時:
  - 遅延で `/api/get_skill_data` を取得してから再試行。
  - 取得失敗時はIDのみでモーダル表示（処理は継続）。

## 3.4 適用範囲（v1）

- `formatSkillDetailHTML(...)` で描画される説明領域（既存経路）
- キャラクター詳細のバフ説明/フレーバー表示（`renderCharacterCard` 内）
- 上記以外（アイテム説明など）は v1 対象外とする。

---

## 4. 実装方針

## 4.1 パーサ拡張（用語+スキルの統合解釈）

対象:

- `static/js/common/glossary_ui.js`
- `static/js/legacy_globals.js`（フォールバック）

方針:

1. `[[...]]` の中身を解析して種別を判定。
2. `SKILL:` プレフィックスなら `data-ref-type="skill" data-skill-id="..."` を持つ要素を生成。
3. それ以外は既存どおり用語リンクとして生成。
4. 見た目（色・装飾）は既存の `.glossary-term` と同一にする。

推奨HTMLイメージ:

```html
<span class="glossary-term glossary-skill-ref" data-ref-type="skill" data-skill-id="B-01" tabindex="0" role="button">烈火の閃き</span>
```

## 4.2 クリックイベント分岐

対象:

- `static/js/common/glossary_ui.js`

方針:

1. 既存の委譲クリック処理で `.glossary-term` を検知。
2. `data-ref-type="skill"` の場合は用語ポップアップではなくスキルモーダルを開く。
3. それ以外は既存どおり用語ポップアップ。

## 4.3 スキルモーダル呼び出しの公開保証

対象:

- `static/js/modals.js`

方針:

- `openSkillDetailModal` を `window.openSkillDetailModal` として明示公開する。
- 呼び出し元が `window.openSkillDetailModal` を参照するよう統一。

## 4.4 バフ説明表示へマークアップ適用

対象:

- `static/js/modals.js`（`renderCharacterCard` 内の `descriptionText` / `flavorText` 表示）

方針:

- プレーン文字列挿入を `formatGlossaryMarkupToHTML(...)` 経由に置換。
- 改行・エスケープ・リンク生成を共通化。

---

## 5. 変更対象ファイル（案）

1. `static/js/common/glossary_ui.js`
2. `static/js/legacy_globals.js`
3. `static/js/modals.js`
4. `manuals/implemented/10_Glossary_User_Tutorial.md`（実装確定後に記法追記）
5. `manuals/implemented/12_Character_Modal_Spec.md`（実装確定後に表示仕様追記）

---

## 6. テスト観点

1. `[[SKILL:B-01]]` クリックでスキル詳細モーダルが開く。
2. `[[SKILL:B-01|任意名]]` で表示名が任意名になる。
3. 既存 `[[W-19|使用時]]` の挙動が変わらない。
4. 存在しないスキルIDでクリックしてもエラー落ちせずフォールバック表示される。
5. `allSkillData` 未ロード状態でも初回クリックで読み込み後に表示される。
6. キャラクター詳細のバフ説明欄でリンクが機能する。
7. キーボード操作（Enter/Space）でもスキルリンクが開ける。
8. `[[B-01]]` のような `SKILL:` なし記法はスキルリンク化されない。

---

## 7. リスクと回避

- リスク: 用語IDとスキルIDの誤判定
  - 回避: `SKILL:` プレフィックス必須で判定を固定
- リスク: `openSkillDetailModal` のスコープ依存
  - 回避: `window` 明示公開
- リスク: プレーン文字列描画箇所が残り、リンクが効く場所と効かない場所が混在
  - 回避: v1対象画面を明示し、v1.1で展開対象を追加

---

## 8. 受け入れ条件

1. 説明文中の `[[SKILL:...]]` がリンクとして描画される。
2. クリックでキャラクター詳細と同一スキル詳細モーダルが開く。
3. 既存用語図鑑リンク機能に回帰がない。
4. バフ説明欄でも同じ記法が機能する。
5. `SKILL:` なし記法は既存どおり用語記法としてのみ扱われる。

---

本書は実装着手前の合意用マニュアルである。合意後、`manuals/implemented` 側へ確定仕様を反映する。
