# 用語ポップアップ（Glossary）機能 実装計画（リポジトリ統合版）

## 目的
スキル効果テキスト／ログ／状態一覧などに登場する「固有名詞（状態異常・効果・ルール用語）」を、**ホバー（PC）またはクリック／タップ（PC/モバイル）**で説明表示できるようにする。

対象例：出血、出血氾濫、破裂爆発、亀裂崩壊、各種バフ（Bu-xx）など。

---

## ゴール（受け入れ基準）
1. スキル説明文（コスト／効果／特記）に `[[TERM_ID|表示名]]` を埋め込むと、その表示名がリンク化される。
2. リンク化された用語を
   - PC: hover で short（1〜2行）ツールチップ、click で long（詳細）
   - Mobile: tap/click で long（詳細）
   で表示できる。
3. 用語辞書は **term_id をキー**に検索でき、表示名の改名や表記揺れがあっても参照が壊れない。
4. 文字列置換は **HTMLエスケープ（XSS対策）**を前提に安全に行う。
5. 未定義の term_id が参照されても、UIが壊れず「未定義」扱いで表示できる。

---

## 非ゴール（このフェーズではやらない）
- 用語の自動検出（テキスト中の一致を自動リンク化）
- 図鑑画面（検索・カテゴリフィルタ・関連語遷移など）

---

## 仕様（固定）

### 1) 参照記法（明示マークアップ方式）
- `[[TERM_ID|表示名]]`
  - `TERM_ID`：用語辞書のキー（例：`TERM_BLEED`、`EFFECT_RUPTURE`、`BUFF_Bu-08`）
  - `表示名`：画面に出すテキスト（例：出血、破裂爆発）

将来拡張（任意）
- `[[TERM_ID]]`（表示名省略時は辞書の display_name を使う。未定義なら TERM_ID を表示）

### 2) 用語辞書（glossary）データモデル
スプレッドシート（またはCSV）に以下の列を用意する。

最小カラム（推奨）
- `term_id` (string, unique, required)
- `display_name` (string, required)
- `category` (string, required) 例：`status` / `buff` / `debuff` / `effect` / `rule`
- `short` (string, optional) ツールチップ用
- `long` (string, optional) 詳細ポップアップ用
- `links` (string, optional) 関連 term_id のCSV

任意カラム
- `synonyms` (string, optional) 別名のCSV（将来の自動リンク化に備える）
- `icon` (string, optional)

クライアント配布形（JSON）
```json
{
  "TERM_BLEED": {
    "term_id": "TERM_BLEED",
    "display_name": "出血",
    "category": "status",
    "short": "…",
    "long": "…",
    "links": ["TERM_BLEED_FLOOD"]
  }
}
```

### 3) UI仕様
- **ツールチップ（short）**：PC hover時。shortがあれば表示。なければ表示しない。
- **ポップアップ（long）**：click/tap時。longが無ければ short を表示。どちらも無ければ「説明未登録」。
- 閉じ方：外側クリック、Escキー。
- 配置：クリックした要素の `getBoundingClientRect()` 基準で画面内に収まるよう補正。

---

## 既存コード前提（重要）
このリポジトリには既に「図鑑データをCSVから取得→JSONキャッシュに保存→グローバル辞書へ反映」という仕組みがある。

- バフ図鑑：`manager/buffs/loader.py` が CSV を取得し `buff_catalog_cache.json` を生成し、`extensions.all_buff_data` に反映する。
- クライアント側のスキル詳細HTMLは `static/js/battle/utils/DomUtils.js` の `formatSkillDetailHTML()` が生成している。
  - 現状は `effect/cost/special/command` を **エスケープせず innerHTML に流している**ため、Glossary統合時に合わせてエスケープを導入する（副作用：意図的にHTMLを埋め込んでいた場合は効かなくなる）。

---

## 実装（ファイル単位の差分設計）

### サーバ側

#### 1) `extensions.py`
- 追加
  - `all_glossary_data = {}` をグローバルに追加（`all_skill_data`／`all_buff_data` と同列）

#### 2) 新規: `manager/glossary/loader.py`
バフ図鑑ローダー（`manager/buffs/loader.py`）の構造を踏襲する。

- 定数
  - `GLOSSARY_CSV_URL`：Glossaryシートを publish した CSV URL
  - `CACHE_FILE = <repo_root>/glossary_catalog_cache.json`
- `GlossaryCatalogLoader` クラス
  - `fetch_from_csv()`：CSVを取得し、`term_id` をキーに dict 化
    - `links/synonyms` はCSV文字列なら `split(',')` して配列化（空要素は除外）
  - `save_to_cache(data)`
  - `load_from_cache()`
  - `refresh()`
  - `load_terms()`：キャッシュ優先で読み込み、最後に `extensions.all_glossary_data` を `clear/update`

- グローバルインスタンス
  - `glossary_catalog_loader = GlossaryCatalogLoader()`

#### 3) `manager/data_manager.py`（または「全データ更新」をまとめているファイル）
既存の「全データ更新」手順に glossary を追加する。

- 全データ更新（例：`update_all_data()` 相当）
  - `from manager.glossary.loader import glossary_catalog_loader`
  - `glossary_catalog_loader.refresh()` を実行
- 起動時初期化（例：`init_app_data()` 相当）
  - `glossary_catalog_loader.load_terms()` を実行

※既存のバフ更新が重複している箇所があるが、本タスクでは**挙動を変えない**（将来の整理対象）。

#### 4) 配布方法（最小変更）
クライアントが辞書を参照できる形にする。

優先順位
1. **既に「静的JSONを直接読ませる」流れがある場合**：`/glossary_catalog_cache.json` を `static` 配下へ移す（または `send_from_directory` で公開）
2. それが難しい場合：`/api/glossary` のJSONエンドポイントを追加し、クライアントが `fetch` する

「どちらが既存に合うか」は、現行の `buff_catalog_cache.json` の配布方法に合わせる。

---

### クライアント側

#### 1) 新規: `static/js/common/glossary_ui.js`
依存なし・グローバル関数として実装する（visual系が window グローバルを多用しているため）。

提供API（window）
- `window.Glossary = { initOnce, ensureDataLoaded, getTerm, parseMarkupToHTML, bindDelegatedEvents, showTooltip, showPopup, hideAll }`

要点
- `initOnce()`
  - 1回だけ初期化（フラグで多重初期化防止）
  - データ読み込み（後述）
  - document へのイベント委譲をセット
- `ensureDataLoaded()`
  - `window.glossaryData` があればそれを使う
  - なければ `fetch('/api/glossary')` または `fetch('/glossary_catalog_cache.json')`（サーバ側方針に合わせる）
  - 失敗しても例外で落とさず、空辞書で継続
- `getTerm(term_id)`
  - 未定義なら `null`
- `parseMarkupToHTML(text)`
  - 文字列を **HTMLエスケープ**してから `[[...]]` を `span` に置換
  - 出力は HTML string（既存の `formatSkillDetailHTML` が string を返しているため）
  - `span` 形式
    - `<span class="glossary-term" data-term-id="TERM_ID" role="button" tabindex="0">表示名</span>`

イベント委譲
- click/tap
  - `.glossary-term` をクリックしたら popup
- hover（PC）
  - `pointerenter/pointerleave` を使い、`(pointer: fine)` の時だけ tooltip

ポップアップDOM
- 初期化時に `document.body` 直下へコンテナを1つ追加
  - tooltip 用（小）
  - popup 用（大）
- `Esc` と外側クリックで閉じる

#### 2) 既存スキル詳細HTMLへの統合
対象ファイル
- `static/js/battle/utils/DomUtils.js`

変更方針
- `formatSkillDetailHTML(skillData)` 内で、以下の項目を **エスケープ＋Glossaryパース**した上でHTMLへ埋め込む。
  - `command`
  - `cost`
  - `effect`
  - `special`

具体
- `Glossary.parseMarkupToHTML()` を使う。
  - `commandHTML = Glossary.parseMarkupToHTML(command)`
  - `costHTML = Glossary.parseMarkupToHTML(cost)`
  - `effectHTML = Glossary.parseMarkupToHTML(effect)`
  - `specialHTML = Glossary.parseMarkupToHTML(special)`

注意
- `parseMarkupToHTML` の内部でエスケープするため、ここでは `innerHTML` に流してよいのは
  - `Glossary` が生成した `span` と、フォーマット用の最低限の `div` のみ
- 辞書本文（short/long）は **textContent** で描画する（HTMLとして解釈しない）。

#### 3) 初期化呼び出しポイント
次のいずれか（既存構造に合わせて最小変更で選ぶ）。

- `static/js/main.js` の「アプリ起動」相当箇所で `Glossary.initOnce()` を呼ぶ
- もしくは visual戦闘タブの初期化（`static/js/visual/visual_main.js` の `setupVisualBattleTab()`）の冒頭で `Glossary.initOnce()` を呼ぶ

推奨
- **main.js で1回だけ**呼ぶ（タブに依存しないため）

#### 4) CSS
追加先（どちらか）
- `static/css/modules/common_ui.css` に追記
- もしくは新規 `static/css/modules/glossary.css` を追加し、`static/styles.css` に `@import` する

最低限のスタイル
- `.glossary-term`
  - 下線（点線）＋カーソル
  - ホバーで背景色を軽く
- tooltip/popup コンテナ
  - `position: fixed; z-index: 9999; max-width; padding; border; box-shadow; border-radius;`

---

## 作業タスク（Codex向け：実行順）

### Task 1: サーバに glossary ローダーを追加
- `extensions.py` に `all_glossary_data = {}`
- `manager/glossary/loader.py` を新規作成
- `glossary_catalog_cache.json` の生成・読み込み・`extensions.all_glossary_data` 反映

### Task 2: 起動時初期化／更新手順へ組み込み
- `init_app_data()` 相当へ `glossary_catalog_loader.load_terms()` を追加
- 全データ更新へ `glossary_catalog_loader.refresh()` を追加

### Task 3: クライアント glossary UI（イベント委譲）を追加
- `static/js/common/glossary_ui.js` を新規作成
- `Glossary.initOnce()` を `main.js`（推奨）または `visual_main.js` から呼ぶ

### Task 4: スキル詳細HTMLを安全化＋Glossary対応
- `static/js/battle/utils/DomUtils.js` の `formatSkillDetailHTML()` を更新
  - `command/cost/effect/special` を `Glossary.parseMarkupToHTML()` 経由でHTML化
  - これにより XSS 対策も同時に入る

### Task 5: CSS追加
- `.glossary-term` と tooltip/popup のスタイルを追加

### Task 6: 手動テスト（最低限）
- スキル効果に `[[TERM_TEST|テスト用語]]` を入れ、クリックで説明が出る
- 未定義ID（例：`[[TERM_NOPE|未定義]]`）でもUIが壊れない
- PCで hover tooltip（shortがあるときだけ）
- Esc / 外側クリックで閉じる

---

## セキュリティ注意（必須）
- glossary の `short/long` は **HTMLとして解釈しない**（必ず textContent で表示）。
- スキルの `command/cost/effect/special` は **必ずHTMLエスケープ**した上で、Glossaryの `span` だけを例外的にHTMLとして差し込む。

---

## 付録：term_id 命名規約（提案）
- 状態異常（ゲーム的な状態）：`STATUS_BLEED` / `STATUS_RUPTURE` / `STATUS_FISSURE`
- ダメージ発生源（定数に対応）：`DS_bleed` / `DS_bleed_flood`（DamageSource）
- 効果名：`EFFECT_RUPTURE_EXPLOSION` など
- バフ図鑑（Bu-xx）：`BUFF_Bu-08`

※この命名は「人間が読みやすい」ことが目的。機械的には **一意なら何でもよい**。
