# R1：冥鳴ひまりとSEの短い試作

計画53のR1。宣言・マッチ、威力、ダメージと勝利FPの3場面・10段階です。
約51.94秒。合意した台本を省略せず、声を早めて目安の45秒へ収めることはしていません。
全編の作り直しは、この試作の確認後です。

## 仮置きと合意した表現

- 味方は男冒険者、HP129/129・MP12/12・FP0。敵は人狼型シュラーカー、HP30/30・MP6/6・FP0。
- 画像・最大値は試作用の仮置き。表示名は「味方」「敵」。画像自体は元PNGと同じです。
- 威力の台本はユーザー提示の「基礎威力」「ダイス威力」「物理補正」「最終威力」を使います。
- 「スキルを破壊する」は使わず、攻撃同士のマッチで勝った側だけが攻撃できると説明します。
- 敵HPは30→21、味方FPは0→1。最後に両方のスロットを「行動済み」とし、「これで2人とも行動を終えました」と話します。
- 前の場面・出身の恩恵・HP/MPを持ち越す説明、速度値6の味方から攻撃するような説明は入れません。
- R1は全編の途中の抜粋なので、ラウンド開始や終了時FP＋2の場面は含みません。

## 声と音源

- VOICEVOX ENGINE **0.26.0、Windows CPU版**。冥鳴ひまり／ノーマル。
- `/speakers`でキャラクターとスタイルを検索し、今回の応答はstyle id 14でした。数値だけで声を決めません。
- 話速1.0、ピッチ0、抑揚1.0。詳細はvoice/config.json。VOICEVOXエディターは使っていません。
- `parseNarration`のttsPartsを使います。表示文は変えず、「1d2」「1d3」「FP」の読みを指定します。
- markごとの音声長を足して、manifestのcuesへ設定します。原音とqueryはvoice/cache/に保持し、台本・声・設定を含むhashで再利用します。
- 声は-20 LUFSを目標に調整。同じ声に従来SEと＋6dBのSEを合成した2案です。
- 音源の出典・ライセンスは[sfx/README](sfx/README.md)。BGMはありません。
- 最後のスライドに**VOICEVOX:冥鳴ひまり**を表示。字幕OFFでも残ります。

## VOICEVOXの導入と起動

[公式リリース0.26.0](https://github.com/VOICEVOX/voicevox_engine/releases/tag/0.26.0)のWindows CPU版を、リポジトリ外の
`C:/Users/yharu/tools/voicevox-engine-0.26.0/windows-cpu/`へ展開しました。
ダウンロードしたアーカイブのSHA-256は、GitHub公式APIのdigestと照合済みです。
`8684e1aa6b856c9fb51720552b4f2d5068e094bc3d0b104467dee20b76f99992`

```powershell
& C:/Users/yharu/tools/voicevox-engine-0.26.0/windows-cpu/run.exe --host 127.0.0.1 --port 50021 --no-use_gpu --cpu_num_threads 4 --disable_mutable_api --output_log_utf8
```

初回起動ではエンジンのユーザー辞書領域がAppDataに作られます。試作の読みはconfig.json内で指定し、エンジンの辞書APIは変更しません。
利用条件の確認結果は[計画53§6.2](../../../manuals/planned/53_Explainer_Video_Plan.md)にあります。
生成物を動画・HTMLで配布するときにもクレジットを残します。ソフトやモデルは配布しません。

## 生成・ビルド・確認

リポジトリのルートから、VOICEVOXを起動した状態で実行します。

```powershell
$egatariDir = 'C:/Users/yharu/tools/egatari-studio'
$r1Dir = Join-Path (Get-Location) 'typst_manual/動画/01_1ラウンドの流れ_R1'
$ffmpegDir = 'C:/Users/yharu/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin'
$env:PATH = "$ffmpegDir;$env:PATH"
$videoTemp = Join-Path (Get-Location) 'typst_manual/動画/_local/media-temp'
New-Item -ItemType Directory -Force -Path $videoTemp | Out-Null
$env:TEMP = $videoTemp
$env:TMP = $videoTemp

node --test typst_manual/動画/scripts/test-r1-audio.mjs
node typst_manual/動画/scripts/prepare-r1.mjs $egatariDir --baseline
npm --prefix $egatariDir run build -- "$r1Dir/deck.html" --embed-audio
Copy-Item -LiteralPath "$r1Dir/out/deck.html" -Destination "$r1Dir/out/deck-baseline.html"
node $egatariDir/render/render.mjs "$r1Dir/out/deck-baseline.html" --out "$r1Dir/out/baseline" --full --fps 24 --scale 1 --captions

node typst_manual/動画/scripts/prepare-r1.mjs $egatariDir
npm --prefix $egatariDir run build -- "$r1Dir/deck.html" --embed-audio
Copy-Item -LiteralPath "$r1Dir/out/deck.html" -Destination "$r1Dir/out/deck-plus6.html"
node typst_manual/動画/scripts/verify-r1.mjs $egatariDir
npm --prefix $egatariDir run check -- "$r1Dir/deck.html"
node $egatariDir/render/render.mjs "$r1Dir/out/deck-plus6.html" --out "$r1Dir/out/plus6" --full --fps 24 --scale 1 --captions
npm --prefix $egatariDir run sheet -- $r1Dir --tiles --cols 3 --width 640
```

- `out/baseline/full.mp4`と`out/plus6/full.mp4`で聴き比べます。声と画像、長さは同じです。
- 単一HTMLは`out/deck-baseline.html`と`out/deck-plus6.html`。`?captions=1`、Aキーで声付き自動再生。
- `out/audio-report-*.json`に声の識別・キュー・段階長・合成後ピークを記録します。
- `voice/cache/`、`audio/steps/`、`audio/manifest.json`、`out/`はGit対象外です。
- 基準版のprepare-media.mjsとegatariのsynth.pyはR1の生成に使いません。

## 検証

WAVの入出力、markの区切り時刻、混合時のピークと範囲外SEをユニットテストします。
ブラウザでは全音声段階の先頭・中間・末尾の字幕、cue、数値、巻き戻し、画像の読み込み、字幕OFFのクレジットを確認します。
動画出力で字幕が途中から飛ばないよう、R1の部品は各音声段階の全長を描きます。
checkの警告3件は入場段階0の台本なしです。通常の音声段階は7件すべてに音声があります。

試聴後、SEは＋6dB版の採用を決めました。声の細かな読み・間は全編で確認します。
共通クレジットを最後に5秒表示する方針も合意済みです。R1は比較の記録として保持し、次は計画53のR2-1（全編台本とクレジットの見本）へ進む計画です。
