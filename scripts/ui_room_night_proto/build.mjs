import { readFile, writeFile } from 'node:fs/promises';

const out = new URL('../../_local/ui_room_night_proto/', import.meta.url);
const widths = [1280, 1024];
const scenes = [
  {
    id: 'a', title: 'A　探索中',
    note: 'ドックと枠を暗い面にまとめると、立ち絵と探索背景に目が向く。長文は紙の面に残し、話者と判定結果を色と太字で見分けられる。',
    shots: [['a', 'PC4人・会話・探索ドック']],
  },
  {
    id: 'b', title: 'B　戦闘中のラウンド',
    note: '明るい青・赤は盤面で輪郭を拾いやすく、HP・MPは数値、FPは丸い札でも見分けられる。1024pxでは宣言パネルが盤面とチャットの一部に重なる。',
    shots: [['b-board', '盤面と陣営色', 'tokens'], ['b-declare', '宣言とチャット'], ['b-resolve', '解決とチャット']],
  },
  {
    id: 'c', title: 'C　窓',
    note: '夜色のキャラ・アイテム窓から紙のスキル詳細へ切り替わると、参照画面だと分かる。宝石の印は見出しを拾いやすくするが、絵文字のある見出しでは印が重なる。',
    shots: [['c-character', 'キャラ設定・スキル・バフ'], ['c-items', 'アイテム'], ['c-skill', 'スキル詳細（紙）']],
  },
  {
    id: 'd', title: 'D　知らせ',
    note: '確認は金の主ボタン、誤りは見出しと枠、成功は緑の印で区別する。右下の知らせは盤面の中央を空けるが、幅1024pxではチャットと重なる。',
    shots: [['d-confirm', '保存の確認'], ['d-error', '誤りの窓'], ['d-notices', '保存結果と右下の知らせ']],
  },
];

function figure(id, variant, width, title) {
  const src = `shots/${id}-${variant}-${width}.png`;
  return `<figure><figcaption>${title}</figcaption><a href="${src}" target="_blank" rel="noopener">
    <img src="${src}" width="${width}" height="800" alt="${title}・${width}px" loading="lazy"></a></figure>`;
}

function compare([id, title, variant], width) {
  const current = figure(id, 'current', width, '今');
  const night = figure(id, 'night', width, '夜色と金');
  if (!variant) return `<h3>${title}</h3><div class="comparison">${current}${night}</div>`;
  return `<h3>${title}</h3><div class="comparison">${current}<div>
    <fieldset class="palette"><legend>陣営と HP・MP・FP</legend>
      <label><input type="radio" name="palette-${width}" value="legacy" checked> 今の色</label>
      <label><input type="radio" name="palette-${width}" value="night"> 夜色のトークン</label>
    </fieldset>
    <div data-palette="legacy">${night}</div>
    <div data-palette="night" hidden>${figure(id, 'tokens', width, '夜色と金・夜色のトークン')}</div>
  </div></div>`;
}

function sceneHtml({id, title, note, shots}, width) {
  const gemComparison = id === 'c' ? `<h3>宝石の印 · タブとアイテムの見出し</h3>
    <div class="comparison">${figure('c-items', 'night', width, '印なし')}${figure('c-items', 'gems', width, '印あり')}</div>` : '';
  return `<section id="${id}-${width}"><h2>${title}</h2><p>${note}</p>
    ${shots.map(shot => compare(shot, width)).join('')}${gemComparison}</section>`;
}

for (const width of widths) {
  const files = scenes.flatMap(scene => scene.shots.flatMap(([id, , variant]) =>
    ['current', 'night', ...(variant ? [variant] : []), ...(id === 'c-items' ? ['gems'] : [])]
      .map(style => `shots/${id}-${style}-${width}.png`)));
  await Promise.all(files.map(async filename => {
    const png = await readFile(new URL(filename, out));
    if (png.readUInt32BE(16) !== width || png.readUInt32BE(20) !== 800) throw Error(`画像の寸法が不正です: ${filename}`);
  }));
}

await writeFile(new URL('index.html', out), `<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ルームと戦闘 · 夜色と金の試作</title>
<style>
  :root { color-scheme: dark; color: #ece6d6; background: #0f1120; font: 16px/1.65 system-ui, sans-serif; }
  * { box-sizing: border-box; }
  body { max-width: 2600px; padding: 1.2rem clamp(.8rem, 2vw, 2rem) 3rem; margin: auto; }
  h1, h2 { font-family: "Yu Mincho", serif; margin: 0; }
  h1 { color: #f0d27a; }
  h3 { margin: 1.1rem 0 .4rem; font-size: 1rem; }
  p { margin: .35rem 0 .8rem; max-width: 75ch; color: #d4cfbf; }
  fieldset { margin: 0 0 .4rem; padding: .2rem .7rem .45rem; border: 1px solid #8f93aa; border-radius: .4rem; }
  legend { padding-inline: .3rem; }
  label { margin-inline-end: .7rem; white-space: nowrap; }
  input { accent-color: #d9b85a; }
  a { color: #f0d27a; }
  :focus-visible { outline: 2px solid #f0d27a; outline-offset: 2px; }
  nav { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
  section { margin-top: 1.6rem; border-top: 1px solid #8f7a3c; padding-top: 1rem; }
  .comparison { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: end; gap: .8rem; }
  figure { margin: 0; }
  figcaption { margin-bottom: .25rem; font-weight: 700; }
  img { display: block; width: 100%; height: auto; border: 1px solid #8f7a3c; border-radius: .4rem; }
</style>
</head>
<body>
<h1>ルームと戦闘 · 夜色と金の試作</h1>
<p>同じルームを今の画面と夜色で撮影しました。画像を開くと撮影時の幅で確認できます。</p>
<nav aria-label="表示切替">
 <fieldset><legend>撮影時の幅</legend>
  ${widths.map((w, i) => `<label><input type="radio" name="width" value="${w}" ${i ? '' : 'checked'}> ${w}px</label>`).join('')}
 </fieldset>
 ${scenes.map(({id, title}) => `<a data-scene="${id}" href="#${id}-1280">${title}</a>`).join('')}
</nav>
<main>${widths.map((w, i) => `<div data-width="${w}" ${i ? 'hidden' : ''}>${scenes.map(scene => sceneHtml(scene, w)).join('')}</div>`).join('')}</main>
<script>
  document.addEventListener('change', ({target}) => {
    if (target.name === 'width') {
      for (const panel of document.querySelectorAll('[data-width]')) panel.hidden = panel.dataset.width !== target.value;
      for (const link of document.querySelectorAll('[data-scene]')) link.href = '#' + link.dataset.scene + '-' + target.value;
    }
    if (target.name.startsWith('palette-')) {
      for (const picture of target.closest('.comparison').querySelectorAll('[data-palette]')) {
        picture.hidden = picture.dataset.palette !== target.value;
      }
    }
  });
</script>
</body>
</html>
`, 'utf8');
console.log('Wrote _local/ui_room_night_proto/index.html');
