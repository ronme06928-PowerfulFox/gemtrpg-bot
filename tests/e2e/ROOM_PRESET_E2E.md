# 待機列と登場のブラウザー検証

ユニット・敵編成・ステージが入った確認用 DB でアプリを起動する。通常のテストではこのブラウザーテストをスキップする。

```powershell
$env:RUN_ROOM_PRESET_E2E = "1"
pytest -q tests/e2e/test_room_preset_apply_e2e.py
```

GM が通常ルームで遭遇を保存し、盤面へ登場させる。別のブラウザーの PL には確定したキャラクターだけが届く。

手動で操作を比較する場合は[D01 Part 5](../../manuals/implemented/D01_Play_Mode_Specs.md#part-5-待機列と登場計画61)に沿い、1280px と 680px で遭遇の準備・登場・増援を確認する。
