# キャラHTMLツール 画像出力機能 実装方針（暫定）

## 目的
- キャラ作成ツールで入力した情報を、共有しやすい **1枚のPNG画像** として出力する。
- 対象情報は最低限、以下を含む。
  - キャラクター名
  - 種別（プレイヤー / シナリオ）
  - 出身・ボーナス
  - 能力値・戦闘ステータス（HP/MP含む）
  - 技能値
  - 取得済みスキル
  - 輝化スキル / 特殊パッシブ
  - 所持アイテム

## 実装対象ファイル
- `CharaCreator/GEMDICEBOT_CharaCreator.html`

## UI追加方針
- 「データ入出力」セクションに新規ボタンを追加する。
  - ラベル案: `🖼 画像出力 (.png)`
  - 配置: 既存の `コピー` / `保存(.json)` ボタンと同列
- クリック時に `exportCharacterSheetImage()` を実行する。

## 画像生成方式
- 外部ライブラリは使わず、ブラウザ標準の `canvas` API で描画する。
- 理由:
  - 単体HTML構成を維持できる
  - 依存追加なしで動作しやすい
  - CORSやCDN不達の影響を受けにくい

## 出力レイアウト方針
- タイトル: `<キャラ名> キャラシート`
- セクション分割カード形式（白背景＋見出し色）
  - 能力値
  - 戦闘ステータス
  - 技能値
  - 取得スキル
  - 輝化スキル
  - 特殊パッシブ
  - 所持アイテム
- テキストは折り返し描画（日本語対応のため文字単位ラップ）
- 画像サイズは固定幅 + 可変高さ（内容量に応じて伸長）

## データ収集方針
- 既存のDOM入力値と既存配列を直接参照して構築する。
  - DOM: `char-name`, 各能力値入力, `st-hp-*`, `st-mp-*`, ほか
  - 配列: `SELECTED_SKILLS`, `SELECTED_RADIANCE`, `SELECTED_PASSIVES`, `SELECTED_ITEMS`
- 情報収集技能の出身補正は既存ロジック `getInfoSkillModifier()` を再利用して反映。

## ダウンロード方針
- `canvas.toDataURL('image/png')` でPNG化
- `<a download>` で保存
- ファイル名は `<キャラ名>_sheet.png`
- OS禁則文字は `_` に置換して安全化

## 想定ヘルパー関数
- `sanitizeFilename(name)`
- `wrapTextByChar(ctx, text, maxWidth)`
- `drawRoundedRect(ctx, x, y, width, height, radius)`
- `getCharacterSheetExportData()`
- `exportCharacterSheetImage()`

## エラーハンドリング
- `canvas.getContext('2d')` 取得失敗時は `alert` で通知して中断
- データ欠損時は `なし` を表示して描画継続

## 検証方針
- 最低確認項目:
  - ボタン押下でPNGが保存される
  - 空データ時でも画像化できる
  - スキル/アイテム多件数時にレイアウト破綻しない
  - JSON保存/読込機能に副作用がない
  - 既存の計算処理（`calculateStats`）が壊れていない

## 保留事項
- 長文コマンド全文を画像に含めるか（初版は非表示または省略推奨）
- 色・デザイン調整（可読性優先で初版実装後に調整）
- 将来的に「画像テンプレート差し替え」機能を追加するか
