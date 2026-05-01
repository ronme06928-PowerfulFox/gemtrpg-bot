# 17. Phase3 Strict Errata（既存マニュアル補正）

**作成日**: 2026-05-02  
**対象**: `manuals/implemented` 内の旧仕様記述

---

## 1. この補正の位置づけ
- 既存マニュアルに残る「`buff_name` 単独可」「動的命名バフ可」の記述は、Phase3時点では無効。
- 本書は、既存資料の差分補正として最優先で参照する。

## 2. Phase3で有効なルール
1. `APPLY_BUFF` は `buff_id` 必須。  
2. `REMOVE_BUFF` は `buff_id` 必須。  
3. `buff_name` 単独指定はエラー。  
4. 動的命名バフ（例: `Power_Atk5`）による効果決定は行わない。  
5. 効果強度は `buff_id + data.value` で扱う。

## 3. 既存資料で読み替える箇所
- `buff_id/buff_name` と書かれている箇所は `buff_id` のみ有効。
- `REMOVE_BUFF needs buff_name` と書かれている箇所は `buff_id` 必須へ読み替え。
- 動的パターン表（`_Atk{N}` 等）は履歴情報としてのみ扱い、現行運用には使わない。

## 4. 優先順位
- 実装コード（validator / runtime）  
  >
- 本Errata  
  >
- 旧マニュアル本文
