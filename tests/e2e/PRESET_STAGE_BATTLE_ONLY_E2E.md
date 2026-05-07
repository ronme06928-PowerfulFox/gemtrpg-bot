# プリセット/ステージ E2E 確認手順

## 目的
通常プリセット適用、戦闘専用ステージ選択、戦闘突入、ステージ効果詳細表示の主要導線で、致命的なエラーや明らかな誤表示が出ないことを確認します。

## 自動テスト
通常の `pytest` ではスキップされます。ブラウザとローカルサーバーを用意できる環境でのみ実行します。

```powershell
python app.py
```

別ターミナルで実行します。

```powershell
$env:RUN_ROOM_PRESET_E2E = "1"
$env:ROOM_PRESET_E2E_BASE_URL = "http://127.0.0.1:5000"
pytest -q tests/e2e/test_room_preset_apply_e2e.py
```

ブラウザを表示して確認したい場合は以下も設定します。

```powershell
$env:ROOM_PRESET_E2E_HEADLESS = "0"
```

## 確認範囲
自動テストは以下を通します。

1. GMとして入室する。
2. 通常ルームを作成する。
3. `通常プリセット` を開く。
4. ステージ適用チェックボックスを確認する。
5. ステージプリセットを通常ルームへ適用する。
6. 戦闘専用ルームを作成する。
7. `戦闘専用編成` を開く。
8. ステージプリセットを選択する。
9. `戦闘突入` を実行する。
10. 戦闘中のステージ効果カードを確認する。
11. `詳細` からステージ効果詳細を開く。
12. `ステージ効果詳細` と `効果ルール` が表示されることを確認する。

## 失敗時に見る場所
- `#visual-room-preset-btn`: 通常プリセットボタン
- `#room-preset-apply-backdrop`: 通常プリセットモーダル
- `#room-stage-apply-*`: ステージ適用チェックボックス
- `#visual-bo-btn`: 戦闘専用編成ボタン
- `#bo-draft-backdrop`: 戦闘専用編成モーダル
- `#bo-stage-select`: ステージ選択
- `#bo-draft-start-btn`: 戦闘突入
- `#visual-stage-effect-card`: 戦闘中のステージ効果カード
- `#stage-field-effect-modal-backdrop`: ステージ効果詳細
