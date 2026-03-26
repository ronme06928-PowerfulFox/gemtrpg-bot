# 02 Mass Phase

## 責務範囲
- `manager/battle/resolve_auto_mass_phase.py`

## 目的
- mass_summation と mass_individual の分岐を正しく解決する
- 対象収集、ダメージ適用、trace 追記を安定化する

## 自動テスト
```powershell
pytest -q tests/test_select_resolve_smoke.py -k "mass"
```

## 重点観点
- summation は参加者合算値との比較で delta ダメージを適用する
- individual は対象ごとに clash/one-sided を切り替える
- mass 処理後に `phase` が `resolve_single` に移る

## 実機確認
- 2体以上で mass_summation を受け、勝敗に応じて被ダメ対象が変わること
- mass ログの表示順が「結果 -> 詳細」の順で安定していること
- mass 解決後も single 解決が継続されること
