# 21. Phase3 完了判定チェックリスト

**作成日**: 2026-05-02  
**用途**: Phase3 運用完了のGo/No-Goを同一基準で判定する。

---

## 1. 必須判定項目
- [ ] `skills_cache.json` で `schema` 未指定が 0 件
- [ ] `APPLY_BUFF` の `buff_id` 欠落が 0 件
- [ ] `REMOVE_BUFF` の `buff_id` 欠落が 0 件
- [ ] `buff_name` 単独指定（Phase3禁止）が 0 件
- [ ] `test_phase3_strict_rehearsal.py` が通過
- [ ] `test_phase3_non_battle_input_audit.py` が通過
- [ ] `test_skill_catalog_smoke.py`（JSON lint）が通過

## 2. 運用判定項目
- [ ] GMバフ付与UIが `buff_id` 入力専用である
- [ ] GMバフ解除APIが `buff_id` 必須である
- [ ] `gm_remove_buff_rejected(buff_not_found)` が異常増加していない
- [ ] 実運用マニュアルがPhase3仕様へ更新済み

## 3. ロールバック判定
- [ ] 重大障害時に戻す対象（設定/コード/キャッシュ）が明文化されている
- [ ] ロールバック後の検証手順（最低限テスト）が明文化されている

---

## 4. 判定ルール
- 全ての必須判定項目が `true` なら「Phase3完了」。
- 必須判定項目に1つでも `false` があれば「未完了」。
