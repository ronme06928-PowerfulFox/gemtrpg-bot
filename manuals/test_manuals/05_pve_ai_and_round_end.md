# 05 PvE AI And Round End

## 責務範囲
- `manager/battle/pve_intent_planner.py`
- `manager/battle/battle_ai.py`
- round_end 系（召喚・付与スキル・状態更新）

## 自動テスト
```powershell
pytest -q tests/test_pve_auto_intents.py tests/test_battle_ai_skill_selection.py
pytest -q tests/test_round_end_summon_lock.py tests/test_unified_calc.py
```

## 重点観点
- PvE 自動宣言が無効対象を選ばない
- AI がコスト不足や対象不整合を回避する
- round_end で summon / granted skill / status の同期が崩れない

## 実機確認
- PvE 部屋で複数ラウンド連続自動進行しても停止しないこと
- ラウンド跨ぎでバフ残存ターンやロック解除が正しいこと
- 召喚の出入り後もターゲット選択が壊れないこと
