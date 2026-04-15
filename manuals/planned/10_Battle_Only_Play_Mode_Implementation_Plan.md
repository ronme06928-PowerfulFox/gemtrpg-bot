# 10 戦闘専用プレイモード 改修計画書（設計リセット版）

**更新日**: 2026-04-16  
**対象**: 戦闘専用モード（ルーム内導線・ロビー導線・プリセット管理・戦闘突入）  
**方針**: 本書は実装計画のみ。実装は次工程で実施する。

---

## 1. この改修の目的

- 戦闘専用モードを「直感的に使える運用UI」に再設計する。
- キャラクターJSONを無変換で保存・再利用できる導線に統一する。
- GM専用の管理操作と、プレイヤー参加操作（非GM利用）を分離する。
- 既存の「ステージ」概念を撤廃し、ルーム編成中心に整理する。

---

## 2. 要件確定（今回反映）

1. キャラクタープリセットはアプリ全体で保持する。
2. 保存時に公開範囲を選択できる。  
   - `GMのみ`  
   - `全員公開`
3. プリセットの保存・編集・削除はGMのみ。
4. JSON取り込みは無変換保存。  
   - `kind: "character"` 形式をそのまま保持  
   - 利用時に味方/敵どちらで使うかを選べる
5. 保存時に用途チェックを持つ。  
   - `味方に使用可`  
   - `敵に使用可`
6. 「HP/MP/速度の手動微調整欄」は廃止済み前提で維持しない。
7. 画面名を変更する。  
   - `戦闘専用プリセット編集` -> `キャラクタープリセット編集`
8. 「ステージ」概念は廃止する。
9. 敵は「敵編成プリセット（名前付き）」として保存し、選択利用できる。
10. 敵編成プリセット内で、敵ごとに行動チャート（behavior_profile）上書きを保存できる。
11. 味方編成は2モード。  
    - `プリセット編成`  
    - `現在ルームの味方をそのまま利用`
12. `現在ルーム利用`時は「必要味方人数」を指定し、人数不一致なら戦闘突入不可。
13. 戦闘突入時は自動配置。  
    - 操作者画面のマップ中心を基準  
    - 可能な限り十分な間隔を空けて配置
14. 戦闘突入時に陣営を必ず反映。  
    - 味方: `ally`  
    - 敵: `enemy`
15. 戦闘専用モードは常時PVE扱い。
16. 敵ターゲット矢印は既定で表示。
17. ロビー（ルーム外）でも戦闘専用設定画面を開ける。
18. ルームに入らなくてもJSONからキャラプリセット保存可能にする。
19. 敵編成プリセット設定は別画面（専用ポップアップ）に分離する。  
    - `キャラクタープリセット編集` からボタンで開く  
    - 敵編成の作成/編集/削除は専用画面で完結させる

---

## 3. 現状実装（2026-04-15時点）と差分

### 3.1 既存土台（利用する）

- プリセット保存ストア: `data/cache/battle_only_presets_cache.json`
- サーバー: `events/socket_battle_only.py`
- ストア管理: `manager/battle_only_presets.py`
- UI:
  - `static/js/modals/battle_only_catalog_modal.js`
  - `static/js/modals/battle_only_draft_modal.js`
  - `static/js/modals/battle_only_participant_modal.js`

### 3.2 主な不足

- 敵編成プリセット（編成名＋推奨味方人数＋敵ごと行動チャート）の独立管理が未実装。
- 味方編成モード（プリセット/現在ルーム利用）の切替が未実装。
- 非GMの戦闘突入導線が弱い（中央導線・プレイヤー向け開始フロー不足）。
- ルーム外のJSON保存導線が限定的。
- 旧設計説明（ステージ前提）が残存。

---

## 4. 改修後のデータモデル

## 4.1 グローバル保存ストア（battle_only_presets_cache）

```json
{
  "version": 2,
  "updated_at": 0,
  "character_presets": {
    "boc_001": {
      "id": "boc_001",
      "name": "バグ取りの翁",
      "visibility": "gm|public",
      "allow_ally": true,
      "allow_enemy": true,
      "character_json": {
        "kind": "character",
        "data": {}
      },
      "created_at": 0,
      "updated_at": 0,
      "created_by": "GM",
      "updated_by": "GM"
    }
  },
  "enemy_formations": {
    "bof_001": {
      "id": "bof_001",
      "name": "翁と増やしの塩",
      "visibility": "gm|public",
      "recommended_ally_count": 2,
      "members": [
        {
          "preset_id": "boc_001",
          "count": 1,
          "behavior_profile_override": {}
        },
        {
          "preset_id": "boc_002",
          "count": 2,
          "behavior_profile_override": {}
        }
      ],
      "created_at": 0,
      "updated_at": 0,
      "created_by": "GM",
      "updated_by": "GM"
    }
  }
}
```

## 4.2 ルーム state（battle_only）

```json
{
  "play_mode": "battle_only",
  "battle_only": {
    "status": "lobby|draft|in_battle",
    "ally_mode": "preset|room_existing",
    "required_ally_count": 2,
    "enemy_formation_id": "bof_001",
    "ally_entries": [
      { "preset_id": "boc_010", "user_id": "u_1" }
    ],
    "enemy_entries": [
      {
        "preset_id": "boc_001",
        "count": 1,
        "behavior_profile_override": {}
      }
    ],
    "records": [],
    "active_record_id": null,
    "options": {
      "force_pve": true,
      "show_enemy_target_arrows": true
    }
  }
}
```

---

## 5. 権限と公開範囲

| 操作 | GM | Player |
|---|---|---|
| キャラプリセット保存/編集/削除 | 可 | 不可 |
| 敵編成プリセット保存/編集/削除 | 可 | 不可 |
| 公開プリセット閲覧 | 可 | 可 |
| GM限定プリセット閲覧 | 可 | 不可 |
| 戦闘専用ルームで敵編成選択 | 可 | 可（公開のみ） |
| 戦闘突入実行 | 可 | 可（battle_only時、バリデーション通過時） |

補足:
- 非GM戦闘突入を許可するのは「遊べるようにしたい」要件対応。
- 管理系CRUDはGM限定を維持。

---

## 6. UI/UX 設計

## 6.1 画面名称と導線

- モーダル名:
  - `キャラクタープリセット編集`
- ロビー:
  - 右下常設ボタン `戦闘専用設定`
- 戦闘専用ルーム:
  - 画面中央に `戦闘専用` アクションエリアを表示
  - GM/Player共通で「敵編成選択 -> 味方準備 -> 戦闘突入」

## 6.2 キャラプリセット編集モーダル

- タブA: `キャラプリセット`
  - JSON貼り付け取り込み
  - 現在ルームのキャラ取り込み（`現在値`/`初期値`選択）
  - 公開範囲・用途チェック（味方/敵）設定
  - 一覧カードクリックで詳細モーダル（ステータス/スキル/コマンド/パッシブ）
- `敵編成プリセット編集を開く` ボタンを配置

## 6.2.1 敵編成プリセット専用ポップアップ（新設）

- モーダル名:
  - `敵編成プリセット編集`
- 機能:
  - 編成名
  - 推奨味方人数
  - 敵メンバー（キャラプリセット選択 + 体数）
  - 敵ごとの行動チャート上書き編集
  - 敵編成の保存/読込/削除
- 目的:
  - キャラプリセット編集と敵編成編集の責務を分離し、入力密度を下げる
  - 敵編成作成時の操作導線を単純化する

## 6.3 戦闘専用編成モーダル

- 敵編成プリセット選択
- 味方編成モード切替:
  - `プリセット編成`
  - `現在ルームの味方を使う`
- `現在ルーム利用`時:
  - 必要味方人数を指定
  - ルーム内味方人数と一致しなければ突入ボタン無効
- ボタン名統一:
  - `戦闘開始` 表記を `戦闘突入` に統一

---

## 7. 戦闘突入処理フロー（仕様）

1. バリデーション  
   - 敵編成が存在する  
   - 味方編成条件が成立する  
   - 公開範囲/権限に違反しない
2. ルームキャラ生成  
   - プリセット使用時: `character_json` から生成（無変換元を利用）  
   - ルーム利用時: 既存味方をそのまま利用
3. 陣営設定を明示上書き  
   - 味方: `type/team/side/faction = ally`  
   - 敵: `type/team/side/faction = enemy`
4. 自動配置  
   - 操作者画面中心アンカーを基準  
   - 2マス間隔を優先し不足時のみ詰める
5. PVE固定オプション適用  
   - `force_pve = true`  
   - `show_enemy_target_arrows = true`
6. 戦闘突入ログ出力と状態更新  
   - `battle_only.status = in_battle`

---

## 8. Socket/API 改修計画

## 8.1 維持するイベント

- `request_bo_catalog_list`
- `request_bo_preset_save`
- `request_bo_preset_delete`
- `request_bo_draft_state`
- `request_bo_draft_update`
- `request_bo_start_battle`
- `request_bo_record_state`
- `request_bo_record_mark_result`
- `request_bo_record_export`

## 8.2 追加/拡張するイベント

- `request_bo_enemy_formation_save`
- `request_bo_enemy_formation_delete`
- `request_bo_enemy_formation_list`
- `request_bo_select_enemy_formation`
- `request_bo_set_ally_mode`
- `request_bo_validate_entry`

拡張要点:
- `request_bo_start_battle` の実行権限を `GMのみ` から `battle_only参加者` へ拡張。
- 敵編成IDから `enemy_entries` を展開可能にする。
- 行動チャート上書きを敵生成時に `flags.behavior_profile` へ注入する。

---

## 9. 既存データ方針

- 旧「ステージ」関連データは本改修で参照しない。
- 既存 battle_only テスト用データは破棄前提（ユーザー指示）。
- 保存ストアは `version:2` へ移行し、旧キーは読み捨て互換または初期化で整理する。

---

## 10. テスト計画（実装後）

## 10.1 自動テスト

- `tests/test_battle_only_catalog.py` 拡張
  - キャラプリセット保存（無変換JSON保持）
  - 敵編成プリセットCRUD
  - 可視性（GM/public）フィルタ
  - 非GM戦闘突入可否
  - 味方モード `preset|room_existing` バリデーション
  - 陣営設定反映（ally/enemy）
  - 戦績出力

- 新規候補
  - `tests/test_battle_only_enemy_formation.py`
  - `tests/test_battle_only_entry_validation.py`
  - `tests/test_battle_only_spawn_faction_and_anchor.py`

## 10.2 手動テスト

1. ロビーから `戦闘専用設定` を開き、JSONだけでキャラプリセット保存できる。
2. キャラプリセット詳細モーダルでステータス/コマンド/スキルが確認できる。
3. 敵編成プリセットを作成し、推奨味方人数と行動チャート上書きを保存できる。
4. `キャラクタープリセット編集` から専用ボタンで `敵編成プリセット編集` ポップアップを開ける。
5. 戦闘専用ルームで敵編成を選び、`プリセット編成` と `現在ルーム利用` を切替できる。
6. `現在ルーム利用` で人数不一致時に `戦闘突入` が無効になる。
7. 戦闘突入後、味方駒が青・敵駒が赤（陣営反映）になる。
8. 配置が画面中心基準で左右に分かれ、間隔が確保される。
9. PVE扱いと敵矢印の既定表示を確認できる。

---

## 11. 実装フェーズと見通し（全体）

## Phase 0: 設計確定（0.5日）

- 本書の確定
- 既存UI文言の統一方針確定

## Phase 1: 保存モデル再編（1.5日）

- ストア `version:2` 化
- キャラプリセット/敵編成プリセット分離
- 旧ステージ依存除去

## Phase 2: サーバーAPI改修（2.0日）

- `socket_battle_only.py` のイベント追加
- 非GM突入条件の実装
- 行動チャート上書き注入

## Phase 3: UI改修（2.0日）

- `キャラクタープリセット編集` モーダル再編
- `敵編成プリセット編集` 専用ポップアップ新設
- 戦闘専用編成モーダルの2モード実装
- ロビー常設導線と中央導線追加

## Phase 4: 戦闘突入ロジック仕上げ（1.0日）

- 陣営反映の最終保証
- 中心基準自動配置と間隔調整の最終調整
- PVE/矢印既定値固定

## Phase 5: テストと調整（1.0日）

- 自動テスト追加
- 手動テスト実施
- 文言/UI調整

### 合計見通し

- 実装+検証で **約8.0日**（単独作業想定）
- 主リスク:
  - 既存 battle_only UI と旧イベントの互換維持
  - 非GM突入時の権限制御境界
  - 行動チャート上書きの適用タイミング差異

---

## 12. 実装開始条件

- 本計画書の承認
- 非GM戦闘突入の最終権限境界（全参加者可/ルームオーナーのみ可）の確定
- 優先順（まず敵編成プリセットか、まず味方モード切替か）の確定
