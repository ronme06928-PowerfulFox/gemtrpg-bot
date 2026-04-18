# 17. 戦闘専用プレイモード 実装済み仕様

最終更新: 2026-04-18  
対象: 実装運用（Current）  
移管元: `manuals/planned/10_Battle_Only_Play_Mode_Implementation_Plan.md`

---

## 0. 本書の位置づけ

本書は、戦闘専用プレイモードの「実装済み仕様」をまとめた運用仕様です。  
計画書で扱っていた内容のうち、現在のコードに反映済みの項目を `implemented/` 側へ移管しています。

---

## 1. 実装済みの中核仕様

1. 戦闘専用モード用プリセットストアを `version:2` で管理する。
1. キャラクタープリセットを JSON 無変換で保存する。
1. 敵編成プリセット、味方編成プリセット、ステージプリセットを個別管理する。
1. 公開範囲（`gm` / `public`）に応じた閲覧制御を行う。
1. プリセット CRUD は GM のみ許可する。
1. 戦闘専用ルームでの戦闘突入は参加者導線を提供する（公開プリセット前提）。
1. 戦闘突入時に陣営を `ally` / `enemy` へ明示設定する。
1. 戦闘専用モードを PVE 前提で運用し、敵矢印表示を既定有効にする。
1. 戦績はルーム状態に保持し、エクスポートを提供する。
1. 敵編成・味方編成・ステージプリセットは全体 JSON 出力に対応する。

---

## 2. データモデル（実装）

プリセット保存は `data/cache/battle_only_presets_cache.json` を使用する。  
主要キー:

- `character_presets`
- `enemy_formations`
- `ally_formations`
- `stage_presets`

ルーム状態は `room_state.battle_only` を使用する。  
主要キー:

- `status` (`lobby` / `draft` / `in_battle`)
- `selected_stage_id`
- `ally_mode` (`preset` / `room_existing`)
- `enemy_formation_id`
- `ally_formation_id`
- `required_ally_count`
- `enemy_entries`
- `ally_entries`
- `records`

---

## 3. UI 構成（実装）

主要モーダル:

- `キャラクタープリセット編集`
- `編成プリセット管理`（ハブ）
- `敵編成プリセット編集`
- `味方編成プリセット編集`
- `ステージプリセット編集`
- `戦闘専用 かんたん戦闘突入`
- `戦闘専用編成`

方針:

- キャラクター素材管理と編成管理を分離する。
- プレイヤー向けには「ステージ選択→戦闘突入」の短経路を提供する。

---

## 4. サーバーイベント（実装）

既存イベント群に加え、以下を実装済み:

- `request_bo_enemy_formation_save` / `delete` / `list`
- `request_bo_ally_formation_save` / `delete` / `list`
- `request_bo_stage_preset_save` / `delete` / `list`
- `request_bo_select_stage_preset`
- `request_bo_set_ally_mode`
- `request_bo_validate_entry`
- `request_bo_export_enemy_formations_json`
- `request_bo_export_ally_formations_json`
- `request_bo_export_stage_presets_json`
- `request_bo_record_export`

---

## 5. 運用上の注意

1. 管理系操作（保存・編集・削除）は GM 権限が必要。
1. 非GMは公開範囲 `public` のプリセットのみ参照可能。
1. `room_existing` 利用時は `required_ally_count` を満たす必要がある。
1. ルームを跨ぐ永続はプリセットのみ。戦績はルーム生存中データとして扱う。

---

## 6. 計画書からの移管方針

以下は `planned/10` から本書へ移管済み:

1. 戦闘専用モード再設計の要件確定事項
1. v2 ストア設計方針
1. モーダル分離方針
1. ステージプリセット導線
1. JSON エクスポート方針

`planned` 側には本トピックの旧計画書を残さず、今後は本書を正本として更新する。
