# 亀裂 ラウンド管理仕様書（実装済み）

**文書種別**: 実装仕様（implemented）  
**最終更新日**: 2026-03-26  
**ステータス**: 実装済み  
**対象コード**: `manager/game_logic.py`, `manager/utils.py`, `manager/battle/common_manager.py`, `manager/battle/core.py`, `plugins/fissure.py`

---

## 1. 仕様要点

本仕様では、亀裂付与の管理を次のルールで統一する。

1. `APPLY_STATE` で `state_name: "亀裂"` かつ `value > 0` の場合:
   - `rounds > 0` が指定されていれば、新方式（時限亀裂バフ管理）で付与
   - `rounds` 未指定なら、旧方式（永続の状態異常加算）で付与
2. `APPLY_STATE_PER_N` で `state_name: "亀裂"` かつ `value > 0` の場合:
   - `rounds > 0` 指定時のみ新方式で付与
   - `rounds` 未指定時は旧方式のまま
3. `APPLY_FISSURE_BUFFED` も引き続き利用可能（新方式に合流）

---

## 2. 新方式のデータ管理

### 2.1 亀裂バフの表現

新方式では `special_buffs` に `buff_id: "Bu-Fissure"` を作成して管理する。  
バフ名は `亀裂_R{rounds}`（例: `亀裂_R4`）を使用する。

代表例:

```json
{
  "name": "亀裂_R4",
  "buff_id": "Bu-Fissure",
  "lasting": 4,
  "count": 3,
  "data": {
    "fissure_count": 3,
    "original_rounds": 4
  }
}
```

### 2.2 スタック規則

1. 同一 `original_rounds` の既存バフがある場合:
   - `count` のみ加算
   - `lasting` は更新しない（延長しない）
2. `original_rounds` が異なる場合:
   - 別バケットとして新規作成

---

## 3. 亀裂付与量上昇バフ（突き崩す等）の確定挙動

`_Crack` / `_CrackOnce` の `state_bonus(stat="亀裂")` は、新方式でも適用される。  
付与量は次で確定する。

`final_amount = base_amount + bonus_amount`

この `final_amount` は、**使用したスキルが指定した `rounds` の亀裂バケットへそのまま加算**する。  
増量分だけ別ラウンドのバケットを作ることはしない。

`_CrackOnce` は、実際に亀裂付与が成立した時のみ消費する（不発時は消費しない）。

---

## 4. 終了処理と崩壊処理

### 4.1 ラウンド終了時

`Bu-Fissure` の `lasting` が 0 になったら、対応する `count` 分だけ `亀裂` ステータスを減算してからバフを削除する。

### 4.2 亀裂崩壊時

`亀裂崩壊_DAMAGE` / `FISSURE_COLLAPSE` で亀裂を消費する際は、`亀裂` ステータス減算とあわせて `Bu-Fissure` バケットも整合して削除する。

---

## 5. スキルJSON書き換えガイド（実装準拠）

### 5.1 推奨方針

実装済み方針に合わせ、既存 `APPLY_STATE` 形式に `rounds` を追加する移行を推奨する。

- `rounds` あり: 時限亀裂
- `rounds` なし: 永続亀裂（旧仕様互換）

### 5.2 変換ルール

1. `APPLY_STATE` + `state_name: "亀裂"` + `value > 0`:
   - 時限化したい場合は `rounds` を追加
2. `APPLY_STATE_PER_N` + `state_name: "亀裂"` + `value > 0`:
   - 時限化したい場合は `rounds` を追加
3. `value <= 0` の亀裂減算・消費:
   - 既存定義を維持（書き換え不要）
4. 亀裂崩壊系 `CUSTOM_EFFECT`:
   - JSON変更不要（実装側で `Bu-Fissure` 整合クリア）
5. 増量バフを付与するスキル（例: `突き崩す_CrackOnce1`）:
   - 原則変更不要
   - 亀裂を実際に付与するスキル側に `rounds` を設定すること

### 5.3 書き換え例

#### 例A: `APPLY_STATE` を時限化（推奨）

変更前:

```json
{
  "timing": "HIT",
  "type": "APPLY_STATE",
  "target": "target",
  "state_name": "亀裂",
  "value": 1
}
```

変更後:

```json
{
  "timing": "HIT",
  "type": "APPLY_STATE",
  "target": "target",
  "state_name": "亀裂",
  "value": 1,
  "rounds": 3
}
```

#### 例B: `APPLY_STATE_PER_N` を時限化

変更前:

```json
{
  "timing": "HIT",
  "type": "APPLY_STATE_PER_N",
  "source": "self",
  "source_param": "戦慄",
  "per_N": 2,
  "target": "target",
  "state_name": "亀裂",
  "value": 1,
  "max_value": 2
}
```

変更後:

```json
{
  "timing": "HIT",
  "type": "APPLY_STATE_PER_N",
  "source": "self",
  "source_param": "戦慄",
  "per_N": 2,
  "target": "target",
  "state_name": "亀裂",
  "value": 1,
  "max_value": 2,
  "rounds": 3
}
```

#### 例C: 明示的に `APPLY_FISSURE_BUFFED` を使う場合（互換）

```json
{
  "timing": "HIT",
  "type": "APPLY_FISSURE_BUFFED",
  "target": "target",
  "rounds": 3,
  "value": 1
}
```

---

## 6. 実装確認チェック

1. `rounds` 付き `APPLY_STATE` で亀裂が `Bu-Fissure` 管理に入ること
2. `rounds` なし `APPLY_STATE` が旧挙動（永続）を維持すること
3. `_Crack` / `_CrackOnce` 増量分がスキル指定 `rounds` バケットに合算されること
4. ラウンド満了で `count` 分だけ `亀裂` が減算されること
5. 崩壊時に `Bu-Fissure` バケットが整合して消去されること
