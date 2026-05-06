# 通常プリセット E2E 確認手順

この手順は、通常ルームで戦闘専用プリセット由来の「敵キャラ」「敵編成」「ステージ」を扱う導線の回帰確認用です。

## 自動テスト

通常の `pytest` ではスキップされます。ブラウザとローカルサーバーを用意できる環境でだけ実行します。

```powershell
python app.py
```

別ターミナルで:

```powershell
$env:RUN_ROOM_PRESET_E2E = "1"
pytest -q tests/e2e/test_room_preset_apply_e2e.py
```

任意設定:

```powershell
$env:ROOM_PRESET_E2E_BASE_URL = "http://127.0.0.1:5000"
$env:ROOM_PRESET_E2E_HEADLESS = "0"
```

## 検証内容

1. GMとして入室する。
2. アプリ内入力モーダルで通常ルームを作成する。
3. 通常ルーム内で `通常プリセット` を開く。
4. ステージタブで以下4項目が表示されることを確認する。
   - `敵編成を適用（全置換）`
   - `背景を適用`
   - `フィールド効果を適用`
   - `ステージアバターを適用`
5. 敵キャラタブで敵プリセットを適用し、完了表示を確認する。
6. 敵編成タブで全置換確認モーダルを通して適用し、完了表示を確認する。
7. チャットログに `[Preset] enemy formation applied` が出ることを確認する。

## 失敗時に見る場所

- `#visual-room-preset-btn` が存在しない場合: 通常プリセットボタンの表示条件を確認する。
- `#app-dialog-input` または `#app-dialog-confirm` が存在しない場合: 標準 `prompt/confirm` へ戻っていないか確認する。
- `#room-stage-apply-*` が存在しない場合: ステージチェックボックスUIの描画を確認する。
- `適用しました` が出ない場合: `room_preset_applied` の受信、または完了メッセージ上書き処理を確認する。

