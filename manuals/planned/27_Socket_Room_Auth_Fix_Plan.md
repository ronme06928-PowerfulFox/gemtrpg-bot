# 27 ルーム内Socketイベント認証水準引き上げ計画

**作成日**: 2026-06-27  
**種別**: planned  
**状態**: 実装完了（実機スモーク確認・moved to implemented 待ち）  
**前提計画**: [26_Render_Local_Account_Management_Plan.md](26_Render_Local_Account_Management_Plan.md) Phase 5 残項「残りのSocketイベント（battle/char/items/exploration）の全面棚卸し」

---

## 1. 背景と目的

Plan 26 Phase 5（membership正本化）では、choke-point方式で全SocketイベントのGM判定をmembership再解決へ移行した。  
しかし各ハンドラの**「自分が宛先ルームに在室しているか」**の検証（`is_sid_in_room`）は明示的に先送りされており、以下の文が残っている：

> 残りのSocketイベント（battle/char/items/exploration）の全面棚卸しはPhase 5で実施。（26, Phase 0第2弾）

本計画はその棚卸しと修正を担う。

**ゴール**：全Socketイベントハンドラで、ペイロードの `room` に対してSIDが在室済みかを検証し、
クロスルーム操作（在室していないルームへの書き込み・読み取り）を不可能にする。

---

## 2. 現状の問題

### 2.1 既に正しく実装されているファイル（参考）

| ファイル | 良い実装 |
|---|---|
| `events/socket_main.py` | `is_sid_in_room(request.sid, room)` を呼んでいる |
| `events/socket_room_presets.py` | `_require_room_participant(room)` ヘルパーを使用 |
| `events/socket_battle_only.py` | `_require_gm(event)` + `_require_room_participant(room)` |

### 2.2 未修正ファイルの問題一覧

| 優先度 | ファイル | 対象イベント数 | 問題内容 |
|---|---|---|---|
| 🔴 Critical | `events/socket_exploration.py` | 4 | TODO残存。在室チェックなし・GM権限サーバー検証なし |
| 🔴 Critical | `events/battle/common_routes.py` | ~30 | 在室チェックなし（ターン進行・スキル宣言・行動意図 等） |
| 🟠 High | `events/battle/duel_routes.py` | 複数 | 在室チェックなし |
| 🟠 High | `events/battle/wide_routes.py` | 複数 | 在室チェックなし |
| 🟠 High | `events/socket_char.py` | 複数 | キャラ追加/編集に在室チェックなし |
| 🟡 Medium | `events/socket_items.py` | 複数 | owner_id検証あり・在室チェックなし |

### 2.3 具体的なリスク例

- ルームAにいるユーザーが `{'room': 'ルームB', 'mode': 'exploration'}` を送信し、ルームBの探索モードを切り替えられる
- ルームAのプレイヤーが `{'room': 'ルームB'}` を送信し、ルームBのターンを進められる
- 在室していないルームにキャラクターを追加できる

---

## 3. 設計方針

### 3.1 適用する検証パターン

`manager/room_access.py` の `is_sid_in_room` を使う。既に全ファイルにインポート可能。

```python
from manager.room_access import is_sid_in_room

@socketio.on('request_change_mode')
def handle_change_mode(data):
    room = data.get('room')
    if not room:
        return
    if not is_sid_in_room(request.sid, room):   # ← 追加
        emit('error', {'message': 'Not in this room'}, to=request.sid)
        return
    # 既存処理
```

### 3.2 GM権限が必要なイベントの検証順序

在室チェック → GM権限チェック の順で行う。  
GM権限判定は Plan 26 Phase 5 で実装済みの `get_user_info_from_sid` 経由で membership から取得できる。

```python
if not is_sid_in_room(request.sid, room):
    emit('error', {'message': 'Not in this room'}, to=request.sid)
    return
user_info = get_user_info_from_sid(request.sid)
if user_info.get('attribute') != 'GM':
    emit('error', {'message': 'GM only'}, to=request.sid)
    return
```

### 3.3 キャラクター操作の検証順序

在室チェック → キャラ所有者チェック（`is_authorized_for_character`）の順。  
所有者チェックは既存のものをそのまま活用する。

---

## 4. 実装フェーズ

### Phase A: 探索モード（小規模・先行）

**対象**: `events/socket_exploration.py`

**作業内容**：

1. 全4イベントの先頭に `is_sid_in_room` チェックを追加
2. BGM変更・立ち絵位置更新などGM専用操作にGM権限サーバー検証を追加
3. line 25-28 の TODO コメントを削除

**対象イベント一覧**：

| イベント名 | 現状 | 追加する検証 |
|---|---|---|
| `request_change_mode` | 在室チェックなし | 在室チェック |
| `request_update_exploration_bg` | 在室チェックなし・GM検証なし | 在室チェック + GM権限 |
| `request_update_tachie_location` | 在室チェックなし | 在室チェック（全員可） |
| `request_exploration_roll` | 在室チェックなし | 在室チェック |

**完了ゲート**：
- 在室していないSIDからのイベントがエラーを返す
- 非GMからの背景変更が拒否される
- 正常な在室ユーザーからの操作が従来通り動作する

---

### Phase B: キャラクター管理

**対象**: `events/socket_char.py`

**作業内容**：

1. キャラクター追加イベントの先頭に `is_sid_in_room` チェックを追加
2. その他のキャラ操作イベント（編集・削除等）にも同様に追加
3. 追加後 `is_authorized_for_character` との二重検証になっていることを確認

**完了ゲート**：
- 在室していないSIDが別ルームにキャラを追加できない
- 既存のキャラ所有者チェックが引き続き機能する

---

### Phase C: 戦闘イベント（大規模・体系的）

**対象**: `events/battle/common_routes.py`, `events/battle/duel_routes.py`, `events/battle/wide_routes.py`

**作業内容**：

1. 各ファイルのSocketハンドラを全件リストアップ
2. 各イベントに必要な権限レベル（在室のみ / GM専用 / キャラ所有者 or GM）を確定
3. 権限レベルに応じた検証を先頭に追加

**権限レベル分類（common_routes.py 主要イベント）**：

| イベント名 | 必要権限 |
|---|---|
| `request_next_turn` | GM |
| `request_new_round` | GM |
| `request_end_round` | GM |
| `request_reset_battle` | GM |
| `request_force_end_match` | GM |
| `request_move_token` | 在室（キャラ所有者 or GM） |
| `battle_intent_commit` | 在室（キャラ所有者 or GM） |
| `battle_intent_change_skill` | 在室（キャラ所有者 or GM） |
| `battle_intent_change_target` | 在室（キャラ所有者 or GM） |
| `request_add_debug_character` | GM |
| その他戦闘設定系 | GM |

**完了ゲート**：
- 在室していないSIDがターンを進められない
- playerがGM専用操作を実行できない
- 既存の正常な戦闘フローが動作する

---

### Phase D: アイテム使用

**対象**: `events/socket_items.py`

**作業内容**：

1. `request_use_item` の先頭に `is_sid_in_room` チェックを追加
2. その他のアイテム系イベントにも同様に追加

---

### Phase E: テスト追加

**新規テストファイル**: `tests/test_socket_room_auth.py`

**テスト内容**：

```python
# 在室していないSIDからのイベントが拒否される
def test_exploration_rejects_non_room_member():
    # SIDをルームAで接続し、ルームBのイベントを送信 → エラー返却

def test_battle_next_turn_rejects_non_room_member():
    # 同上（戦闘版）

def test_battle_next_turn_rejects_non_gm():
    # 在室しているがGMでないユーザーからのターン進行 → 拒否

def test_exploration_bg_rejects_non_gm():
    # 在室しているがGMでないユーザーからの背景変更 → 拒否

def test_char_add_rejects_non_room_member():
    # 在室していないSIDからのキャラ追加 → 拒否

# 正常動作の回帰テスト
def test_exploration_change_mode_ok():
def test_battle_intent_ok_by_char_owner():
```

---

## 5. 実装手順

1. Phase A（探索）を先行実装・単体確認
2. Phase B（キャラ）を実装
3. Phase C（戦闘 common_routes）を実装 — イベント数が多いため `grep @socketio.on events/battle/common_routes.py` で全件洗い出してから着手
4. Phase C（duel/wide）を実装
5. Phase D（アイテム）を実装
6. Phase E（テスト）を追加・全件通過確認
7. `pytest -q` + `python scripts/check_text_encoding.py` でCIチェック通過確認
8. JS編集がある場合は `npm run build`
9. 本ファイルを `manuals/implemented/` へ移管

---

## 6. 修正対象ファイルマップ

```
manager/
  room_access.py      ← is_sid_in_room() の定義元（変更不要）

events/
  socket_exploration.py   ← Phase A（4イベント）
  socket_char.py          ← Phase B
  socket_items.py         ← Phase D
  battle/
    common_routes.py      ← Phase C（最大・~30イベント）
    duel_routes.py        ← Phase C
    wide_routes.py        ← Phase C

tests/
  test_socket_room_auth.py  ← Phase E（新規）
```

---

## 7. 実装進捗

- [x] Phase A: 探索モード（`socket_exploration.py`）2026-06-27
- [x] Phase B: キャラクター管理（`socket_char.py`）2026-06-28
- [x] Phase C: 戦闘 common_routes 2026-06-28
- [x] Phase C: 戦闘 duel_routes / wide_routes 2026-06-28
- [x] Phase D: アイテム使用（`socket_items.py`）2026-06-28
- [x] Phase E: テスト追加・全件通過（`tests/test_socket_room_auth.py` 8件）2026-06-28
- [x] `pytest -q` 通過（568 passed）2026-06-28
- [ ] 実機スモーク確認（探索モード切替・戦闘ターン進行・キャラ追加）
- [ ] `manuals/implemented/` へ移管

---

## 8. 完了条件

- 在室していないSIDからのいかなるSocketイベントも、対象ルームの状態を変更・読み取りできない
- GM専用操作はサーバー側でGM権限を検証している（フロントのUI制御は補助のみ）
- 既存の正常な戦闘・探索フローが全て動作する（回帰なし）
- `pytest -q` で全件通過
