# 24 簡易ステータス編集改善 / UI統一 実装サマリ
作成日: 2026-05-09

## 1. 目的
`planned/24_Quick_Edit_and_UI_Consistency_Plan.md` で扱っていた以下2件の実装結果を、完了後の正本として要約する。

1. 簡易ステータス編集機能の操作性改善
2. 戦闘系UIの統一

本書は完了後の参照用であり、計画過程そのものは保持しない。

---

## 2. ストリームA: 簡易ステータス編集改善

### 2.1 実装結果
- バフ付与を辞書連動プルダウン化
- 選択中バフの名称 / 説明 / 効果要約プレビューを追加
- `lasting` / `delay` / `count` の入力補助を追加
- Value駆動バフ向け `value` 入力を追加
- 現在付与中バフの識別しやすい解除UIを追加
- `出血 / 破裂 / 亀裂 / 戦慄 / 荊棘` の状態異常付与UIを追加
- `亀裂` に対してスタック数に加え継続ラウンド指定を追加
- アイテム増減を辞書連動プルダウン化
- `GM Buff / Item Control` をキャラごとに折り畳み可能にし、初期状態を折り畳みに変更

### 2.2 実装ファイル
- `static/js/action_dock.js`
- `events/socket_char.py`

### 2.3 補足
- 追加イベントは GM専用の `request_gm_apply_state` に限定
- 実ブラウザ確認は完了条件から外し、コード上の最低限確認で完了扱い

---

## 3. ストリームB: 戦闘系UI統一

### 3.1 決定したルール
- 対象スコープは戦闘系画面のみ
- 同じ役割のUIは同じ見た目と挙動に統一
- 主要UIルール:
  - ボタン種別: `primary / secondary / ghost / danger`
  - 角丸: `6px / 8px / 12px`
  - モーダルヘッダー: 上辺にアクセントライン
  - キャラデータ書き込み操作は明示送信

### 3.2 実装結果
- デザイントークンを `common_ui.css` に集約
- 簡易ステータス編集モーダルへ統一ルールを適用
- 他の戦闘モーダル群へ横展開
- Action Dock / 戦闘パネルにも適用

### 3.3 主要ファイル
- `static/css/modules/common_ui.css`
- `static/css/action_dock.css`
- 戦闘系モーダル群の各JS / CSS

---

## 4. 確認結果
- `node --check static/js/action_dock.js`
- `python -m py_compile events/socket_char.py`

上記を通過済み。

---

## 5. 関連文書
- `manuals/implemented/14_GM_Buff_Item_Operations_Spec.md`
- `manuals/planning_process.md`

`planned/24_Quick_Edit_and_UI_Consistency_Plan.md` は完了に伴い削除した。
