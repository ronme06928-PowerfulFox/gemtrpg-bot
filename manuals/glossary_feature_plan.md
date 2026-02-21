# 用語ポップアップ（Glossary）機能 実装計画（リポジトリ統合版・現状反映）

## 0. 現状確認サマリ（2026-02-19）
以下を現行コードで確認済み。

- Glossary機能は未実装
  - `extensions.py` に `all_glossary_data` がない
  - `manager/glossary/loader.py` がない
  - APIに Glossary配布エンドポイントがない
- スキル詳細HTMLは未エスケープで `innerHTML` に挿入されている
  - `static/js/battle/utils/DomUtils.js`
  - `static/js/legacy_globals.js`
- `formatSkillDetailHTML` が2箇所に重複実装されている
  - モジュール版: `static/js/battle/utils/DomUtils.js`
  - レガシー版: `static/js/legacy_globals.js`
- フロントのデータAPI命名は `get_*_data` 系に統一されている
  - 例: `/api/get_skill_data`, `/api/get_item_data`, `/api/get_radiance_data`, `/api/get_passive_data`
- `main.js` は `DOMContentLoaded` で初期データを順次 fetch している
  - `static/js/main.js`
- `manager/data_manager.py` の `update_all_data()` はバフ更新ブロックが重複している（既存状態）

---

## 1. 目的
スキル説明文（コスト／効果／特記／コマンド）に埋め込まれた用語を、PCではhover/click、モバイルではtapで参照できるようにする。

---

## 2. 受け入れ基準
1. `[[TERM_ID|表示名]]` をリンク化し、tooltip/popupで説明表示できる。
2. `[[TERM_ID]]`（表示名省略）も解釈できる。
3. `term_id` キーで辞書参照でき、表記変更で参照が壊れない。
4. 未定義IDでもUIが壊れず「説明未登録」で表示できる。
5. `command/cost/effect/special` はXSS耐性を持つ（HTMLエスケープ前提）。
6. tooltip/popup本文（`short/long`）はHTML解釈せず `textContent` で表示する。

---

## 3. 旧計画からの修正点（重要）
1. **配布経路を `/api/get_glossary_data` に固定**
   - このリポジトリのAPI命名規約に合わせる。
   - ルート直下 `glossary_catalog_cache.json` 直配信は採用しない。
2. **初期化経路を明示**
   - `Glossary.initOnce()` は `main.js` の `DOMContentLoaded` で1回呼ぶ。
   - `static/index.html` に `js/common/glossary_ui.js` の script 追加が必要。
3. **重複formatter対応を計画へ追加**
   - `DomUtils.js` だけでなく `legacy_globals.js` 側も整合させる。
   - 方針は「`formatSkillDetailHTML` の実装を1系統に寄せる」。
4. **`update_all_data()` の手順整理を同時実施**
   - 既存の重複バフ更新を1回に整理し、Glossary更新を追加して 6ステップ化する。

---

## 4. 仕様（固定）

### 4.1 マークアップ記法
- `[[TERM_ID|表示名]]`
- `[[TERM_ID]]`（表示名省略時は辞書 `display_name`、なければ `TERM_ID`）

### 4.2 用語辞書データモデル
最小カラム:
- `term_id` (required, unique)
- `display_name` (required)
- `category` (required)
- `short` (optional)
- `long` (optional)
- `links` (optional CSV)
- `synonyms` (optional CSV)
- `icon` (optional)

`category` の運用固定値:
- `状態異常`
- `効果`
- `バフ`
- `デバフ`
- `ルール`
- `スキルタグ`
- `タイミング`

配布JSON（term_idキー）:
```json
{
  "TERM_BLEED": {
    "term_id": "TERM_BLEED",
    "display_name": "出血",
    "category": "状態異常",
    "short": "継続ダメージ。",
    "long": "ラウンド進行時に追加ダメージを受ける。",
    "links": ["TERM_BLEED_FLOOD"]
  }
}
```

### 4.3 UI仕様
- PC:
  - hover: `short` をtooltip表示（なければ非表示）
  - click: `long` 優先、なければ `short`、なければ「説明未登録」
- Mobile:
  - tap/clickでpopup表示
- 閉じる操作:
  - 外側クリック、`Esc`
- 表示位置:
  - 対象要素の `getBoundingClientRect()` 基準で画面内に補正

---

## 5. 実装設計（ファイル単位）

### 5.1 サーバ側

#### A. `extensions.py`
- `all_glossary_data = {}` を追加。

#### B. 新規 `manager/glossary/loader.py`
`manager/buffs/loader.py` と同系統で実装。

- 定数:
  - `GLOSSARY_CSV_URL`
  - `CACHE_FILE = <repo_root>/glossary_catalog_cache.json`
- `GlossaryCatalogLoader`:
  - `fetch_from_csv()`
    - `term_id` をキーに dict 化
    - `links/synonyms` はCSV文字列を配列化（空要素除外）
  - `save_to_cache(data)`
  - `load_from_cache()`
  - `refresh()`
  - `load_terms()`
    - キャッシュ優先、未取得時CSV
    - 最後に `extensions.all_glossary_data` を `clear/update`
- グローバル:
  - `glossary_catalog_loader = GlossaryCatalogLoader()`

#### C. `manager/data_manager.py`
- `init_app_data()` に `glossary_catalog_loader.load_terms()` を追加。
- `update_all_data()` に `glossary_catalog_loader.refresh()` を追加。
- 既存の重複バフ更新ブロックは1つに整理し、進捗表示を実際のステップ数と一致させる。

#### D. `app.py`
- `extensions` import に `all_glossary_data` を追加。
- 新規API:
  - `@app.route('/api/get_glossary_data', methods=['GET'])`
  - 返却: `all_glossary_data`
  - 空の場合は `glossary_catalog_loader.load_terms()` を呼んでから返却。

---

### 5.2 クライアント側

#### A. 新規 `static/js/common/glossary_ui.js`
グローバルAPI:
- `window.Glossary = { initOnce, ensureDataLoaded, getTerm, parseMarkupToHTML, bindDelegatedEvents, showTooltip, showPopup, hideAll }`

要点:
- `ensureDataLoaded()`
  - `window.glossaryData` があれば利用
  - なければ `/api/get_glossary_data` を fetch
  - 失敗時は空辞書で継続
- `parseMarkupToHTML(text)`
  - 先にHTMLエスケープ
  - `[[...]]` を `.glossary-term` span に置換
  - 改行は `<br>` に変換（表示崩れ防止）
- `getTerm(termId)`
  - 未定義なら `null`
- tooltip/popup本文は `textContent` で描画

#### B. `static/index.html`
- `js/common/glossary_ui.js` を読み込み順に追加（`main.js` より前）。

#### C. `static/js/main.js`
- `DOMContentLoaded` 内で `Glossary.initOnce()` を1回実行（存在チェック付き）。

#### D. `static/js/battle/utils/DomUtils.js`
- `formatSkillDetailHTML()` の `command/cost/effect/special` を
  `Glossary.parseMarkupToHTML()` 経由で生成。
- `Glossary` 未初期化時の安全フォールバック（単純エスケープ）を持たせる。

#### E. `static/js/legacy_globals.js`
- `formatSkillDetailHTML` の重複実装を解消。
  - 方針1: レガシー定義を削除し `DomUtils` 実装へ統一
  - 方針2: レガシー側は安全な委譲ラッパーのみにする

#### F. CSS
- 新規 `static/css/modules/glossary.css`
  - `.glossary-term`（点線下線、hover）
  - `.glossary-tooltip`
  - `.glossary-popup`
- `static/styles.css` に `@import 'css/modules/glossary.css';`

---

## 6. 実装タスク順（実行順）
### Task 1
サーバ辞書基盤追加（`extensions.py`, `manager/glossary/loader.py`）

### Task 2
起動時初期化・全更新手順へ組み込み（`manager/data_manager.py`）

### Task 3
Glossary配布API追加（`app.py`）

### Task 4
UI基盤追加（`static/js/common/glossary_ui.js`, `static/index.html`, `static/js/main.js`）

### Task 5
スキル詳細HTML安全化とGlossary統合（`DomUtils.js` + `legacy_globals.js`）

### Task 6
CSS追加（`glossary.css`, `styles.css`）

### Task 7
検証（手動 + 既存回帰）

---

## 7. テスト観点（最低限）
1. `[[TERM_TEST|テスト用語]]` がリンク化され popup表示される。
2. `[[TERM_TEST]]`（表示名省略）が期待どおり表示される。
3. 未定義IDでもUIが壊れない。
4. PC hoverで `short` のみ tooltip表示、clickで popup表示。
5. `Esc` / 外側クリックで閉じる。
6. `command/cost/effect/special` に `<script>` 等を入れても実行されない。
7. 既存のスキル詳細表示（visual/wide/declare）が崩れない。

---

## 8. セキュリティ要件（必須）
- 用語本文（`short/long`）は常に `textContent`。
- `parseMarkupToHTML()` は「エスケープ -> マークアップ置換」の順序を厳守。
- `innerHTML` に入るのは、アプリ側が生成した最小限タグのみ。
