# 状態配信のローカル計測

対象: `PERF-BASELINE`。合成データだけで状態配信の構築・Socket.IO Packetエンコード・サイズを測る。通常起動したアプリや本番へは接続しない。

## 実行

アプリ用のPython依存が入った環境で、リポジトリ直下から実行する。

```powershell
python scripts/benchmark_state_delivery.py
```

このPCでPythonの環境を明示する場合:

```powershell
& 'C:/Users/yharu/anaconda3/python.exe' scripts/benchmark_state_delivery.py
```

結果は `_local/performance/state_delivery.json` の最新1点に上書きする。既存のDB・ルーム・マスター・バックアップへ書き込まない。環境・HEAD・未コミット差分の有無と計測対象ソースのハッシュを記録し、ルームの内容や環境変数は出力しない。

既定は準備5回、定常100回。別条件は `--warmup` と `--samples`、結果を別に保存する場合は `--output` で指定する。比較が済んだ古い結果は残さず、再測定に必要なスクリプトと最新JSONを保持する。

## 読み方

- small / medium / stressは固定合成条件で、実際の卓の代表条件ではない。全体状態と戦闘状態の2イベントが出なければ測定失敗とする。
- `first_ms` はその条件の初回測定。アプリのコールドスタート時間ではない。準備の後の定常値からp50・nearest-rankのp95・最大値を求める。
- `participant_build_ms` は公開状態のdeepcopy、`battle_payload_build_ms` は戦闘状態の構築、`packet_encode_ms` は標準Socket.IO Packetエンコード。`total_ms` は配信関数の全体で、計測用ラッパーの負荷も含む。
- `packet_bytes` はSocket.IOイベント文字列をUTF-8にしたサイズ。Engine.IO/WebSocket/TLSヘッダー、圧縮、回線、受信者数は含まない。`participant_json_field_bytes` は値だけのcompact JSONで、イベント合計への内訳の目安。
- 宣言・解決計算・DB・サーバーの休止復帰・Socket往復・ブラウザ描画は測っていない。宣言ハンドラが使うイベント経路も全体配信と異なる。

初回結果・制約・次の測定は[性能計画](../projects/app_foundation/performance_and_hosting.md#状態配信の初回結果)、課題の状態は[基盤課題一覧](../projects/app_foundation/backlog.md)に記録する。

## ツールの検証

```powershell
python -m pytest -q tests/test_state_delivery_benchmark.py tests/test_python_module_size_guard.py
```

テストではネットワーク・DB接続の拒否、2イベントの実生成とエンコードサイズ、集計・入力エラー、秘密情報を結果へ出さないことを確認する。独立したサブプロセスで計測し、実アプリの起動・DBへ接続しない。
