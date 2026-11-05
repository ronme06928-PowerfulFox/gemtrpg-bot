# 動画の追加字体

元ファイルはGoogle Fonts公式リポジトリの以下から2026-11-05に取得した。双方SIL Open Font License 1.1で、埋め込み・改変・再配布可能。元の著作権とOFL全文は隣のOFL-*.txt、配布HTMLのfont-licensesにも収録する。Reserved Font Nameの指定は両方ともない。

- Cinzel: https://github.com/google/fonts/blob/main/ofl/cinzel/Cinzel%5Bwght%5D.ttf
- Zen Antique: https://github.com/google/fonts/blob/main/ofl/zenantique/ZenAntique-Regular.ttf

指定PythonのfontToolsとBrotliで `scripts/prepare-video-fonts.py` を実行する。Cinzelは900へ静的化、Zen Antiqueは400。台本・デッキ・本番の描画文字を拾ったWOFF2を生成し、デッキ内fonts/へコピーする。URLは必ずデッキ内へ向ける（egatariがフォルダ外のURLを埋め込まないため）。著作権・許諾のnameメタデータも保持する。

元ファイルのSHA-256:

- `Cinzel-wght.ttf`: `f4d83d34d1f6c741193e4acf4b3dff9531e5a67b6aa65228d00a7db72a4e0f34`
- `ZenAntique-Regular.ttf`: `8c5cf7a136837ee705d06bbc133ea18ac06b7dd284f38aace91f5de36725c315`
