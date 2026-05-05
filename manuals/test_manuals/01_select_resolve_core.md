# 01 Select/Resolve Core

## 責務範囲
- `manager/battle/core.py`
- `manager/battle/resolve_auto_runtime.py`
- `manager/battle/resolve_auto_mass_phase.py`
- `manager/battle/resolve_auto_single_phase.py`

## 目的
- フェーズ遷移（`resolve_mass -> resolve_single -> round_end`）が崩れないこと
- trace と state emit が意図通り出力されること
- resolve 実行後に一時コンテキストが掃除されること

## 自動テスト
```powershell
pytest -q tests/test_select_resolve_smoke.py
```

## 重点観点
- `step_total` が stale 値を引きずらない
- `resolve_snapshot_intents` がない場合でも `intents` にフォールバックする
- `battle_state` の一時キー（`__room_name`, `__resolve_intents_override`）が最終的に消える

## 実機確認
- 同一ラウンド内で mass と single の両方を宣言し、mass が先に解決されること
- round 終了時に UI 側が `battle_round_finished` を受け取り、入力状態がリセットされること
- ログポップアップを開いて trace が欠落していないこと
