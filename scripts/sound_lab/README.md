# 宝石の加護の試聴（計画55 §4.3）

`presets.json` の値を直し、リポジトリのルートで次を実行する。Python は NumPy・SciPy 入りの Anaconda、`ffmpeg` は [動画の README](../../typst_manual/動画/README.md) の手順で 9.0.1 を PATH の先頭に置く。

```powershell
& 'C:/Users/yharu/anaconda3/python.exe' scripts/sound_lab/chime.py
npm run gallery
```

48 kHz ステレオの OGG は `_local/sound_lab/` に生成する。試聴ページは `_local/fx_gallery/fx_gallery.html`。C1 の試聴版は `_local/sound_sources/c1_preview.mp3` に置く。C1 が手元にない場合も S1〜S3 は生成できる。

| 注文 | 変える値 |
| --- | --- |
| さらさら | `copies` を増やし、`copy_gain` を下げる。`jitter.time` と `jitter.pan` で粒をわずかに散らす |
| 神聖 | `reverb.seconds` と `reverb.mix` を上げ、`reverb.cutoff_hz` を下げて柔らかく広げる |
| 明るく／暗く | `overtones` を上げる／下げる。`cutoff_hz` を上げる／下げる |
| 耳障り | `cutoff_hz` と `strike.gain` を下げる。高い部分音の `decay` を短くする |
| 余韻を短く | `decay` と `reverb.seconds` を下げる。さらに短くする場合は `fade` を増やす |
| 重く／軽く | `low_gain` を上げる／下げる |
| 派手に／控えめに | `reverb.mix`・`jitter.pan`・粒数を上げる／下げる。試聴時の音量は一覧のつまみで動かす |

`seed` を固定すると合成は同じ波形になる。`duration` と `fade` は秒、`decay` は各部分音が20 dB下がるまでの秒。全案の出力ピークは `peak_dbfs` でそろえる。

```powershell
& 'C:/Users/yharu/anaconda3/python.exe' scripts/sound_lab/analyze.py _local/sound_sources/c1_preview.mp3 --output _local/sound_lab/c1-analysis.json
& 'C:/Users/yharu/anaconda3/python.exe' scripts/sound_lab/analyze.py _local/sound_sources/c1_preview.mp3 --compare _local/sound_lab/s1.ogg
```

原音では 3.89 秒まで発音候補が続くため、解析は冒頭から 4.05 秒を使う。比較では発音間隔、重心、基音・高域の減衰を同じ方法で推定する。候補は音の立ち上がりの推定で、棒の本数には一致しない。試聴版の高域は圧縮と重なった余韻の影響があるため、推定した比と減衰は目安にする。値の表では推定できた部分音を使い、読めない部分には自由な棒の比と減衰の初期値を使う。
