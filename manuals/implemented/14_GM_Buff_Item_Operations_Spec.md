# 14 GMバフ/アイテム運用 仕様書（実装確定）

**最終更新日**: 2026-05-02  
**対象バージョン**: Current  
**関連フェーズ**: Phase A（認可強化）/ Phase B（GM API）/ Phase C（GM UI）

## 1. 本書の目的

セッション進行中に GM が行う以下の操作について、実装済み仕様を一箇所に固定する。

- 任意キャラクターへのバフ/デバフ付与
- 任意キャラクターからのバフ/デバフ解除
- 任意キャラクターのアイテム個数増減（付与/没収）
- 既存イベントの認可強化（所有者 or GM）

## 2. 実装済み範囲

## 2.1 Phase A: 認可強化

- `request_state_update`  
  更新対象キャラに対して `所有者 or GM` のサーバー側チェックを実施。
- `request_use_item`  
  `payload.user_id` で指定されたキャラに対して `所有者 or GM` を必須化。

## 2.2 Phase B: GM API

- `request_gm_apply_buff`
- `request_gm_remove_buff`
- `request_gm_adjust_item`

いずれもサーバー側で `attribute == "GM"` を必須とし、反映後は状態同期を行う。

## 2.3 Phase C: GM UI

`static/js/action_dock.js` のクイック編集に GM 専用パネルを実装。

- バフ付与フォーム（`buff_id`, `lasting`, `delay`, `count`）
- バフ解除フォーム（付与済み一覧から選択）
- アイテム増減フォーム（`item_id`, `delta`）

加えて、バフ付与フォーム上部に各入力値の意味を表示するヘルプ行を追加済み。

## 3. GM UI 入力ルール（確定）

## 3.1 バフ付与欄の意味

- `buff_id`: `Bu-xx` 形式のID（必須）
- `lasting`: 効果が継続するラウンド数
- `delay`: 効果が有効化されるまでの待機ラウンド数
- `count`: スタック数/使用回数系バフ向けの任意値

## 3.2 解除欄

- 現在 `special_buffs` に存在するエントリから選択して解除する。
- 解除要求は `buff_id` のみ送る（Phase3仕様）。

## 3.3 アイテム増減欄

- `delta > 0`: 付与
- `delta < 0`: 没収
- `delta == 0`: 不正入力として拒否

## 4. API仕様（運用視点）

## 4.1 `request_gm_apply_buff`

入力:

- `room`
- `target_id`
- `buff_id`（必須）
- `lasting`（省略時はサーバー側既定）
- `delay`（省略時はサーバー側既定）
- `count`（任意）

動作:

- `buff_id` から名称解決して付与する。
- `buff_name` 単独指定は受理しない（エラー）。
- 付与後は `broadcast_state_update` で同期。

## 4.2 `request_gm_remove_buff`

入力:

- `room`
- `target_id`
- `buff_id`（必須）

動作:

- `buff_id` が一致するエントリのみ解除対象とする。
- `buff_name` ベース解除は行わない。

## 4.3 `request_gm_adjust_item`

入力:

- `room`
- `target_id`
- `item_id`
- `delta`

動作:

- 正負で増減を分岐（付与/没収）。
- 在庫不足など失敗時はエラーを返して反映しない。

## 5. `buff_name` で動的バフは使えるか

結論: **使えない（Phase3）**。  
2026-05-02 以降、`buff_name` 単独指定は受理しない。  
バフ付与/解除は `buff_id` 指定が必須。

運用上の注意:

- 一部のシステム特殊処理は `buff_id` 依存で分岐するため、常に `buff_id` を指定すること。
- `count` の意味はバフごとに異なるため、汎用UIでは「任意の追加値」として扱う。

## 6. 既存マニュアルとの関係

- 操作全体の導線は `02_Integrated_GM_Creator_Manual.md` を正とする。
- データ定義の詳細は `03_Integrated_Data_Definitions.md` を正とする。
- 本書は「GM運用時のバフ/アイテム操作」に限定した確定仕様。
