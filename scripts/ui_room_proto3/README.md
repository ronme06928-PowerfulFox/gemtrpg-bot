# ルームの試作 第3回

UI計画 §7.4 の論点7（大理石の白の窓）・論点8（宝飾の台座の飾り）・論点9（操作ボタンの色分け）を見るための見本です。アプリは起動しません。

```bash
node scripts/ui_room_proto3/build.mjs
```

`/_local/ui_room_proto3/index.html` を開きます（`python -m http.server 8765 --directory _local` などで配る）。上の帯で、場面・ボタンの色・大理石・台座の飾りを切り替えます。

- `marble.css`：大理石の白のトークン（`[data-theme="marble"]`、白と象牙）。筋は SVG のノイズから作る。
- `setting.css`：宝飾の台座の飾り（角の爪・見出しの宝石の台座・留め具の区切り・角を落としたボタン）。金属の色は各テーマの `--ui-gold` から取る。
- 夜色と紙の色は `static/css/modules/common_ui.css` をそのまま写して使う。
