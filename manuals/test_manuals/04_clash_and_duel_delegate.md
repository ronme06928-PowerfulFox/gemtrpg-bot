# 04 Clash And Duel Delegate

## 責務範囲
- `manager/battle/resolve_match_runtime.py`
- `manager/battle/resolve_legacy_log_adapter.py`
- `manager/battle/resolve_trace_runtime.py`
- `manager/battle/resolve_effect_runtime.py`

## 目的
- duel_solver 委譲の計算を維持しつつ select/resolve 文脈に安全に取り込む
- 既存ログ形式と新trace形式の整合を保つ

## 自動テスト
```powershell
pytest -q tests/test_skill_target_tags.py tests/test_match_integraton.py
```

## 重点観点
- clash 委譲中に turn progression 副作用が漏れない
- delegate summary から legacy ログ入力への再構成が崩れない
- バフ付与/解除ログが欠落しない
- AFTER_DAMAGE_APPLY タイミングが双方に適用される

## 実機確認
- clash で引き分け/勝利/敗北それぞれの表示が正しいこと
- ログ詳細ポップアップの skill 情報・power snapshot が破綻しないこと
- 連続対戦でログ重複が増殖しないこと
