# 03 Single Phase And Reuse

## 責務範囲
- `manager/battle/resolve_auto_single_phase.py`

## 目的
- single queue の競合解決と one-sided/clash 分岐を安定化する
- USE_SKILL_AGAIN 系の仮想スロット挿入を安全に処理する

## 自動テスト
```powershell
pytest -q tests/test_select_resolve_smoke.py -k "single or reuse or hard_followup"
pytest -q tests/test_skill_target_tags.py
```

## 重点観点
- 同一 target 競合時に reciprocal clash を優先し、残りは one-sided になる
- 再使用スロットは deterministic な位置に挿入される
- `cancelled_without_use` と `resolved_slots` が整合する
- self destruct / feint / evade などの分岐が破綻しない

## 実機確認
- 再使用スキルでチェーン回数上限が効くこと
- 競合時に勝者/敗者のログとダメージ表示が矛盾しないこと
- one-sided 不発時に不要な追加演出が出ないこと
